"""Write the daily Excel file, HTML digest and the paste-into-Claude Markdown file."""
from __future__ import annotations

import html
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .sources import SOURCE_HOME

COLUMNS = [
    ("title", 45), ("company", 25), ("location", 30), ("salary", 22), ("score", 8),
    ("reason", 60), ("link", 50), ("letter", 40), ("eligibility", 18), ("source", 16),
]


def _loc(job) -> str:
    loc = job["location"]
    if isinstance(loc, list):
        if not loc:
            return "Worldwide"
        if len(loc) > 6:
            return f"{len(loc)} countries incl. Iraq"
        return ", ".join(loc)
    return loc or "(not stated)"


def write_xlsx(jobs: list[dict], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "jobs"
    ws.append([c for c, _ in COLUMNS])
    for i, (_, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="305496")
    check_fill = PatternFill("solid", fgColor="FFF2CC")
    for j in jobs:
        ws.append([
            j["title"], j["company"], _loc(j), j["salary"], j["score"], j["reason"],
            j["url"], "", j["eligibility"], j["source"],
        ])
        r = ws.max_row
        link = ws.cell(row=r, column=7)
        link.hyperlink = j["url"]
        link.font = Font(color="0563C1", underline="single")
        if j["eligibility"] != "eligible":
            ws.cell(row=r, column=9).fill = check_fill
        for c in (1, 6):
            ws.cell(row=r, column=c).alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)


def write_html(jobs: list[dict], path: Path, day: str, stats: dict) -> None:
    e = html.escape
    rows = []
    for j in jobs:
        badge = "" if j["eligibility"] == "eligible" else '<span class="chk">check location</span>'
        salary = f'<div class="sal">{e(j["salary"])}</div>' if j["salary"] else ""
        rows.append(f"""
<article>
  <div class="score s{min(j['score'] // 25, 3)}">{j['score']}</div>
  <div class="body">
    <h2><a href="{e(j['url'])}" target="_blank" rel="noopener">{e(j['title'])}</a></h2>
    <div class="meta">{e(j['company'])} · {e(_loc(j))} {badge}</div>
    {salary}
    <div class="reason">{e(j['reason'])}</div>
    <div class="src">via <a href="{e(SOURCE_HOME.get(j['source'], ''))}" target="_blank" rel="noopener">{e(j['source'])}</a> · {e(j['elig_note'])}</div>
  </div>
</article>""")
    stat_line = " · ".join(f"{e(k)}: {v}" for k, v in stats.items())
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Hunter {day}</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --muted:#667085; --line:#e4e7ec; --accent:#2f5fd0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171c; --card:#1d2129; --ink:#e7e9ee; --muted:#9aa3b2; --line:#2c323d; --accent:#7ea2ff; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .stats {{ color:var(--muted); font-size:13px; margin-bottom:20px; }}
article {{ display:flex; gap:14px; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; margin-bottom:10px; }}
.score {{ flex:none; width:44px; height:44px; border-radius:8px; display:grid; place-items:center; font-weight:700; color:#fff; }}
.s0 {{ background:#98a2b3; }} .s1 {{ background:#d39e00; }} .s2 {{ background:#3b82f6; }} .s3 {{ background:#16a34a; }}
.body {{ min-width:0; }} h2 {{ font-size:16px; margin:0 0 2px; }} a {{ color:var(--accent); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.meta,.src {{ color:var(--muted); font-size:13px; }} .reason {{ font-size:13px; margin-top:4px; overflow-wrap:anywhere; }} .sal {{ font-size:13px; }}
.chk {{ background:#fde68a; color:#78350f; border-radius:4px; padding:0 6px; font-size:12px; margin-inline-start:6px; }}
.empty {{ color:var(--muted); padding:40px 0; text-align:center; }}
</style></head><body><main>
<h1>Job Hunter — {day}</h1>
<div class="stats">{stat_line}</div>
{''.join(rows) if rows else '<p class="empty">No new matching jobs today.</p>'}
<p class="stats">Sources: <a href="https://remotive.com">Remotive</a>, <a href="https://remoteok.com">Remote OK</a>, <a href="https://himalayas.app">Himalayas</a>, <a href="https://weworkremotely.com">We Work Remotely</a>. Review each posting yourself before applying.</p>
</main></body></html>"""
    path.write_text(doc, encoding="utf-8")


def write_claude_md(jobs: list[dict], path: Path, day: str, n: int, chars: int) -> None:
    top = jobs[:n]
    out = [
        f"# Jobs for cover letters — {day}",
        "",
        "Please write a short, tailored cover letter (150–220 words) for each job below. "
        "I am based in Iraq and work remotely. Use only facts from my CV/profile; do not invent experience. "
        "Return one letter per job, headed with the job number and title.",
        "",
        "**My profile:** _(paste your CV summary here)_",
        "",
    ]
    for i, j in enumerate(top, 1):
        desc = j["description"][:chars].strip()
        if len(j["description"]) > chars:
            desc += " …"
        out += [
            "---",
            f"## {i}. {j['title']}",
            f"- **Company:** {j['company']}",
            f"- **Location:** {_loc(j)}" + ("  ⚠️ check location" if j["eligibility"] != "eligible" else ""),
            f"- **Link:** {j['url']}  (via {j['source']})",
            f"- **Score:** {j['score']} — {j['reason']}",
            "",
            desc,
            "",
        ]
    if not top:
        out.append("_No new matching jobs today._")
    path.write_text("\n".join(out), encoding="utf-8")
