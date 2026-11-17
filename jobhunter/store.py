"""SQLite file that remembers which job URLs were already reported."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path


class SeenStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, title TEXT, company TEXT, first_seen TEXT)"
        )

    def is_seen(self, url: str) -> bool:
        return self.conn.execute("SELECT 1 FROM seen WHERE url = ?", (url,)).fetchone() is not None

    def mark(self, jobs: list[dict]) -> None:
        today = date.today().isoformat()
        self.conn.executemany(
            "INSERT OR IGNORE INTO seen (url, title, company, first_seen) VALUES (?, ?, ?, ?)",
            [(j["url"], j["title"], j["company"], today) for j in jobs],
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
