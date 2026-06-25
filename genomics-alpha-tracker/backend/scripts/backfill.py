"""Backfill history from day one — build a usable dataset before the first cron.

Usage (from backend/):
    python -m scripts.backfill                 # full universe, all layers
    python -m scripts.backfill --symbol CRSP   # single name
    python -m scripts.backfill --years 3       # deeper price history
    python -m scripts.backfill --score-only    # just recompute Alpha Signal
"""
from __future__ import annotations

import argparse
import logging

from sqlmodel import Session

from app.db import engine, init_db
from app.ingestion.runner import active_symbols, backfill_symbol
from app.scoring.engine import compute_scores
from app.universe.manager import sync_from_yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genomics Alpha Tracker backfill")
    parser.add_argument("--symbol", help="single symbol to backfill")
    parser.add_argument("--years", type=int, default=2, help="years of price history")
    parser.add_argument("--score-only", action="store_true", help="only recompute scores")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        sync_from_yaml(session)

        if not args.score_only:
            symbols = [args.symbol.upper()] if args.symbol else active_symbols(session)
            for i, sym in enumerate(symbols, 1):
                logger.info("[%d/%d] backfilling %s", i, len(symbols), sym)
                result = backfill_symbol(session, sym, years=args.years)
                logger.info("  -> %s", result)

        logger.info("Computing Alpha Signal scores ...")
        snaps = compute_scores(session)
        logger.info("Done. %d score snapshots written.", len(snaps))


if __name__ == "__main__":
    main()
