"""
Offline tests for parser, aggregator, and scheduler.
Run with: python -m pytest test_scraper.py -v
         or: python test_scraper.py
"""

import sys
import os
import json
import tempfile
from datetime import date
from unittest.mock import patch, MagicMock

# Add the scraper directory to path
sys.path.insert(0, os.path.dirname(__file__))

import parser as p13f
import aggregate as agg
import scheduler

# ---------------------------------------------------------------------------
# Minimal 13F infotable XML sample (realistic structure)
# ---------------------------------------------------------------------------
SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>5000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>28000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>3000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>8500000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>67066G104</cusip>
    <value>2000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>22000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""

SAMPLE_XML_NO_NS = b"""<?xml version="1.0" encoding="UTF-8"?>
<informationTable>
  <infoTable>
    <nameOfIssuer>AMAZON COM INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>023135106</cusip>
    <value>1500000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>12000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Apple Inc</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>800000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>4500000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_parser_with_namespace():
    positions = p13f.parse_infotable(SAMPLE_XML)
    assert len(positions) == 3, f"Expected 3 positions, got {len(positions)}"

    apple = next(p for p in positions if p["cusip"] == "037833100")
    assert apple["issuer_name"] == "APPLE INC"
    assert apple["value_usd"] == 5_000_000_000  # 5000000 * 1000
    assert apple["shares"] == 28_000_000
    assert apple["share_type"] == "SH"

    msft = next(p for p in positions if p["cusip"] == "594918104")
    assert msft["value_usd"] == 3_000_000_000
    print("PASS: test_parser_with_namespace")


def test_parser_without_namespace():
    positions = p13f.parse_infotable(SAMPLE_XML_NO_NS)
    assert len(positions) == 2
    amzn = next(p for p in positions if p["cusip"] == "023135106")
    assert amzn["value_usd"] == 1_500_000_000
    print("PASS: test_parser_without_namespace")


def test_aggregate_sums_across_funds():
    fund1_positions = [
        {"fund_name": "FundA", "issuer_name": "APPLE INC", "cusip": "037833100", "value_usd": 5_000_000_000, "shares": 28_000_000},
        {"fund_name": "FundA", "issuer_name": "MICROSOFT CORP", "cusip": "594918104", "value_usd": 3_000_000_000, "shares": 8_500_000},
    ]
    fund2_positions = [
        {"fund_name": "FundB", "issuer_name": "Apple Inc", "cusip": "037833100", "value_usd": 800_000_000, "shares": 4_500_000},
        {"fund_name": "FundB", "issuer_name": "NVIDIA CORP", "cusip": "67066G104", "value_usd": 2_000_000_000, "shares": 22_000_000},
    ]
    all_positions = fund1_positions + fund2_positions
    results = agg.aggregate(all_positions)

    assert len(results) == 3, f"Expected 3 unique CUSIPs, got {len(results)}"

    # Top holding should be APPLE (5B + 800M = 5.8B)
    assert results[0]["cusip"] == "037833100"
    assert results[0]["total_market_value_usd"] == 5_800_000_000
    assert results[0]["num_funds_holding"] == 2
    assert results[0]["total_shares"] == 32_500_000
    # Most common name is "APPLE INC" (appears once from FundA, once as "Apple Inc" from FundB)
    # Counter picks most common; with a tie it's arbitrary — just check it's non-empty
    assert results[0]["issuer_name"] != ""

    # Sort order: Apple > MSFT (3B) > Nvidia (2B)
    assert results[1]["cusip"] == "594918104"
    assert results[2]["cusip"] == "67066G104"
    print("PASS: test_aggregate_sums_across_funds")


def test_aggregate_writes_csv():
    positions = [
        {"fund_name": "FundA", "issuer_name": "APPLE INC", "cusip": "037833100", "value_usd": 1_000_000, "shares": 5000},
    ]
    results = agg.aggregate(positions)
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(agg, "OUTPUT_DIR", tmpdir):
            path = agg.write_csv(results, "2025Q4")
            assert os.path.exists(path)
            with open(path) as f:
                content = f.read()
            assert "037833100" in content
            assert "APPLE INC" in content
    print("PASS: test_aggregate_writes_csv")


def test_period_label():
    assert agg.period_label("2025-12-31") == "2025Q4"
    assert agg.period_label("2026-03-31") == "2026Q1"
    assert agg.period_label("2026-06-30") == "2026Q2"
    assert agg.period_label("2026-09-30") == "2026Q3"
    print("PASS: test_period_label")


def test_scheduler_within_window():
    # 3 days after Q1 2026 deadline (May 15) = May 18
    ok, deadline = scheduler.should_run(today=date(2026, 5, 18))
    assert ok, "Should run on May 18 (3 days after May 15 deadline)"
    assert deadline == date(2026, 5, 15)
    print("PASS: test_scheduler_within_window")


def test_scheduler_outside_window():
    # 10 days after deadline
    ok, _ = scheduler.should_run(today=date(2026, 5, 25))
    assert not ok, "Should not run 10 days after deadline"
    print("PASS: test_scheduler_outside_window")


def test_scheduler_before_window():
    # 1 day after deadline (window starts at +2)
    ok, _ = scheduler.should_run(today=date(2026, 5, 16))
    assert not ok, "Should not run 1 day after deadline (window starts at +2)"
    print("PASS: test_scheduler_before_window")


def test_funds_json_valid():
    with open(os.path.join(os.path.dirname(__file__), "funds.json")) as f:
        data = json.load(f)
    funds = data["funds"]
    assert len(funds) == 20, f"Expected 20 funds, got {len(funds)}"
    for fund in funds:
        assert "name" in fund and fund["name"]
        assert "cik" in fund and fund["cik"].startswith("0")
    print(f"PASS: test_funds_json_valid ({len(funds)} funds)")


if __name__ == "__main__":
    tests = [
        test_parser_with_namespace,
        test_parser_without_namespace,
        test_aggregate_sums_across_funds,
        test_aggregate_writes_csv,
        test_period_label,
        test_scheduler_within_window,
        test_scheduler_outside_window,
        test_scheduler_before_window,
        test_funds_json_valid,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"FAIL: {t.__name__}: {exc}")
            failed += 1
    if failed:
        print(f"\n{failed} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} tests passed.")
