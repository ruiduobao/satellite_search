"""Scrape the SatNOGS DB satellite catalog (https://db.satnogs.org).

The SatNOGS DB tracks every satellite (mostly amateur / small / university
cubesats) that has been observed by the SatNOGS ground station network. The
public REST API is at ``https://db.satnogs.org/api/satellites/`` and returns
JSON with pagination. The default page size is 100 and the API exposes
``status`` (``alive`` / ``dead`` / ``re-entered`` / ``future`` / ``unknown``),
``norad_cat_id``, ``launched``, ``deployed``, ``operator``, ``countries``
(comma-separated ISO codes), ``website``, and ``citation`` (a long blob of
URLs separated by spaces — useful as a "see also" cross-reference).

Note: the SatNOGS API ignores ``page_size`` for the ``status``-filtered
endpoints (it always returns the full filtered set in one call, capped at
~3,000 records). We therefore make one or two requests per status and
paginate only for the unfiltered query.

This script

1. Pulls ``status='alive'`` and ``status='re-entered'`` subsets (the two
   most useful ones) and writes ``satnogs_alive.jsonl`` /
   ``satnogs_reentered.jsonl``. Optionally also pulls the unfiltered set
   (which is paginated) into ``satnogs_all.jsonl``.

2. Retries 3 times with exponential backoff on transient errors.

We bypass the global 7897 proxy by setting ``requests.trust_env = False``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

requests.trust_env = False

API_URL = "https://db.satnogs.org/api/satellites/"
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA_DIR = os.path.join(SKILL_ROOT, "data")
ALL_JSONL = os.path.join(DATA_DIR, "satnogs_all.jsonl")
ALIVE_JSONL = os.path.join(DATA_DIR, "satnogs_alive.jsonl")
REENTERED_JSONL = os.path.join(DATA_DIR, "satnogs_reentered.jsonl")

USER_AGENT = "satellite_search/0.4 (+https://github.com/ruiduobao/satellite_search)"
PAGE_SIZE = 100
MAX_PAGES = 60


def fetch(params: Dict[str, Any], retries: int = 3) -> List[Dict[str, Any]]:
    """Fetch one or more pages of the SatNOGS API and return the merged list.

    The API behaviour: a status-filtered query returns the full filtered
    set in a single call (capped at ~3000 records). An unfiltered query
    paginates with ``page`` and ``page_size``.
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(API_URL, params={**params, "format": "json"},
                              headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                raise ValueError(f"Unexpected response type: {type(data)}")
            return data
        except (requests.RequestException, ValueError) as e:
            last_err = e
            wait = 2 ** attempt
            print(f"[satnogs] request attempt {attempt} failed: {e}; retry in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {params}: {last_err}")


def fetch_unfiltered() -> List[Dict[str, Any]]:
    """Paginate the unfiltered API. ~3,000 records across ~30 pages."""
    all_records: List[Dict[str, Any]] = []
    page = 1
    while page <= MAX_PAGES:
        records = fetch({"page": page, "page_size": PAGE_SIZE})
        if not records:
            break
        all_records.extend(records)
        if len(records) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.5)  # be polite
    return all_records


def write_jsonl(records: List[Dict[str, Any]], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Scrape the SatNOGS DB API")
    p.add_argument("--quick", action="store_true",
                   help="Only fetch status=alive subset (fastest, default)")
    p.add_argument("--all", dest="fetch_all", action="store_true",
                   help="Also paginate the unfiltered set into satnogs_all.jsonl")
    args = p.parse_args()

    print("[satnogs] fetching status=alive ...", file=sys.stderr)
    t0 = time.time()
    alive = fetch({"status": "alive", "page_size": 500})
    print(f"[satnogs] alive: {len(alive):,} in {time.time()-t0:.1f}s", file=sys.stderr)
    write_jsonl(alive, ALIVE_JSONL)

    if not args.quick:
        print("[satnogs] fetching status=re-entered ...", file=sys.stderr)
        t0 = time.time()
        reentered = fetch({"status": "re-entered", "page_size": 500})
        print(f"[satnogs] re-entered: {len(reentered):,} in {time.time()-t0:.1f}s",
              file=sys.stderr)
        write_jsonl(reentered, REENTERED_JSONL)

    if args.fetch_all:
        print("[satnogs] fetching unfiltered (paginated) ...", file=sys.stderr)
        t0 = time.time()
        all_records = fetch_unfiltered()
        # Merge with status-filtered sets to get a complete view
        seen = {(r.get("sat_id") or r.get("norad_cat_id")) for r in all_records}
        for extra in alive:
            if (extra.get("sat_id") or extra.get("norad_cat_id")) not in seen:
                all_records.append(extra)
                seen.add(extra.get("sat_id") or extra.get("norad_cat_id"))
        print(f"[satnogs] total unique: {len(all_records):,} in {time.time()-t0:.1f}s",
              file=sys.stderr)
        write_jsonl(all_records, ALL_JSONL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
