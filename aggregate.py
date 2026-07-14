"""
Aggregate positions across all funds and write output CSV/JSON.
"""

import csv
import json
import logging
import os
from collections import Counter, defaultdict
from typing import List, Optional

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def aggregate(fund_positions: List[dict]) -> List[dict]:
    """Roll up all fund positions into a per-CUSIP summary.

    fund_positions: list of dicts with keys:
        fund_name, issuer_name, cusip, title_of_class, value_usd, shares

    Returns a list of dicts sorted descending by total_market_value_usd.
    """
    value_sum: dict[str, int] = defaultdict(int)
    shares_sum: dict[str, int] = defaultdict(int)
    fund_set: dict[str, set] = defaultdict(set)
    name_counter: dict[str, Counter] = defaultdict(Counter)

    for row in fund_positions:
        key = row["cusip"]
        value_sum[key] += row.get("value_usd", 0)
        shares_sum[key] += row.get("shares", 0)
        fund_set[key].add(row["fund_name"])
        if row.get("issuer_name"):
            name_counter[key][row["issuer_name"]] += 1

    results = []
    for cusip, total_val in value_sum.items():
        most_common_name = name_counter[cusip].most_common(1)[0][0] if name_counter[cusip] else ""
        results.append({
            "issuer_name": most_common_name,
            "cusip": cusip,
            "total_market_value_usd": total_val,
            "num_funds_holding": len(fund_set[cusip]),
            "total_shares": shares_sum[cusip],
        })

    results.sort(key=lambda r: r["total_market_value_usd"], reverse=True)
    return results


def write_csv(results: List[dict], period_label: str) -> str:
    """Write results to output/holdings_<period_label>.csv. Returns the file path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"holdings_{period_label}.csv")
    fieldnames = ["issuer_name", "cusip", "total_market_value_usd", "num_funds_holding", "total_shares"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    logger.info("Wrote %d rows to %s", len(results), path)
    return path


def write_json(results: List[dict], period_label: str) -> str:
    """Write results to output/holdings_<period_label>.json. Returns the file path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"holdings_{period_label}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Wrote JSON to %s", path)
    return path


def period_label(period_of_report: Optional[str]) -> str:
    """Convert '2025-12-31' → '2025Q4', etc."""
    if not period_of_report:
        return "unknown"
    try:
        parts = period_of_report.split("-")
        year = parts[0]
        month = int(parts[1])
        quarter = (month - 1) // 3 + 1
        return f"{year}Q{quarter}"
    except Exception:
        return period_of_report.replace("-", "")
