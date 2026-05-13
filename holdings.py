"""
Fetch holdings for the CHPS ETF.

Primary source: yfinance (scrapes Yahoo Finance fund holdings page).
Fallback: a hardcoded snapshot so the tool still works when the live
fetch fails or returns an incomplete list.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

ETF_TICKER = "CHPS"

# Hardcoded fallback snapshot of CHPS top holdings (tickers only).
# Update this list whenever the ETF rebalances significantly.
_FALLBACK_TICKERS: list[str] = [
    "NVDA",
    "AMD",
    "AVGO",
    "QCOM",
    "INTC",
    "MRVL",
    "MPWR",
    "MCHP",
    "SWKS",
    "QRVO",
    "TXN",
    "ADI",
    "MU",
    "ON",
    "AMAT",
    "KLAC",
    "LRCX",
    "ASML",
    "TSM",
    "WOLF",
]


class Holding(NamedTuple):
    ticker: str
    name: str
    weight: float  # percentage, e.g. 8.5 means 8.5 %


def fetch(use_fallback: bool = False) -> list[Holding]:
    """Return a list of current CHPS ETF holdings.

    Tries yfinance first; falls back to the hardcoded snapshot on any error.
    Pass use_fallback=True to skip the live fetch entirely (useful in tests).
    """
    if not use_fallback:
        try:
            return _fetch_via_yfinance()
        except Exception as exc:
            logger.warning("yfinance fetch failed (%s); using fallback snapshot.", exc)

    return _fallback_holdings()


def _fetch_via_yfinance() -> list[Holding]:
    import yfinance as yf  # import here so the module loads without yfinance installed

    etf = yf.Ticker(ETF_TICKER)

    # yfinance exposes fund holdings on the .funds_data attribute (>=0.2.37)
    # and also as .info["holdings"] on some builds.
    holdings: list[Holding] = []

    try:
        fd = etf.funds_data
        if fd is not None and hasattr(fd, "top_holdings"):
            df = fd.top_holdings
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    ticker = str(row.get("symbol", row.name or "")).strip().upper()
                    name = str(row.get("holdingName", ticker)).strip()
                    weight = float(row.get("holdingPercent", 0.0)) * 100
                    if ticker:
                        holdings.append(Holding(ticker=ticker, name=name, weight=weight))
                if holdings:
                    logger.info("Fetched %d holdings from yfinance funds_data.", len(holdings))
                    return holdings
    except Exception as exc:
        logger.debug("funds_data path failed: %s", exc)

    # Older yfinance path
    info = etf.info or {}
    raw = info.get("holdings", [])
    for item in raw:
        ticker = str(item.get("symbol", "")).strip().upper()
        name = str(item.get("holdingName", ticker)).strip()
        weight = float(item.get("holdingPercent", 0.0)) * 100
        if ticker:
            holdings.append(Holding(ticker=ticker, name=name, weight=weight))

    if not holdings:
        raise ValueError("yfinance returned no holdings for %s" % ETF_TICKER)

    logger.info("Fetched %d holdings via yfinance info.", len(holdings))
    return holdings


def _fallback_holdings() -> list[Holding]:
    logger.info("Using hardcoded fallback holdings (%d tickers).", len(_FALLBACK_TICKERS))
    return [Holding(ticker=t, name=t, weight=0.0) for t in _FALLBACK_TICKERS]
