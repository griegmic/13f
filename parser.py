"""
Parse 13F infotable XML into a list of position dicts.

The 13F schema uses a namespace; we strip it before parsing to keep
selectors simple.
"""

import re
import logging
from typing import List, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# EDGAR 13F namespace prefix (varies by year; strip it uniformly)
_NS_PATTERN = re.compile(r'\s+xmlns[^"]*"[^"]*"')
_TAG_NS_PATTERN = re.compile(r'\{[^}]+\}')


def _strip_namespaces(xml_bytes: bytes) -> bytes:
    text = xml_bytes.decode("utf-8", errors="replace")
    text = _NS_PATTERN.sub("", text)
    return text.encode("utf-8")


def _text(element: ET.Element, tag: str) -> Optional[str]:
    child = element.find(tag)
    if child is None:
        # Try case-insensitive search as a fallback (some filers capitalise differently)
        tag_lower = tag.lower()
        for ch in element:
            if _TAG_NS_PATTERN.sub("", ch.tag).lower() == tag_lower:
                return (ch.text or "").strip() or None
        return None
    return (child.text or "").strip() or None


def parse_infotable(xml_bytes: bytes) -> List[dict]:
    """Parse a 13F infotable XML blob.

    Returns a list of dicts with keys:
        issuer_name, cusip, title_of_class, value_usd, shares, share_type
    """
    cleaned = _strip_namespaces(xml_bytes)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        logger.error("XML parse error: %s", exc)
        return []

    positions = []
    for info in root.iter("infoTable"):
        try:
            issuer = _text(info, "nameOfIssuer") or ""
            cusip = (_text(info, "cusip") or "").upper().strip()
            title = _text(info, "titleOfClass") or ""

            value_raw = _text(info, "value")
            # value field is in thousands USD per the 13F schema
            value_usd = int(value_raw.replace(",", "")) * 1000 if value_raw else 0

            shrs_el = info.find("shrsOrPrnAmt")
            if shrs_el is None:
                shares = 0
                share_type = "SH"
            else:
                shares_raw = _text(shrs_el, "sshPrnamt") or "0"
                shares = int(shares_raw.replace(",", ""))
                share_type = _text(shrs_el, "sshPrnamtType") or "SH"

            if not cusip:
                logger.debug("Skipping row with empty CUSIP: %s", issuer)
                continue

            positions.append({
                "issuer_name": issuer,
                "cusip": cusip,
                "title_of_class": title,
                "value_usd": value_usd,
                "shares": shares,
                "share_type": share_type,
            })
        except Exception as exc:
            logger.warning("Failed to parse infoTable row: %s", exc)
            continue

    return positions
