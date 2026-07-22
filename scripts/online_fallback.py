"""For every eoPortal entry that did NOT get a successful detail fetch,
run a web search restricted to eoportal.org and store the top result(s).

This is the "we tried, we failed, here's where to look" fallback — it
doesn't fabricate data, just gives the user a pointer to the most
relevant non-eoPortal source (or a confirmation that eoPortal really
doesn't have a page for this slug).

Output: ``<data_dir>/web_search_results.jsonl`` — one record per slug::

    {"query": "...", "engine": "...", "results": [{title,url,snippet}, ...],
     "checked_at": "ISO timestamp"}

Usage
-----
    python scripts/online_fallback.py
    python scripts/online_fallback.py --only-slug <slug> [--only-slug ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import local_index, online_search  # type: ignore  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Web-search fallback for eoPortal entries that couldn't be fetched.",
    )
    p.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "data"))
    p.add_argument("--only-slug", action="append", default=[],
                   help="Only run for these slugs (repeatable)")
    p.add_argument("--num-results", type=int, default=5)
    p.add_argument("--sleep", type=float, default=0.0,
                   help="Sleep between searches (seconds).")
    p.add_argument("--include-fetched", action="store_true",
                   help="Re-search even for entries that already have a detail record.")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    out_path = os.path.join(args.data_dir, "web_search_results.jsonl")

    # Load eoPortal catalogue
    eoportal = local_index.all_eoportal()
    if args.only_slug:
        wanted = set(args.only_slug)
        eoportal = [r for r in eoportal if r.get("slug") in wanted]
    if not args.include_fetched:
        eoportal = [r for r in eoportal if not r.get("detail")]
    if args.limit:
        eoportal = eoportal[:args.limit]

    # Load existing results to skip already-searched
    done: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("query"):
                        done[rec["query"]] = rec
        except Exception:
            pass

    if not args.quiet:
        print(f"Web-search fallback for {len(eoportal)} eoPortal slugs (skipping {len(done)} already done)...")

    results: List[Dict[str, Any]] = list(done.values())
    for i, rec in enumerate(eoportal, 1):
        slug = rec.get("slug")
        name = rec.get("name") or slug
        if not slug:
            continue
        if slug in done and not args.only_slug:
            continue
        # Build a query that's a little smarter than just the slug
        q = f"{name} {slug}".strip()
        t0 = time.time()
        try:
            res = online_search.search_satellite_online(q, site="eoportal.org",
                                                       num_results=args.num_results)
        except Exception as e:
            res = None
        elapsed = time.time() - t0
        out: Dict[str, Any] = {
            "query": slug,
            "name": name,
            "engine": (res or {}).get("engine"),
            "results": (res or {}).get("results") or [],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": round(elapsed, 1),
        }
        # Mark success
        if any("eoportal.org" in (r.get("url") or "") for r in out["results"]):
            out["hint"] = "Found eoPortal URLs in search results"
        results.append(out)
        if not args.quiet:
            n_results = len(out["results"])
            has_eo = any("eoportal.org" in (r.get("url") or "") for r in out["results"])
            print(f"  [{i:4d}/{len(eoportal)}] {slug:50s} -> {n_results:2d} results  "
                  f"{'EO!' if has_eo else '   '}  ({elapsed:4.1f}s)",
                  flush=True)
        # Persist after every 10
        if i % 10 == 0 or i == len(eoportal):
            with open(out_path, "w", encoding="utf-8") as f:
                for r in results:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if args.sleep:
            time.sleep(args.sleep)

    # Final write
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if not args.quiet:
        n_with_eo = sum(
            1 for r in results
            if any("eoportal.org" in (x.get("url") or "") for x in r.get("results") or [])
        )
        print(f"\nWrote {len(results)} records -> {out_path}")
        print(f"  with eoPortal URLs found: {n_with_eo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
