"""Job source fetchers. Each returns a list of normalized job dicts:

  source, title, company, location (str or list), salary, url, description (plain text), posted (datetime|None)

Terms checked 2026-11-17 (see README):
  Remotive   - public API, max ~4 calls/day, link back + credit "Remotive", no resubmitting to job boards.
  RemoteOK   - public API, link back to the Remote OK URL + credit "Remote OK".
  Himalayas  - public API, keep applicationLink unchanged, credit Himalayas, data refreshes daily.
  WWR        - public RSS feeds; terms have no clause against automated access.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

USER_AGENT = "job-hunter/1.0 (personal daily job search; one run per day)"
TIMEOUT = 30

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, */*"})


def html_to_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "• ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()


def fix_text(s: str) -> str:
    """Repair UTF-8 text that was decoded as Latin-1 ("â€" garbage) — happens on some feeds."""
    if s and ("â" in s or "Ã" in s):
        try:
            return s.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                return s.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return s


def _get(url: str, **params):
    r = session.get(url, params=params or None, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def _fmt_money(lo, hi, currency="USD", period=""):
    def f(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return f"{v:,.0f}" if v else None
    lo, hi = f(lo), f(hi)
    if not lo and not hi:
        return ""
    rng = f"{lo}–{hi}" if lo and hi and lo != hi else (lo or hi)
    return f"{currency or ''} {rng}{(' / ' + period) if period else ''}".strip()


# ---------------------------------------------------------------- Remotive
def fetch_remotive(cfg: dict) -> list[dict]:
    jobs, seen = [], set()
    for i, term in enumerate(cfg.get("remotive_searches", [])[:4]):  # hard cap: 4 calls/day
        if i:
            time.sleep(35)  # Remotive blocks >2 requests/minute
        data = _get("https://remotive.com/api/remote-jobs", search=term).json()
        for j in data.get("jobs", []):
            if j["url"] in seen:
                continue
            seen.add(j["url"])
            posted = None
            try:
                posted = datetime.fromisoformat(j["publication_date"]).replace(tzinfo=timezone.utc)
            except Exception:
                pass
            jobs.append({
                "source": "Remotive",
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("candidate_required_location", "") or "",
                "salary": j.get("salary", "") or "",
                "url": j["url"],
                "description": html_to_text(j.get("description", "")),
                "posted": posted,
            })
    return jobs


# ---------------------------------------------------------------- RemoteOK
def fetch_remoteok(cfg: dict) -> list[dict]:
    data = _get("https://remoteok.com/api").json()
    jobs = []
    for j in data[1:]:  # first element is the legal notice
        if not j.get("url"):
            continue
        posted = None
        if j.get("epoch"):
            posted = datetime.fromtimestamp(int(j["epoch"]), tz=timezone.utc)
        jobs.append({
            "source": "Remote OK",
            "title": fix_text(j.get("position", "")),
            "company": fix_text(j.get("company", "")),
            "location": fix_text(j.get("location", "") or ""),
            "salary": _fmt_money(j.get("salary_min"), j.get("salary_max"), "USD", "year"),
            "url": j["url"],
            "description": fix_text(html_to_text(j.get("description", ""))) + "\nTags: " + ", ".join(j.get("tags") or []),
            "posted": posted,
        })
    return jobs


# ---------------------------------------------------------------- Himalayas
def fetch_himalayas(cfg: dict) -> list[dict]:
    jobs, seen = [], set()
    for i, term in enumerate(cfg.get("search_terms", [])):
        if i:
            time.sleep(2)
        # country=Iraq returns jobs whose restrictions include Iraq or have none (worldwide)
        data = _get("https://himalayas.app/jobs/api/search", q=term, country="Iraq").json()
        for j in data.get("jobs", []):
            link = j.get("applicationLink") or j.get("guid")
            if not link or link in seen:
                continue
            seen.add(link)
            posted = None
            if j.get("pubDate"):
                posted = datetime.fromtimestamp(int(j["pubDate"]), tz=timezone.utc)
            jobs.append({
                "source": "Himalayas",
                "title": j.get("title", ""),
                "company": j.get("companyName", ""),
                "location": list(j.get("locationRestrictions") or []),
                "salary": _fmt_money(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod")),
                "url": link,  # kept unchanged, as the API terms require
                "description": html_to_text(j.get("description", "")),
                "posted": posted,
            })
    return jobs


# ---------------------------------------------------------------- We Work Remotely
WWR_FEEDS = [
    "https://weworkremotely.com/remote-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-design-jobs.rss",
    "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
    "https://weworkremotely.com/categories/all-other-remote-jobs.rss",
]


def fetch_wwr(cfg: dict) -> list[dict]:
    jobs, seen = [], set()
    for i, feed in enumerate(WWR_FEEDS):
        if i:
            time.sleep(2)
        root = ET.fromstring(_get(feed).content)
        for item in root.iter("item"):
            link = (item.findtext("link") or "").strip()
            if not link or link in seen:
                continue
            seen.add(link)
            raw_title = item.findtext("title") or ""
            company, _, title = raw_title.partition(": ")
            if not title:
                company, title = "", raw_title
            region = (item.findtext("region") or "").strip()
            country = (item.findtext("country") or "").strip()
            location = region if not country else f"{region}, {country}".strip(", ")
            posted = None
            try:
                posted = parsedate_to_datetime(item.findtext("pubDate"))
            except Exception:
                pass
            jobs.append({
                "source": "We Work Remotely",
                "title": title.strip(),
                "company": company.strip(),
                "location": location,
                "salary": "",
                "url": link,
                "description": html_to_text(item.findtext("description") or ""),
                "posted": posted,
            })
    return jobs


SOURCES = {
    "Remotive": fetch_remotive,
    "Remote OK": fetch_remoteok,
    "Himalayas": fetch_himalayas,
    "We Work Remotely": fetch_wwr,
}

SOURCE_HOME = {
    "Remotive": "https://remotive.com",
    "Remote OK": "https://remoteok.com",
    "Himalayas": "https://himalayas.app",
    "We Work Remotely": "https://weworkremotely.com",
}
