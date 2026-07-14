#!/usr/bin/env python3
"""
Main entry point for the 13F hedge fund scraper.

Usage:
    python scraper.py                  # only runs near a 13F deadline
    python scraper.py --force          # run regardless of date
    python scraper.py --test-fund      # fetch + print Bridgewater's latest filing only
"""

import argparse
import json
import logging
import os
import sys
from typing import List, Optional

import edgar_client
import parser as p13f
import aggregate as agg
import scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FUNDS_FILE = os.path.join(os.path.dirname(__file__), "funds.json")


def load_funds() -> List[dict]:
    with open(FUNDS_FILE, encoding="utf-8") as f:
        return json.load(f)["funds"]


def scrape_fund(fund: dict) -> tuple[Optional[str], List[dict]]:
    """Fetch and parse the latest 13F for one fund.

    Returns (period_of_report, positions).
    """
    name = fund["name"]
    cik = fund["cik"]
    logger.info("Processing %s (CIK %s)", name, cik)

    filing = edgar_client.get_latest_13f(cik)
    if filing is None:
        logger.warning("No 13F-HR found for %s — skipping.", name)
        return None, []

    logger.info(
        "  Latest filing: %s  period=%s  filed=%s",
        filing["accession_number"],
        filing["period_of_report"],
        filing["filing_date"],
    )

    url = edgar_client.get_infotable_url(cik, filing["accession_number"])
    if url is None:
        logger.warning("Could not locate infotable XML for %s — skipping.", name)
        return filing["period_of_report"], []

    xml_bytes = edgar_client.fetch_infotable_xml(url)
    positions = p13f.parse_infotable(xml_bytes)

    # Tag each position with the fund name
    for pos in positions:
        pos["fund_name"] = name

    logger.info("  Parsed %d positions from %s", len(positions), name)
    return filing["period_of_report"], positions


def run(force: bool = False) -> Optional[str]:
    """Run the full scrape pipeline. Returns the path to the output CSV, or None."""
    if not force:
        ok, deadline = scheduler.should_run()
        if not ok:
            logger.info("Not within a run window. Use --force to override.")
            return None

    funds = load_funds()
    all_positions: List[dict] = []
    periods = []

    for fund in funds:
        try:
            period, positions = scrape_fund(fund)
        except Exception as exc:
            logger.error("Failed to scrape %s: %s", fund["name"], exc)
            continue
        if period:
            periods.append(period)
        all_positions.extend(positions)

    if not all_positions:
        logger.error("No positions collected — aborting.")
        return None

    # Use the most common period_of_report as the label
    from collections import Counter
    label_period = Counter(periods).most_common(1)[0][0] if periods else None
    label = agg.period_label(label_period)
    logger.info("Aggregating %d positions for period %s", len(all_positions), label)

    results = agg.aggregate(all_positions)
    csv_path = agg.write_csv(results, label)
    agg.write_json(results, label)

    logger.info("Done. Top 5 holdings:")
    for row in results[:5]:
        logger.info(
            "  %s (%s): $%,.0f across %d funds",
            row["issuer_name"],
            row["cusip"],
            row["total_market_value_usd"],
            row["num_funds_holding"],
        )

    return csv_path


def test_fund():
    """Quick smoke-test: fetch Bridgewater's latest filing and print the accession number."""
    cik = "0001350694"
    logger.info("=== Smoke test: Bridgewater Associates (CIK %s) ===", cik)
    filing = edgar_client.get_latest_13f(cik)
    if filing is None:
        logger.error("No 13F-HR filing found!")
        sys.exit(1)
    print(f"Accession number : {filing['accession_number']}")
    print(f"Period of report : {filing['period_of_report']}")
    print(f"Filing date      : {filing['filing_date']}")
    print(f"Form type        : {filing['form_type']}")

    url = edgar_client.get_infotable_url(cik, filing["accession_number"])
    print(f"Infotable URL    : {url}")

    if url:
        xml = edgar_client.fetch_infotable_xml(url)
        positions = p13f.parse_infotable(xml)
        print(f"Positions parsed : {len(positions)}")
        if positions:
            print("First position   :", positions[0])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="13F Hedge Fund Scraper")
    parser.add_argument("--force", action="store_true", help="Run regardless of date")
    parser.add_argument("--test-fund", action="store_true", help="Smoke-test one fund")
    args = parser.parse_args()

    if args.test_fund:
        test_fund()
    else:
        out = run(force=args.force)
        if out:
            print(f"Output: {out}")
