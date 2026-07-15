#!/usr/bin/env python3
"""
Copy quarterly holdings JSON from output/ into docs/data/ and rebuild the
site manifest. Run after each scraper run to update the GitHub Pages site,
then commit docs/.
"""

import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(ROOT, "output")
SITE_DATA_DIR = os.path.join(ROOT, "docs", "data")

_HOLDINGS_RE = re.compile(r"holdings_(\d{4})Q(\d)\.json$")


def main() -> None:
    os.makedirs(SITE_DATA_DIR, exist_ok=True)
    # keep the site's fund list in sync with the scraper config
    shutil.copy2(os.path.join(ROOT, "funds.json"), os.path.join(SITE_DATA_DIR, "funds.json"))
    print("published funds.json")
    quarters = []
    for name in sorted(os.listdir(OUTPUT_DIR)):
        m = _HOLDINGS_RE.match(name)
        if not m:
            continue
        shutil.copy2(os.path.join(OUTPUT_DIR, name), os.path.join(SITE_DATA_DIR, name))
        quarters.append({"label": f"Q{m.group(2)} {m.group(1)}", "file": name,
                         "sort": f"{m.group(1)}Q{m.group(2)}"})
        print(f"published {name}")

    if not quarters:
        raise SystemExit("no holdings_YYYYQQ.json files in output/ — run the scraper first")

    # newest first in the dropdown
    quarters.sort(key=lambda q: q["sort"], reverse=True)
    for q in quarters:
        del q["sort"]
    manifest_path = os.path.join(SITE_DATA_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump({"quarters": quarters}, f, indent=2)
    print(f"wrote manifest with {len(quarters)} quarter(s)")


if __name__ == "__main__":
    main()
