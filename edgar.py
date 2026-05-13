"""
SEC EDGAR integration.

Uses two public, unauthenticated EDGAR REST endpoints:
  - https://www.sec.gov/files/company_tickers.json   → ticker → CIK mapping
  - https://data.sec.gov/submissions/CIK{cik}.json   → company filings index

Quarterly filings tracked: 10-Q (quarterly report) and 10-K (annual report).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import requests

logger = logging.getLogger(__name__)

QUARTERLY_FORMS = {"10-Q", "10-K"}

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# EDGAR policy requires: "Company Name email@domain.com" — no angle brackets,
# no parentheses, just name + space + email.
_HEADERS = {
    "User-Agent": "chps-monitor contact@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}

# Polite delay between requests to avoid hammering EDGAR.
_REQUEST_DELAY = 0.15  # seconds


@dataclass
class Filing:
    ticker: str
    company_name: str
    cik: str
    form: str          # e.g. "10-Q"
    filed: str         # ISO date, e.g. "2024-11-14"
    period: str        # period of report, e.g. "2024-09-30"
    accession: str     # accession number, e.g. "0001234567-24-000001"
    url: str           # link to filing index on EDGAR

    def __str__(self) -> str:
        return (
            f"{self.ticker:<6}  {self.form:<5}  filed={self.filed}  "
            f"period={self.period}  {self.url}"
        )


@lru_cache(maxsize=1)
def _load_ticker_map() -> dict[str, str]:
    """Return {TICKER: zero-padded-CIK} for all companies on EDGAR."""
    resp = _get(_TICKERS_URL)
    raw = resp.json()
    # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    mapping: dict[str, str] = {}
    for entry in raw.values():
        ticker = str(entry.get("ticker", "")).upper().strip()
        cik = str(entry.get("cik_str", "")).zfill(10)
        if ticker:
            mapping[ticker] = cik
    return mapping


def cik_for_ticker(ticker: str) -> Optional[str]:
    """Return the 10-digit padded CIK for a ticker, or None if not found."""
    return _load_ticker_map().get(ticker.upper())


def recent_filings(ticker: str, max_filings: int = 10) -> list[Filing]:
    """Return the most recent 10-Q / 10-K filings for the given ticker."""
    cik = cik_for_ticker(ticker)
    if cik is None:
        logger.warning("No CIK found for ticker %s; skipping.", ticker)
        return []

    url = _SUBMISSIONS_URL.format(cik=cik)
    try:
        resp = _get(url)
    except Exception as exc:
        logger.error("Failed to fetch submissions for %s (CIK %s): %s", ticker, cik, exc)
        return []

    data = resp.json()
    company_name = data.get("name", ticker)
    filings_data = data.get("filings", {}).get("recent", {})

    forms = filings_data.get("form", [])
    filed_dates = filings_data.get("filingDate", [])
    periods = filings_data.get("reportDate", [])
    accessions = filings_data.get("accessionNumber", [])

    results: list[Filing] = []
    for form, filed, period, acc in zip(forms, filed_dates, periods, accessions):
        if form not in QUARTERLY_FORMS:
            continue
        acc_clean = acc.replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/"
            f"{acc}-index.htm"
        )
        results.append(
            Filing(
                ticker=ticker.upper(),
                company_name=company_name,
                cik=cik,
                form=form,
                filed=filed,
                period=period,
                accession=acc,
                url=filing_url,
            )
        )
        if len(results) >= max_filings:
            break

    return results


def fetch_all_filings(tickers: list[str], max_per_ticker: int = 8) -> list[Filing]:
    """Fetch recent quarterly filings for a list of tickers with polite pacing."""
    all_filings: list[Filing] = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(_REQUEST_DELAY)
        filings = recent_filings(ticker, max_filings=max_per_ticker)
        all_filings.extend(filings)
        logger.debug("  %s: %d filing(s) found", ticker, len(filings))
    return all_filings


def _get(url: str, timeout: int = 15) -> requests.Response:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Cannot reach EDGAR ({url}). Check your network connection.\n"
            f"  Detail: {exc}"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"EDGAR request timed out: {url}") from exc
    if resp.status_code == 403:
        raise RuntimeError(
            "EDGAR returned 403 Forbidden. Per SEC policy, requests must include a\n"
            "  User-Agent of the form 'Company Name email@domain.com'.\n"
            f"  Current User-Agent: {_HEADERS['User-Agent']}\n"
            "  Edit _HEADERS['User-Agent'] in edgar.py with your contact details."
        )
    resp.raise_for_status()
    return resp
