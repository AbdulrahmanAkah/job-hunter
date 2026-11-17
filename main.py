"""Job Hunter — find new remote jobs open to Iraq, rank them, write daily files.

Usage:
  python main.py              # normal run (opens the HTML digest when run locally)
  python main.py --no-open    # don't open the browser
  python main.py --dry-run    # don't record jobs as seen (good for testing)
Nothing is ever applied to automatically.
"""
from __future__ import annotations

import argparse
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cfg = yaml.safe_load((ROOT / "keywords.yaml").read_text(encoding="utf-8"))
    scorer = Scorer(cfg)
    store = SeenStore(ROOT / "data" / "seen.sqlite")
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(cfg.get("max_age_days", 30)))

    fetched, errors = [], []
    for name, fn in SOURCES.items():
        try:
            jobs = fn(cfg)
            print(f"[{name}] fetched {len(jobs)}")
            fetched += jobs
        except Exception as exc:  # one broken source must not stop the run
            print(f"[{name}] FAILED: {exc}")
            errors.append(name)

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
        if store.is_seen(j["url"]):
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

    day = date.today().isoformat()
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    write_xlsx(kept, out / f"{day}.xlsx")
    write_html(kept, out / f"{day}.html", day, stats)
    write_claude_md(kept, out / f"{day}_for_claude.md", day,
                    int(cfg.get("top_n_for_claude", 15)), int(cfg.get("description_chars_for_claude", 1200)))

    if not args.dry_run:
        store.mark(kept)
    store.close()

    print(" | ".join(f"{k}: {v}" for k, v in stats.items()))
    print(f"Wrote output/{day}.xlsx, output/{day}.html, output/{day}_for_claude.md")

    if not args.no_open and not os.environ.get("CI"):
        webbrowser.open((out / f"{day}.html").as_uri())
    return 1 if len(errors) == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
