#!/usr/bin/env python3
"""
CHPS ETF Quarterly Filing Monitor
==================================
Checks SEC EDGAR for new 10-Q / 10-K filings from companies held in the
CHPS ETF and reports any filings not seen in previous runs.

Usage
-----
    python monitor.py check          # check for new filings (default)
    python monitor.py check --all    # re-show all filings, not just new ones
    python monitor.py holdings       # print current CHPS holdings
    python monitor.py history        # show previously seen filings
    python monitor.py --fallback ... # use hardcoded holdings instead of live fetch
    python monitor.py --db PATH ...  # use a custom SQLite database path

Run this on a schedule (e.g. weekly via cron) to get notified of new filings.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import holdings as h_mod
import edgar
import db as db_mod


def cmd_check(args: argparse.Namespace) -> int:
    """Fetch holdings, pull EDGAR filings, report anything new."""
    with db_mod.StateDB(Path(args.db)) as state:
        # 1. Fetch / refresh holdings
        holdings = h_mod.fetch(use_fallback=args.fallback)
        state.save_holdings(holdings)
        tickers = [h.ticker for h in holdings]
        print(f"Monitoring {len(tickers)} CHPS holdings for quarterly filings...\n")

        # 2. Fetch recent filings from EDGAR
        all_filings = edgar.fetch_all_filings(tickers, max_per_ticker=8)

        if args.all:
            # Mark them all seen and print everything
            for f in all_filings:
                state.mark_seen(f)
            display = all_filings
            label = "All filings"
        else:
            # Only show genuinely new ones
            display = state.new_filings(all_filings)
            label = "New filings"

        # 3. Report
        if not display:
            print(f"No {label.lower()} found since last run.")
            return 0

        print(f"{label} ({len(display)}):")
        print("-" * 80)
        for f in sorted(display, key=lambda x: (x.filed, x.ticker), reverse=True):
            print(f"  {f}")
        print()
        return 0


def cmd_holdings(args: argparse.Namespace) -> int:
    """Print current CHPS ETF holdings."""
    with db_mod.StateDB(Path(args.db)) as state:
        holdings = h_mod.fetch(use_fallback=args.fallback)
        state.save_holdings(holdings)

    print(f"CHPS ETF holdings ({len(holdings)}):")
    print(f"  {'Ticker':<8}  {'Weight':>7}  Name")
    print("  " + "-" * 50)
    for hold in sorted(holdings, key=lambda x: x.weight, reverse=True):
        weight_str = f"{hold.weight:.2f}%" if hold.weight else "  n/a "
        print(f"  {hold.ticker:<8}  {weight_str:>7}  {hold.name}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Show all previously seen filings stored in the database."""
    with db_mod.StateDB(Path(args.db)) as state:
        rows = state.all_seen()

    if not rows:
        print("No filings recorded yet. Run 'check' first.")
        return 0

    print(f"Previously seen filings ({len(rows)}):")
    print(f"  {'Ticker':<6}  {'Form':<5}  {'Filed':<12}  {'Period':<12}  Accession")
    print("  " + "-" * 70)
    for row in rows:
        print(
            f"  {row['ticker']:<6}  {row['form']:<5}  {row['filed']:<12}  "
            f"{row['period']:<12}  {row['accession']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Monitor quarterly SEC filings for CHPS ETF holdings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db",
        default=str(db_mod.DEFAULT_DB_PATH),
        metavar="PATH",
        help="Path to SQLite state database (default: %(default)s)",
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Use hardcoded holdings snapshot instead of live yfinance fetch",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    sub = parser.add_subparsers(dest="command")

    check_p = sub.add_parser("check", help="Check for new quarterly filings (default)")
    check_p.add_argument(
        "--all",
        action="store_true",
        help="Show all filings, not just ones new since last run",
    )

    sub.add_parser("holdings", help="Print current CHPS ETF holdings")
    sub.add_parser("history", help="Show all previously seen filings")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    # Default command is 'check'
    if args.command is None:
        args.command = "check"
        args.all = False

    if args.command == "check":
        return cmd_check(args)
    if args.command == "holdings":
        return cmd_holdings(args)
    if args.command == "history":
        return cmd_history(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
