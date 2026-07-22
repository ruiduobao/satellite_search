"""One-shot scraper: download the OSCAR satellite list and save as JSONL.

Usage
-----
::

    python scripts/scrape_oscar.py
    python scripts/scrape_oscar.py --data-dir ./data

Outputs
-------
* ``<data_dir>/oscar_satellites.jsonl``  — one record per line
* ``<data_dir>/scrape_report.json``      — metadata about the run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List

# Make the scripts/ package importable when run directly.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import scraper  # type: ignore  # noqa: E402
from core.models import jsonl_dumps  # type: ignore  # noqa: E402


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scrape OSCAR satellite list to JSONL.")
    p.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "data"),
                   help="Output data directory (default: <repo>/data)")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = p.parse_args(argv)

    os.makedirs(args.data_dir, exist_ok=True)
    out_path = os.path.join(args.data_dir, "oscar_satellites.jsonl")
    report_path = os.path.join(args.data_dir, "scrape_report.json")

    t0 = time.time()
    if not args.quiet:
        print("Fetching OSCAR list XLSX ...")
    try:
        xlsx = scraper.fetch_oscar_list()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    records = scraper.parse_oscar_xlsx(xlsx)
    elapsed = time.time() - t0

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(jsonl_dumps([{**r, "source": "oscar"} for r in records]))

    # Append a run-report entry (do not overwrite other sources' reports)
    report = {
        "sources": {},
    }
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception:
            report = {"sources": {}}
    report.setdefault("sources", {})
    report["sources"]["oscar"] = {
        "count": len(records),
        "elapsed_seconds": round(elapsed, 2),
        "out_path": out_path,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if not args.quiet:
        print(f"OK: {len(records)} OSCAR records -> {out_path}  ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
