"""
SQLite-backed state store.

Tracks which filings have already been seen so that each run of the monitor
only surfaces genuinely new filings.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edgar import Filing

DEFAULT_DB_PATH = Path.home() / ".chps_monitor" / "state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_filings (
    accession TEXT PRIMARY KEY,
    ticker    TEXT NOT NULL,
    form      TEXT NOT NULL,
    filed     TEXT NOT NULL,
    period    TEXT NOT NULL,
    seen_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS holdings_snapshot (
    ticker      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    weight      REAL NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class StateDB:
    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Filings
    # ------------------------------------------------------------------

    def is_seen(self, accession: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM seen_filings WHERE accession = ?", (accession,)
        )
        return cur.fetchone() is not None

    def mark_seen(self, filing: "Filing") -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO seen_filings (accession, ticker, form, filed, period)
            VALUES (?, ?, ?, ?, ?)
            """,
            (filing.accession, filing.ticker, filing.form, filing.filed, filing.period),
        )
        self._conn.commit()

    def new_filings(self, filings: list["Filing"]) -> list["Filing"]:
        """Filter to filings not yet recorded in the DB, then persist them."""
        fresh = [f for f in filings if not self.is_seen(f.accession)]
        for f in fresh:
            self.mark_seen(f)
        return fresh

    def all_seen(self) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM seen_filings ORDER BY filed DESC, ticker"
        )
        return cur.fetchall()

    # ------------------------------------------------------------------
    # Holdings snapshot
    # ------------------------------------------------------------------

    def save_holdings(self, holdings: list) -> None:
        self._conn.executemany(
            """
            INSERT INTO holdings_snapshot (ticker, name, weight)
            VALUES (?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name = excluded.name,
                weight = excluded.weight,
                updated_at = datetime('now')
            """,
            [(h.ticker, h.name, h.weight) for h in holdings],
        )
        self._conn.commit()

    def load_holdings(self) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM holdings_snapshot ORDER BY weight DESC, ticker"
        )
        return cur.fetchall()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "StateDB":
        return self

    def __exit__(self, *_) -> None:
        self.close()
