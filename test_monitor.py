"""
Unit tests — no network access required.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import holdings as h_mod
from db import StateDB
from edgar import Filing


class TestFallbackHoldings(unittest.TestCase):
    def test_fallback_returns_holdings(self):
        result = h_mod.fetch(use_fallback=True)
        self.assertGreater(len(result), 0)

    def test_fallback_tickers_are_strings(self):
        result = h_mod.fetch(use_fallback=True)
        for hold in result:
            self.assertIsInstance(hold.ticker, str)
            self.assertTrue(hold.ticker.isupper())

    def test_known_chip_tickers_present(self):
        result = h_mod.fetch(use_fallback=True)
        tickers = {h.ticker for h in result}
        # A few well-known chip companies should be in the fallback list
        for expected in ("NVDA", "AMD", "AVGO"):
            self.assertIn(expected, tickers, f"Expected {expected} in fallback holdings")


class TestStateDB(unittest.TestCase):
    def _make_filing(self, acc="0001234-24-000001", ticker="NVDA", form="10-Q",
                     filed="2024-11-14", period="2024-09-30"):
        return Filing(
            ticker=ticker,
            company_name="NVIDIA Corp",
            cik="0001045810",
            form=form,
            filed=filed,
            period=period,
            accession=acc,
            url=f"https://www.sec.gov/Archives/edgar/data/1045810/{acc}-index.htm",
        )

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db_path = Path(self._tmp) / "test.db"
        self.db = StateDB(self._db_path)

    def tearDown(self):
        self.db.close()

    def test_new_filing_not_seen_initially(self):
        f = self._make_filing()
        self.assertFalse(self.db.is_seen(f.accession))

    def test_mark_seen_persists(self):
        f = self._make_filing()
        self.db.mark_seen(f)
        self.assertTrue(self.db.is_seen(f.accession))

    def test_new_filings_filters_correctly(self):
        f1 = self._make_filing(acc="AAA-24-001", ticker="NVDA")
        f2 = self._make_filing(acc="BBB-24-002", ticker="AMD")
        # Pre-mark f1 as seen
        self.db.mark_seen(f1)

        new = self.db.new_filings([f1, f2])
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0].accession, "BBB-24-002")

    def test_new_filings_marks_returned_as_seen(self):
        f = self._make_filing(acc="CCC-24-003")
        self.db.new_filings([f])
        self.assertTrue(self.db.is_seen("CCC-24-003"))

    def test_duplicate_mark_does_not_raise(self):
        f = self._make_filing()
        self.db.mark_seen(f)
        self.db.mark_seen(f)  # should be idempotent

    def test_save_and_load_holdings(self):
        from holdings import Holding
        sample = [Holding("NVDA", "NVIDIA", 12.5), Holding("AMD", "AMD Inc", 8.0)]
        self.db.save_holdings(sample)
        rows = self.db.load_holdings()
        tickers = {row["ticker"] for row in rows}
        self.assertIn("NVDA", tickers)
        self.assertIn("AMD", tickers)

    def test_all_seen_returns_rows(self):
        f = self._make_filing()
        self.db.mark_seen(f)
        rows = self.db.all_seen()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "NVDA")


if __name__ == "__main__":
    unittest.main()
