# 13f — Common Problems

Handbook of problems hit on this project. Claude-managed. Every entry logs the symptom, what was tried, the solve (if any), and status.

Format for each entry:

## <Short title of the problem> (YYYY-MM-DD)

**Status:** Open | Resolved
**Symptom:** what the user saw / how it manifested (concrete: error messages, unexpected values, wrong counts, etc.)
**Root cause:** why it happened (best current understanding — mark as "suspected" if not confirmed)
**What was tried:** enumerate the attempts, including the ones that didn't work — this is the audit trail
**Solve:** what actually resolved it (file paths + line numbers if relevant). If Open, write "TBD" and note next step.
**Prevention:** how to avoid recurrence (optional)

---

## First real run: scraper had never worked end-to-end (2026-07-13)

**Status:** Resolved
**Symptom:** First-ever real run (`python scraper.py --force`) produced zero results: every fund logged "No 13F-HR filing found" and the output CSV was empty. After partial fixes, later runs showed "XML parse error: unbound prefix" for most funds, "Could not locate infotable XML" for others, and finally dollar values 1000× too large (Apple at $82 trillion).
**Root cause:** Four independent bugs plus bad config — the code had passed its (mocked) test suite but never run against real EDGAR:
1. `edgar_client.get_latest_13f` read `periodOfReport` from EDGAR's submissions JSON; the real key is `reportDate`. `zip()` against the resulting empty list silently yielded nothing, so no filing was ever found for any fund.
2. The filing-index URL used `{accession}-index.json`, which 404s; EDGAR serves the directory listing at `index.json` inside the filing dir. Cost ~30s of retries per fund before the HTML fallback.
3. `parser._strip_namespaces` stripped `xmlns` declarations from raw XML text but left `ns1:`-prefixed tags behind → ElementTree "unbound prefix" for every filer that uses prefixes (most of them).
4. `parser.parse_infotable` multiplied `value` by 1000 per the pre-2023 13F schema; the SEC switched to full dollars in 2023.
5. Config: 10 of 20 CIKs in `funds.json` were wrong entities (defunct filers or non-13F affiliates — Millennium, D.E. Shaw, Two Sigma, Coatue, Baupost, Soroban, Elliott, Third Point, ValueAct, Appaloosa).
**What was tried:** Ran with `--force` → all funds empty → curled Berkshire's submissions JSON and diffed the real keys against the code (found `reportDate`). Re-ran → found filings but 404s on index JSON → curled the filing dir to find `index.json` works. Re-ran → unbound-prefix parse errors (Appaloosa parsed fine — no prefixes — which confirmed the namespace diagnosis); "could not locate infotable" for RenTech/Viking/Berkshire → listed their filing dirs, saw arbitrary filenames (`MSFS13F033126.XML`, `53405.xml`). Values then 1000× off → checked against known Berkshire/Apple position size.
**Solve:**
- `edgar_client.py:66` — `periodOfReport` → `reportDate`
- `edgar_client.py:100` — index URL → `.../{accession_nodash}/index.json`
- `edgar_client.py:111` — infotable = any `.xml` that isn't `primary_doc.xml` (prefer names containing "infotable")
- `parser.py:44` — parse raw XML first, strip `{ns}` from tags after parsing; regex-stripping is now only a fallback
- `parser.py:60` — dropped the ×1000
- `funds.json` — 10 CIKs corrected, each verified against EDGAR company search + a live Q1 2026 13F-HR filing
- `test_scraper.py` — fixtures updated to the full-dollar schema
Verified: full run parses all 20 funds (~39k positions → 8,171 unique CUSIPs) in ~15s; all 9 tests pass.
**Prevention:** Don't trust LLM-generated CIKs — verify against EDGAR company search (`browse-edgar?action=getcompany&company=<name>&type=13F-HR`) and confirm a recent filing exists. When code that calls a real API only has mocked tests, smoke-test one live request before assuming the schema.

---

## Q1 2026 dataset silently contained Greenlight's December 2023 portfolio (2026-07-14)

**Status:** Resolved
**Symptom:** While backfilling Q4 2025 for the deltas feature, Greenlight Capital (CIK 1079114) returned "No 13F-HR filing found" — yet the Q1 2026 run had happily "parsed 116 positions" from the same CIK the day before.
**Root cause:** Greenlight stopped filing under CIK 1079114 after 2023-12-31 (the firm now files as **DME Capital Management, LP**, CIK 1489933). `get_latest_13f` returns whatever the newest filing is, regardless of age, so the "Q1 2026" aggregate silently included a portfolio snapshot from December 2023. Nothing flagged the mismatch — the run labels output by the *most common* period across funds and included every fund's positions regardless of its own period.
**What was tried:** Checked CIK 1079114's submissions JSON directly — last 13F-HR was 2023-12-31, confirming a dead CIK rather than a fetch bug. EDGAR company search for "Greenlight" only returned the dead CIK; searching "DME Capital" found the successor entity with a current Q1 2026 filing.
**Solve:**
- `funds.json` — Greenlight Capital Inc (1079114) → DME Capital Management LP (1489933)
- `scraper.py:run` — funds whose filing period differs from the majority period are now excluded with an "Excluding <fund> — filed for X, not Y" warning, so a stale CIK can degrade coverage but never pollute the data
- Rebuilt both quarters; verified DME contributes Q1 2026 positions and no fund is excluded
**Prevention:** Funds don't just have wrong CIKs — they *migrate* CIKs over time (restructures, renames). Watch scraper logs for the "Excluding" warning each quarter; it's the signal that a fund in `funds.json` needs its CIK re-verified.

---
