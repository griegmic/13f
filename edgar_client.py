"""
EDGAR API client for fetching 13F-HR filings.
Rate limit: max 10 req/s — sleeps 0.1s between calls.
"""

import time
import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)

USER_AGENT = "TrapCore 13F Scraper griegmic@gmail.com"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
RATE_LIMIT_SLEEP = 0.11  # slightly over 0.1s to stay safely under 10 req/s

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    return _session


def _get(url: str, retries: int = 4) -> requests.Response:
    session = _get_session()
    delay = 2
    for attempt in range(retries + 1):
        try:
            time.sleep(RATE_LIMIT_SLEEP)
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            logger.warning("Request failed (%s), retrying in %ds: %s", exc, delay, url)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def _pad_cik(cik: str) -> str:
    return cik.lstrip("0").zfill(10)


def get_latest_13f(cik: str) -> Optional[dict]:
    """Return metadata for the most recent 13F-HR or 13F-HR/A filing.

    Returns a dict with keys: accession_number, filing_date, period_of_report, form_type.
    Returns None if no 13F-HR filing is found.
    """
    padded = _pad_cik(cik)
    url = SUBMISSIONS_URL.format(cik=padded)
    logger.debug("Fetching submissions for CIK %s", padded)
    data = _get(url).json()

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    # EDGAR calls the period-of-report field "reportDate" in submissions JSON
    periods = filings.get("reportDate", [])

    # Walk newest-first (EDGAR returns them in reverse-chronological order)
    best: Optional[dict] = None
    for form, accession, date, period in zip(forms, accessions, dates, periods):
        if form in ("13F-HR", "13F-HR/A"):
            entry = {
                "accession_number": accession,
                "filing_date": date,
                "period_of_report": period,
                "form_type": form,
            }
            if best is None:
                best = entry
            else:
                # Prefer the filing with the most-recent period_of_report
                if period > best["period_of_report"]:
                    best = entry
                elif period == best["period_of_report"] and form == "13F-HR/A":
                    # Amendment supersedes original for the same period
                    best = entry

    # EDGAR also paginates older filings into separate JSON files; for our
    # purposes the most recent quarter is always in "recent".
    if best is None:
        logger.warning("No 13F-HR filing found for CIK %s", padded)
    return best


def get_infotable_url(cik: str, accession: str) -> Optional[str]:
    """Find the infotable XML URL inside a filing's index page."""
    padded = _pad_cik(cik)
    accession_nodash = accession.replace("-", "")
    index_url = FILING_INDEX_URL.format(cik=padded.lstrip("0"), accession=accession_nodash)
    # EDGAR serves the directory listing at index.json inside the filing dir
    index_json_url = (
        f"https://www.sec.gov/Archives/edgar/data/{padded.lstrip('0')}"
        f"/{accession_nodash}/index.json"
    )
    logger.debug("Fetching filing index: %s", index_json_url)
    try:
        index_data = _get(index_json_url).json()
    except Exception:
        # Fall back to the HTML index
        return _scrape_infotable_url_from_html(padded.lstrip("0"), accession_nodash)

    # Filers name the infotable arbitrarily (e.g. MSFS13F033126.XML, 53405.xml);
    # the reliable rule is: the XML file that is not primary_doc.xml.
    base = f"https://www.sec.gov/Archives/edgar/data/{padded.lstrip('0')}/{accession_nodash}/"
    xml_items = [
        item["name"]
        for item in index_data.get("directory", {}).get("item", [])
        if item.get("name", "").lower().endswith(".xml")
        and item.get("name", "").lower() != "primary_doc.xml"
    ]
    for name in xml_items:
        if "infotable" in name.lower():
            return base + name
    if xml_items:
        return base + xml_items[0]

    # Some filings use a different naming convention
    return _scrape_infotable_url_from_html(padded.lstrip("0"), accession_nodash)


def _scrape_infotable_url_from_html(cik_no_lead: str, accession_nodash: str) -> Optional[str]:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_no_lead}/{accession_nodash}/"
    logger.debug("Falling back to HTML index: %s", base)
    resp = _get(base)
    for line in resp.text.splitlines():
        lower = line.lower()
        if "infotable" in lower and ".xml" in lower:
            import re
            match = re.search(r'href="([^"]*infotable[^"]*\.xml)"', lower)
            if match:
                href = match.group(1)
                if not href.startswith("http"):
                    href = "https://www.sec.gov" + href
                return href
    return None


def fetch_infotable_xml(url: str) -> bytes:
    """Download the raw infotable XML bytes."""
    logger.debug("Fetching infotable XML: %s", url)
    return _get(url).content
