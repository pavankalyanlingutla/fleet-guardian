"""
db.py

SQLite persistence for closed-loop automation run history.
Kept deliberately simple (stdlib sqlite3, no ORM) since the JD calls
out SQLite/MySQL directly and this is meant to be readable end to end.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    phase TEXT NOT NULL,          -- detect | analyze | remediate | validate
    detail TEXT NOT NULL,
    healthy INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""


class RunStore:
    def __init__(self, db_path: str = "automation_history.db"):
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def start_run(self) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (started_at) VALUES (?)",
                (datetime.now(timezone.utc).isoformat(),),
            )
            return cur.lastrowid

    def finish_run(self, run_id: int):
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = ? WHERE run_id = ?",
                (datetime.now(timezone.utc).isoformat(), run_id),
            )

    def log_event(self, run_id: int, device_id: str, phase: str, detail: str, healthy: bool | None = None):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO run_events (run_id, device_id, phase, detail, healthy, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    device_id,
                    phase,
                    detail,
                    None if healthy is None else int(healthy),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_history(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY run_id DESC LIMIT ?", (limit,)
            ).fetchall()
            history = []
            for row in rows:
                events = conn.execute(
                    "SELECT * FROM run_events WHERE run_id = ? ORDER BY id ASC",
                    (row["run_id"],),
                ).fetchall()
                history.append(
                    {
                        "run_id": row["run_id"],
                        "started_at": row["started_at"],
                        "finished_at": row["finished_at"],
                        "events": [dict(e) for e in events],
                    }
                )
            return history
