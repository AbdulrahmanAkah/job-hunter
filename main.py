"""Job Hunter — find new remote jobs open to Iraq, rank them, write daily files.

Usage:
  python main.py              # normal run (opens the HTML digest when run locally)
  python main.py --no-open    # don't open the browser
  python main.py --dry-run    # don't record jobs as seen (good for testing)
Nothing is ever applied to automatically.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from jobhunter.eligibility import RESTRICTED, classify
from jobhunter.output import write_claude_md, write_html, write_xlsx
from jobhunter.scoring import Scorer
from jobhunter.sources import SOURCES
from jobhunter.store import SeenStore

ROOT = Path(__file__).resolve().parent


def save_cache(jobs: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{**j, "posted": j["posted"].isoformat() if j["posted"] else None} for j in jobs]
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def load_cache(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    for r in rows:
        r["posted"] = datetime.fromisoformat(r["posted"]) if r["posted"] else None
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="don't record jobs as seen")
    ap.add_argument("--ignore-seen", action="store_true", help="include jobs already reported before")
    ap.add_argument("--from-cache", metavar="DATE", help="re-score the raw jobs saved on DATE (YYYY-MM-DD), no network")
    ap.add_argument("--skip", action="append", default=[], help="skip a source by name (repeatable)")
    ap.add_argument("--out", default="output", help="output folder (default: output)")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cfg = yaml.safe_load((ROOT / "keywords.yaml").read_text(encoding="utf-8"))
    scorer = Scorer(cfg)
    store = SeenStore(ROOT / "data" / "seen.sqlite")
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(cfg.get("max_age_days", 30)))
    cache_dir = ROOT / "data" / "cache"   # raw fetched jobs, kept locally (gitignored) for re-scoring

    fetched, errors = [], []
    if args.from_cache:
        fetched = load_cache(cache_dir / f"{args.from_cache}.json")
        print(f"[cache] loaded {len(fetched)} jobs from {args.from_cache}")
    else:
        for name, fn in SOURCES.items():
            if name in args.skip:
                print(f"[{name}] skipped")
                continue
            try:
                jobs = fn(cfg)
                print(f"[{name}] fetched {len(jobs)}")
                fetched += jobs
            except Exception as exc:  # one broken source must not stop the run
                print(f"[{name}] FAILED: {exc}")
                errors.append(name)
        save_cache(fetched, cache_dir / f"{date.today().isoformat()}.json")

    min_score = int(cfg.get("min_score", 0))
    stats = {"fetched": len(fetched), "old": 0, "already seen": 0, "not relevant": 0, "low score": 0, "restricted": 0}
    kept, seen_urls = [], set()
    for j in fetched:
        if j["url"] in seen_urls:
            continue
        seen_urls.add(j["url"])
        if j["posted"] and j["posted"] < cutoff:
            stats["old"] += 1
            continue
        if not args.ignore_seen and store.is_seen(j["url"]):
            stats["already seen"] += 1
            continue
        score, reason, relevant = scorer.score(j["title"], j["description"])
        if not relevant:
            stats["not relevant"] += 1
            continue
        if score < min_score:
            stats["low score"] += 1
            continue
        status, note = classify(j["location"], j["title"], j["description"])
        if status == RESTRICTED:
            stats["restricted"] += 1
            continue
        j.update(score=score, reason=reason, eligibility=status, elig_note=note)
        kept.append(j)

    kept.sort(key=lambda j: (j["score"], j["eligibility"] == "eligible"), reverse=True)
    stats["new jobs"] = len(kept)
    if errors:
        stats["failed sources"] = ", ".join(errors)

    day = args.from_cache or date.today().isoformat()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    write_xlsx(kept, out / f"{day}.xlsx")
    write_html(kept, out / f"{day}.html", day, stats)
    write_claude_md(kept, out / f"{day}_for_claude.md", day,
                    int(cfg.get("top_n_for_claude", 15)), int(cfg.get("description_chars_for_claude", 1200)))

    if not args.dry_run and not args.from_cache:
        store.mark(kept)
    store.close()

    print(" | ".join(f"{k}: {v}" for k, v in stats.items()))
    print(f"Wrote {args.out}/{day}.xlsx, {args.out}/{day}.html, {args.out}/{day}_for_claude.md")

    if not args.no_open and not os.environ.get("CI"):
        webbrowser.open((out / f"{day}.html").as_uri())
    return 1 if len(errors) == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
