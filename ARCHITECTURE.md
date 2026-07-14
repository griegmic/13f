# 13f — Architecture

Codebase map. Claude-maintained. Read this before modifying code so you don't end up editing the wrong function, missing existing logic, or breaking a coupling. Last updated: 2026-07-13.

## Entry point

`python scraper.py` — the only entry point. Flags:
- no flags: only runs if today is inside a 13F run window (deadline + 2 to + 5 days)
- `--force`: run regardless of date
- `--test-fund`: fetch and print Bridgewater's latest filing only (smoke test)

## Active path

1. `scraper.py` — parses args, loads `funds.json`, orchestrates everything
2. `scheduler.py` — decides whether today is within the run window after a 13F deadline (deadlines hard-coded for 2026 in `DEADLINES_2026`, helper computes future years)
3. `edgar_client.py` — fetches each fund's latest 13F-HR from SEC EDGAR (submissions JSON → filing index → infotable XML)
4. `parser.py` — strips XML namespaces, parses infotable XML into position dicts
5. `aggregate.py` — rolls up positions across funds by CUSIP, writes sorted CSV/JSON to `output/` (creates the dir itself)

## Alternate paths / dead code / insurance

None yet — every module is on the active path. `test_scraper.py` is the test suite, not dead code.

## Key data flow

`funds.json` (20 curated funds with CIKs) → EDGAR submissions API per CIK → latest 13F-HR accession → `infotable.xml` → parsed positions → aggregated per-CUSIP summary → `output/holdings_YYYYQQ.csv` (+ optional JSON), sorted descending by `total_market_value_usd`.

## External couplings

- **SEC EDGAR** (`data.sec.gov` + `www.sec.gov/Archives`) — the only external system. Rate limit 10 req/s; client sleeps 0.11s between calls. `USER_AGENT` in `edgar_client.py` identifies the scraper with griegmic@gmail.com per SEC policy — required, requests without it get blocked.
- No credentials, no Google APIs, no browser automation.

## Known-important patterns

- EDGAR's submissions JSON calls the period-of-report field `reportDate` (not `periodOfReport`); the filing directory listing lives at `.../{accession-no-dashes}/index.json`.
- Filers name their infotable XML arbitrarily (`MSFS13F033126.XML`, `53405.xml`); `edgar_client.get_infotable_url` picks any `.xml` that isn't `primary_doc.xml`, preferring names containing "infotable".
- `parser.py` parses XML with namespaces intact, then strips `{ns}` from tags in the parsed tree; regex-stripping raw text is only a fallback (stripping declarations while leaving `ns1:` prefixes breaks the parse).
- The 13F `value` field is **full USD** since the SEC's 2023 schema change (was thousands before) — do not multiply by 1000.
- `funds.json` CIKs must be the actual 13F-filing entity — big funds have multiple/defunct CIKs. Verify new entries via EDGAR company search filtered to type 13F-HR, and confirm a recent filing exists.
- 13F deadlines are 45 days after quarter end; `scheduler.py` hard-codes 2026 dates and the run window is `[deadline + 2, deadline + 5]` to catch late filers.
- `aggregate.py` keys everything on CUSIP, not ticker — 13F filings don't contain tickers.
- See `Common-Problems.md` (2026-07-13 entry) for the debugging history behind these notes.
