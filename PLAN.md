# 13F Hedge Fund Scraper — Project Plan

## Goal

Build a Python scraper that pulls 13F-HR filings from SEC EDGAR for a curated list of top hedge funds, aggregates positions across all funds, and outputs a sorted list of securities by total dollar value invested. Runs automatically after each quarterly 13F deadline.

## Output

A CSV (and optional JSON) with columns:

- `issuer_name`
- `cusip`
- `total_market_value_usd` (summed across all funds)
- `num_funds_holding`
- `total_shares`

Sorted descending by `total_market_value_usd`.

## 13F Filing Schedule

13Fs are due 45 days after each calendar quarter ends. 2026 deadlines:

- Q4 2025 holdings: **February 17, 2026**
- Q1 2026 holdings: **May 15, 2026**
- Q2 2026 holdings: **August 14, 2026**
- Q3 2026 holdings: **November 16, 2026**

The scraper should run ~2-3 days after each deadline to catch late filers.

-----

## Project Structure

```
13f-scraper/
├── funds.json              # CIK list + fund names (editable config)
├── scraper.py              # Main entry point
├── edgar_client.py         # EDGAR API fetching + rate limiting
├── parser.py               # 13F XML infotable parsing
├── aggregate.py            # Cross-fund roll-up logic
├── scheduler.py            # Deadline-based run trigger
├── output/                 # Per-run CSVs (gitignored)
│   └── holdings_YYYYQQ.csv
├── requirements.txt
└── README.md
```

-----

## Phase 1: Target Fund List (`funds.json`)

Hardcode top hedge funds with their CIK numbers. Starter list (CIKs to be looked up via EDGAR's company search):

- Bridgewater Associates
- Citadel Advisors
- Millennium Management
- D.E. Shaw & Co.
- Renaissance Technologies
- Two Sigma Investments
- Point72 Asset Management
- Viking Global Investors
- Tiger Global Management
- Coatue Management
- Pershing Square Capital
- Appaloosa Management
- Baupost Group
- Lone Pine Capital
- Soroban Capital Partners
- Elliott Investment Management
- Third Point LLC
- ValueAct Capital
- Berkshire Hathaway (technically not a hedge fund but commonly tracked)
- Greenlight Capital

Format:

```json
{
  "funds": [
    { "name": "Bridgewater Associates", "cik": "0001350694" },
    { "name": "Citadel Advisors LLC", "cik": "0001423053" }
  ]
}
```

**Lookup tip:** CIKs can be found via `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=<NAME>&type=13F-HR&dateb=&owner=include&count=40`

-----

## Phase 2: EDGAR Client (`edgar_client.py`)

### Endpoints (no auth required)

- **Fund submission history:** `https://data.sec.gov/submissions/CIK{cik_padded_to_10}.json`
- **Filing index:** `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/`
- **InfoTable XML:** Linked from filing index, typically named `infotable.xml` or `form13fInfoTable.xml`

### Requirements

- **User-Agent header required:** `User-Agent: Your Name your@email.com` — SEC blocks requests without this
- **Rate limit:** Max 10 requests/second — implement `time.sleep(0.1)` between calls
- Use `requests` library with a session for connection reuse
- Retry logic with exponential backoff for transient failures

### Functions

- `get_latest_13f(cik) -> dict` — returns accession number, filing date, period of report
- `get_infotable_url(cik, accession) -> str` — locates the actual XML data file in the filing index
- `fetch_infotable_xml(url) -> bytes`

-----

## Phase 3: Parser (`parser.py`)

Parse the 13F `infotable.xml` schema. Each `<infoTable>` element contains:

- `<nameOfIssuer>` — company name (string, sometimes ALL CAPS, varies by filer)
- `<titleOfClass>` — e.g., "COM", "CLASS A"
- `<cusip>` — 9-character security identifier (best for deduplication)
- `<value>` — market value in thousands USD (multiply by 1000)
- `<shrsOrPrnAmt>` → `<sshPrnamt>` — share count
- `<shrsOrPrnAmt>` → `<sshPrnamtType>` — usually "SH"

Use `lxml` or stdlib `xml.etree.ElementTree`. Note: 13F XML uses a namespace — handle accordingly.

Output per fund: `list[dict]` with fields above.

-----

## Phase 4: Aggregator (`aggregate.py`)

- Group all positions across all funds by `cusip` (more reliable than name)
- Use most common spelling of `nameOfIssuer` per CUSIP for display
- Sum `value` (in dollars) and `sshPrnamt` per CUSIP
- Count distinct funds holding each CUSIP
- Sort descending by total value
- Write to CSV in `output/holdings_YYYYQQ.csv`

### Optional enhancements

- Delta report vs. prior quarter (new positions, exits, % change in size)
- Top 50 / top 100 summary file
- JSON output alongside CSV for downstream tooling

-----

## Phase 5: Scheduler (`scheduler.py`)

Two options — pick one based on deployment preference:

### Option A: Cron / launchd

```cron
# Runs at 9am ET on 19 Feb, 18 May, 17 Aug, 19 Nov (3 days after deadline)
0 9 19 2 * /usr/bin/python3 /path/to/scraper.py
0 9 18 5 * /usr/bin/python3 /path/to/scraper.py
0 9 17 8 * /usr/bin/python3 /path/to/scraper.py
0 9 19 11 * /usr/bin/python3 /path/to/scraper.py
```

### Option B: GitHub Actions

`.github/workflows/run-13f.yml` with `on.schedule` cron triggers + manual `workflow_dispatch` for ad-hoc runs. Commits the output CSV back to the repo or uploads as a workflow artifact.

### Option C: Daily check

Runs daily and exits unless today is within 3 days after a 13F deadline. Simplest to deploy but wastes a tiny bit of CPU.

-----

## Implementation Order

1. Build `edgar_client.py` — verify you can fetch one fund's filing history
1. Build `parser.py` — verify you can parse one infotable XML correctly
1. Build `aggregate.py` — run end-to-end on 2-3 funds, validate CSV output
1. Populate full `funds.json` with all 20 CIKs
1. Add `scheduler.py` and choose deployment method
1. Add logging, error handling, retry logic
1. Add delta-vs-prior-quarter reporting (optional)

-----

## Dependencies

```
requests>=2.31
lxml>=4.9
python-dateutil>=2.8
```

-----

## Edge Cases to Handle

- **Amendments (13F-HR/A):** A fund may file an amendment after the original. Always use the most recent filing for the target quarter.
- **Missing filings:** Some funds skip quarters or file late — log and continue, don't crash.
- **CUSIP collisions:** Rare but possible across share classes. Group by `(cusip, titleOfClass)` if needed.
- **Confidential treatment:** Some positions are filed under confidential treatment and won't appear. Document this limitation.
- **Multiple infotable files:** Large funds split into multiple XML files. Iterate the filing index to find them all.
- **Wrong filing types:** Filter strictly for `13F-HR` (and `13F-HR/A` for amendments) — ignore `13F-NT` (notice filings, no holdings data).

-----

## Kickoff Prompt for Claude Code

> Read PLAN.md and start with Phase 1 and 2. Build `edgar_client.py` first and write a quick test that fetches Bridgewater's most recent 13F-HR filing accession number and prints it. Once that works, move to the parser. Use `requests`, `lxml`, and stdlib only.
