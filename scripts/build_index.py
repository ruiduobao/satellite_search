"""Build the cross-source merged index.

Reads ``oscar_satellites.jsonl`` and ``eoportal_satellites.jsonl`` from the
data directory and writes ``merged_index.json`` — a ``{name -> {source,
...compact fields}}`` lookup table that the ``info`` command uses as a
fast-path for the cross-source pair.

Usage
-----
::

    python scripts/build_index.py
    python scripts/build_index.py --data-dir ./data
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core.models import jsonl_loads  # type: ignore  # noqa: E402


def _load_jsonl(p: str) -> List[Dict[str, Any]]:
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        return jsonl_loads(f.read())


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build the merged satellite index.")
    p.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "data"))
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    oscar = _load_jsonl(os.path.join(args.data_dir, "oscar_satellites.jsonl"))
    eoportal = _load_jsonl(os.path.join(args.data_dir, "eoportal_satellites.jsonl"))

    # merged index: lowercased name -> {"oscar": {...}, "eoportal": {...}}
    # We keep the original-case name as the JSON key but lowercase for lookup
    merged: Dict[str, Dict[str, Any]] = {}

    def _key(s: str) -> str:
        return s.strip().lower()

    for rec in oscar:
        name = rec.get("acronym") or ""
        if not name:
            continue
        merged.setdefault(_key(name), {})
        merged[_key(name)]["oscar"] = {
            "name": name,
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
        # store display name (first one wins)
        merged[_key(name)].setdefault("display", name)

    for rec in eoportal:
        name = rec.get("name") or ""
        if not name:
            continue
        merged.setdefault(_key(name), {})
        merged[_key(name)]["eoportal"] = {
            "name": name,
            "slug": rec.get("slug"),
            "url": rec.get("url"),
        }
        merged[_key(name)].setdefault("display", name)

    out_path = os.path.join(args.data_dir, "merged_index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    if not args.quiet:
        print(f"OK: {len(merged)} unique satellite keys -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
