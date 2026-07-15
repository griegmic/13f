# 13F Hedge Fund Scraper

A Python scraper that pulls **13F-HR** filings from SEC EDGAR for a curated list of top hedge funds, aggregates positions across all funds, and outputs a sorted list of securities by total dollar value invested. Designed to run automatically a few days after each quarterly 13F deadline.

See [PLAN.md](./PLAN.md) for the full project plan, phased implementation order, and edge cases.

## Project docs

- [ARCHITECTURE.md](./ARCHITECTURE.md) — codebase map: entry point, active path, data flow, external couplings. Claude-maintained; read before modifying code.
- [Ideas.md](./Ideas.md) — new-feature ideas, enhancements, proactive refactors (things the project doesn't do yet).
- [Common-Problems.md](./Common-Problems.md) — bug-bashing log for problems in previously-working code, written retroactively after fixes.

---

## What it does

- Fetches the most recent `13F-HR` filing for each fund in `funds.json` from SEC EDGAR
- Parses the `infotable.xml` for every filing
- Aggregates positions across all funds by **CUSIP**
- Writes a sorted CSV (and optional JSON) of every security held, ranked by total dollar value across the basket

## Output

`output/holdings_YYYYQQ.csv`, sorted descending by `total_market_value_usd`:

| Column | Description |
|---|---|
| `issuer_name` | Most common spelling of the issuer across filers |
| `cusip` | 9-character security identifier |
| `total_market_value_usd` | Sum of `value` (in dollars) across all funds holding the security |
| `num_funds_holding` | Count of distinct funds holding the CUSIP |
| `total_shares` | Sum of `sshPrnamt` across all funds |

## 13F Filing Schedule (2026)

13Fs are due **45 days after each calendar quarter ends**:

| Quarter | Deadline |
|---|---|
| Q4 2025 holdings | Feb 17, 2026 |
| Q1 2026 holdings | May 15, 2026 |
| Q2 2026 holdings | Aug 14, 2026 |
| Q3 2026 holdings | Nov 16, 2026 |

The scraper should run ~2–3 days after each deadline to catch late filers.

---

## Project layout

```
13f/
├── funds.json              # CIK list + fund names (editable config)
├── scraper.py              # Main entry point
├── edgar_client.py         # EDGAR API fetching + rate limiting
├── parser.py               # 13F XML infotable parsing
├── aggregate.py            # Cross-fund roll-up logic
├── scheduler.py            # Deadline-based run trigger
├── test_scraper.py         # Test suite
├── output/                 # Per-run CSVs (gitignored)
│   └── holdings_YYYYQQ.csv
├── requirements.txt
├── PLAN.md
├── ARCHITECTURE.md
├── Ideas.md
└── Common-Problems.md
```

## Dependencies

```
requests>=2.31
lxml>=4.9
python-dateutil>=2.8
```

## Quick start

```bash
pip install -r requirements.txt
python scraper.py
# → writes output/holdings_2026Q1.csv
```

## Mini site

The results are browsable at **https://griegmic.github.io/13f/** with two tabs:

- **Holdings** — sortable/searchable table of one quarter's aggregate positions.
- **Quarterly Deltas** — how much money moved into or out of each asset vs the prior quarter: Δ value (signed, colored), Δ as a **percentage of total money invested that quarter**, Δ shares, and NEW/EXITED badges for opened/closed positions. Computed in the browser from two quarters' data; needs at least two published quarters. Note: Δ value includes price moves, not just buying/selling — Δ shares isolates actual trading.

To update the site after a scraper run:

```bash
python publish_site.py   # copies output/*.json into docs/data/ + rebuilds manifest
git add docs && git commit -m "Publish Qn data" && git push
```

To backfill a historical quarter (needed for deltas across older periods):

```bash
python scraper.py --period 2025Q4
```

## SEC EDGAR usage rules

- **User-Agent header is required** — SEC blocks requests without one. Format: `Your Name your@email.com`.
- **Rate limit:** max 10 requests/second. The client sleeps `0.1s` between calls.
- No auth / no API key required.

## Status

Core pipeline implemented (EDGAR client → parser → aggregator → scheduler) with a test suite. Moved out of the TrapCore repo into its own repo on 2026-07-13.
