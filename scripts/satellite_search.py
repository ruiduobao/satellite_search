"""CLI entry point for the satellite_search skill.

Subcommands
-----------
* ``list``    — list all satellites known to the local index
* ``search``  — fuzzy search by name (Chinese + English)
* ``info``    — multi-source merged view of a single satellite
* ``fetch``   — live-fetch a satellite from the source site(s) and append
* ``stats``   — show index statistics
* ``update``  — re-scrape the OSCAR / eoPortal lists into the local index

Output modes
------------
* default          — human-readable text (tables / one-line rows)
* ``--json``       — machine-readable JSON, one object per line / one object
* ``--pretty``     — pretty-printed JSON (one object)
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

from core import local_index, scraper, online_search  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _print_row_table(rows: List[Dict[str, Any]], columns: List[tuple]) -> None:
    """Print a compact table.

    ``columns`` is a list of ``(header, key, fmt)`` tuples. ``fmt`` is one
    of ``"s"`` (string, default) or ``"l"`` (truncate left). Values are
    truncated to fit a 100-char terminal by default.
    """
    width = 100
    # Compute column widths
    widths: List[int] = []
    for header, key, _ in columns:
        max_w = len(header)
        for r in rows:
            v = r.get(key)
            if v is None:
                continue
            s = str(v)
            if len(s) > max_w:
                max_w = len(s)
        widths.append(min(max_w, 40))
    # Header
    line = "  ".join(h.ljust(widths[i]) for i, (h, _, _) in enumerate(columns))
    print(line)
    print("-" * len(line))
    for r in rows:
        cells = []
        for i, (_, key, fmt) in enumerate(columns):
            v = r.get(key)
            if v is None:
                v = ""
            s = str(v)
            w = widths[i]
            if len(s) > w:
                if fmt == "l":
                    s = "..." + s[-w + 3:]
                else:
                    s = s[:w - 1] + "…"
            cells.append(s.ljust(w))
        print("  ".join(cells))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    rows = local_index.list_satellites(source=args.source, limit=args.limit)
    if args.json:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        return 0
    if not rows:
        print("(no satellites in local index; run `update` to scrape)")
        return 0
    cols = [
        ("SOURCE", "source", "s"),
        ("NAME", "name", "l"),
        ("AGENCY", "agency", "l"),
        ("LAUNCH", "launch", "s"),
        ("ORBIT", "orbit", "s"),
        ("STATUS", "status", "s"),
    ]
    _print_row_table(rows, cols)
    print(f"\n{len(rows)} satellites")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    hits = local_index.search(args.keyword, source=args.source, limit=args.limit)
    if args.json:
        for h in hits:
            print(json.dumps(h, ensure_ascii=False))
        return 0
    if not hits:
        print(f"No local matches for {args.keyword!r}.")
        # try online_search as a last resort
        online = online_search.search_satellite_online(args.keyword, num_results=5)
        if online:
            print(f"\n{online['hint']}\n")
            for r in online["results"][:5]:
                print(f"  - {r['title']}\n    {r['url']}\n    {r['snippet'][:120]}")
        return 1
    # human-readable
    print(f"Top {len(hits)} matches for {args.keyword!r} (source={args.source}):\n")
    for i, h in enumerate(hits, 1):
        rec = h["record"]
        if h["source"] == "oscar":
            agency = ", ".join(rec.get("agencies") or []) or "-"
            print(f"  {i:2d}. [OSCAR]    {rec.get('acronym'):20s} | {rec.get('programme', '-'):30s} | {agency} | launch={rec.get('launch','-')}")
        else:
            print(f"  {i:2d}. [EOPORTAL] {rec.get('name'):40s} | slug={rec.get('slug')}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    merged = local_index.info(args.name)
    if merged is None:
        print(f"No local match for {args.name!r}.")
        if not args.no_online:
            online = online_search.search_satellite_online(args.name, num_results=5)
            if online:
                print(f"\n{online['hint']}\n")
                for r in online["results"][:5]:
                    print(f"  - {r['title']}\n    {r['url']}\n    {r['snippet'][:120]}")
        return 1
    payload = merged.to_dict()
    if args.json or args.pretty:
        _print_json(payload)
        return 0
    # pretty human format
    print(f"# {payload['name']}")
    if payload.get("aliases"):
        print(f"  Aliases: {', '.join(payload['aliases'])}")
    print(f"  Sources: {', '.join(payload['sources'])}")
    m = payload.get("merged") or {}
    if m.get("agency"):
        print(f"  Agency:  {m['agency']}")
    if m.get("launch_date"):
        print(f"  Launch:  {m['launch_date']}")
    if m.get("end_of_life"):
        print(f"  EOL:     {m['end_of_life']}")
    if m.get("status"):
        print(f"  Status:  {m['status']}")
    if m.get("orbit"):
        print(f"  Orbit:   {m['orbit']}")
    if m.get("instruments"):
        print(f"  Instruments ({len(m['instruments'])}): {', '.join(m['instruments'][:10])}{' ...' if len(m['instruments']) > 10 else ''}")
    print(f"  Coverage: {m.get('sources_count', len(payload['sources']))} of 2 sources")
    if payload.get("merge_hint"):
        print(f"  Note: {payload['merge_hint']}")
    # URLs
    if payload.get("eoportal") and payload["eoportal"].get("url"):
        print(f"\n  eoPortal: {payload['eoportal']['url']}")
    if payload.get("oscar") and payload["oscar"].get("detail_url"):
        print(f"  OSCAR:    {payload['oscar']['detail_url']}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Live-fetch a single satellite and (optionally) persist it."""
    source = args.source
    out: Dict[str, Any] = {"query": args.name, "source": source, "found": {}}
    target_path = os.path.join(local_index._data_dir(), "eoportal_satellites.jsonl")
    existing = local_index.all_eoportal()
    existing_slugs = {r.get("slug"): r for r in existing}

    # 1) try local first
    if source in ("oscar", "both"):
        rec = local_index._find_in_oscar(args.name)
        if rec:
            out["found"]["oscar"] = rec
    if source in ("eoportal", "both"):
        rec = local_index._find_in_eoportal(args.name)
        if rec:
            out["found"]["eoportal"] = rec
    if args.no_live:
        if not out["found"]:
            print(f"No local match for {args.name!r} (--no-live).")
            return 1
        _print_json(out)
        return 0

    # 2) try live fetch for whichever source is missing
    need_oscar = source in ("oscar", "both") and "oscar" not in out["found"]
    need_eo = source in ("eoportal", "both") and "eoportal" not in out["found"]

    if need_oscar:
        # Find sat_id by exact/loose match in OSCAR
        cand = None
        for r in local_index.all_oscar():
            if r.get("acronym", "").lower() == args.name.lower():
                cand = r
                break
        if cand is None:
            hits = local_index.search(args.name, source="oscar", limit=1)
            cand = hits[0]["record"] if hits else None
        if cand and cand.get("sat_id"):
            print(f"Fetching OSCAR detail for {cand['acronym']} (id={cand['sat_id']}) ...")
            det = scraper.fetch_oscar_detail(int(cand["sat_id"]))
            if det:
                cand = {**cand, "detail": det}
                out["found"]["oscar"] = cand

    if need_eo:
        # find slug
        slug = None
        for r in existing:
            if r.get("name", "").lower() == args.name.lower():
                slug = r.get("slug")
                break
        if slug is None:
            hits = local_index.search(args.name, source="eoportal", limit=1)
            slug = hits[0]["record"].get("slug") if hits else None
        if slug is None:
            # try name-to-slug
            slug = args.name.lower().replace(" ", "-")
            slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-")
        if slug:
            print(f"Fetching eoPortal detail for {slug} ...")
            det = scraper.fetch_eoportal_detail(slug)
            if det:
                # update local cache
                existing_slugs[slug] = det
                with open(target_path, "w", encoding="utf-8") as f:
                    from core.models import jsonl_dumps  # type: ignore
                    f.write(jsonl_dumps(list(existing_slugs.values())))
                local_index._load_jsonl.cache_clear()
                out["found"]["eoportal"] = det
            else:
                out.setdefault("warnings", []).append(
                    f"eoPortal detail fetch for {slug} failed (Cloudflare 504 or no detail page)."
                )

    if not out["found"]:
        print(f"No match for {args.name!r} in {source}.")
        online = online_search.search_satellite_online(args.name, num_results=3)
        if online:
            print(f"\n{online['hint']}\n")
            for r in online["results"][:3]:
                print(f"  - {r['title']} | {r['url']}")
        return 1

    # Re-merge so the user sees the freshly fetched data
    if "eoportal" in out["found"] or "oscar" in out["found"]:
        merged = local_index.info(args.name)
        if merged is not None:
            out["merged"] = merged.to_dict()

    if args.json or args.pretty:
        _print_json(out)
    else:
        print(f"\nFetched for {args.name!r}:")
        for src, rec in out["found"].items():
            n = rec.get("acronym") or rec.get("name") or rec.get("slug")
            url = rec.get("detail_url") or rec.get("url")
            print(f"  [{src}] {n}  ->  {url}")
        if out.get("merged"):
            m = out["merged"]["merged"]
            print(f"\n  Agency:    {m.get('agency')}")
            print(f"  Status:    {m.get('status')}")
            print(f"  Launch:    {m.get('launch_date')}")
            print(f"  Orbit:     {m.get('orbit')}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    s = local_index.stats()
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    print("satellite_search local index statistics")
    print("-" * 40)
    for k, v in s.items():
        print(f"  {k:18s} : {v}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    sources: List[str] = []
    if args.source in ("oscar", "both"):
        sources.append("oscar")
    if args.source in ("eoportal", "both"):
        sources.append("eoportal")
    rc = 0
    for src in sources:
        print(f"\n=== Updating {src} ===")
        t0 = time.time()
        if src == "oscar":
            xlsx = scraper.fetch_oscar_list()
            records = scraper.parse_oscar_xlsx(xlsx)
            from core.models import jsonl_dumps  # type: ignore
            out_path = os.path.join(local_index._data_dir(), "oscar_satellites.jsonl")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(jsonl_dumps([{**r, "source": "oscar"} for r in records]))
            print(f"  {len(records)} records -> {out_path}  ({time.time()-t0:.1f}s)")
        elif src == "eoportal":
            records = scraper.fetch_eoportal_list()
            from core.models import jsonl_dumps  # type: ignore
            out_path = os.path.join(local_index._data_dir(), "eoportal_satellites.jsonl")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(jsonl_dumps([{**r, "source": "eoportal"} for r in records]))
            print(f"  {len(records)} records -> {out_path}  ({time.time()-t0:.1f}s)")
    # rebuild merged index
    print("\n=== Rebuilding merged index ===")
    from build_index import _load_jsonl, _key  # type: ignore
    import json as _json
    data_dir = local_index._data_dir()
    oscar = _load_jsonl(os.path.join(data_dir, "oscar_satellites.jsonl"))
    eoportal = _load_jsonl(os.path.join(data_dir, "eoportal_satellites.jsonl"))
    merged: Dict[str, Dict[str, Any]] = {}
    for rec in oscar:
        n = rec.get("acronym") or ""
        if not n: continue
        merged.setdefault(_key(n), {})
        merged[_key(n)]["oscar"] = {
            "name": n,
            "sat_id": rec.get("sat_id"),
            "agency": ", ".join(rec.get("agencies") or []),
            "launch": rec.get("launch"),
            "eol": rec.get("eol"),
            "programme": rec.get("programme"),
            "orbit": rec.get("orbit"),
            "altitude": rec.get("altitude"),
            "inclination": rec.get("inclination"),
            "ect": rec.get("ect"),
            "status": rec.get("status"),
            "instruments": rec.get("instruments") or [],
            "url": rec.get("detail_url"),
        }
        merged[_key(n)].setdefault("display", n)
    for rec in eoportal:
        n = rec.get("name") or ""
        if not n: continue
        merged.setdefault(_key(n), {})
        merged[_key(n)]["eoportal"] = {
            "name": n,
            "slug": rec.get("slug"),
            "url": rec.get("url"),
        }
        merged[_key(n)].setdefault("display", n)
    out_path = os.path.join(data_dir, "merged_index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {len(merged)} unique keys -> {out_path}")
    return rc


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="satellite_search",
        description="Search and fetch remote-sensing satellite parameters "
                    "from eoPortal (ESA) and WMO OSCAR.",
    )
    p.add_argument("--json", action="store_true",
                   help="Output as JSON Lines (one record per line)")
    p.add_argument("--pretty", action="store_true",
                   help="Output as pretty-printed JSON (single object)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # list
    sp = sub.add_parser("list", help="List all satellites in the local index.")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=cmd_list)

    # search
    sp = sub.add_parser("search", help="Fuzzy search the local index by name.")
    sp.add_argument("keyword", help="Satellite name or partial name")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    # info
    sp = sub.add_parser("info", help="Show merged multi-source info for a satellite.")
    sp.add_argument("name", help="Satellite name (case-insensitive)")
    sp.add_argument("--no-online", action="store_true",
                    help="Don't fall back to web search if local has nothing")
    sp.set_defaults(func=cmd_info)

    # fetch
    sp = sub.add_parser("fetch",
                        help="Live-fetch a satellite from the source site(s) "
                             "and append it to the local index.")
    sp.add_argument("name", help="Satellite name (case-insensitive)")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.add_argument("--no-live", action="store_true",
                    help="Only consult the local index; don't hit the network")
    sp.set_defaults(func=cmd_fetch)

    # stats
    sp = sub.add_parser("stats", help="Show local index statistics.")
    sp.set_defaults(func=cmd_stats)

    # update
    sp = sub.add_parser("update", help="Re-scrape the source catalogues and rebuild the index.")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.set_defaults(func=cmd_update)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
