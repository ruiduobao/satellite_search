"""One-shot scraper: download the eoPortal satellite list (no detail page
fetches) and save as JSONL.

The list page is server-rendered as a Next.js page; the catalogue lives in
``__NEXT_DATA__`` JSON. No Playwright is needed for the list.

Usage
-----
::

    python scripts/scrape_eoportal.py
    python scripts/scrape_eoportal.py --data-dir ./data

Outputs
-------
* ``<data_dir>/eoportal_satellites.jsonl`` — one record per line
* Updates ``<data_dir>/scrape_report.json``
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import scraper  # type: ignore  # noqa: E402
from core.models import jsonl_dumps  # type: ignore  # noqa: E402


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scrape eoPortal satellite list (no detail pages).")
    p.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "data"),
                   help="Output data directory (default: <repo>/data)")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    os.makedirs(args.data_dir, exist_ok=True)
    out_path = os.path.join(args.data_dir, "eoportal_satellites.jsonl")
    report_path = os.path.join(args.data_dir, "scrape_report.json")

    t0 = time.time()
    if not args.quiet:
        print("Fetching eoPortal list ...")
    try:
        records = scraper.fetch_eoportal_list()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    elapsed = time.time() - t0

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(jsonl_dumps([{**r, "source": "eoportal"} for r in records]))

    report = {"sources": {}}
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception:
            report = {"sources": {}}
    report.setdefault("sources", {})
    report["sources"]["eoportal"] = {
        "count": len(records),
        "elapsed_seconds": round(elapsed, 2),
        "out_path": out_path,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if not args.quiet:
        print(f"OK: {len(records)} eoPortal entries -> {out_path}  ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
