"""Rebuild the merged_index.json from the (now detail-enriched) source
JSONL files.

The output structure is unchanged from the previous build_index.py, but
records that have a ``detail`` sub-record (from a successful
eoPortal detail fetch) are surfaced so the ``info`` command can show
the full text / FAQ / Quick facts without re-fetching.

Usage
-----
    python scripts/build_detailed_index.py
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


def _key(s: str) -> str:
    return s.strip().lower()


def main(argv=None):
    p = argparse.ArgumentParser(description="Build the merged index (detail + zh).")
    p.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "data"))
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    oscar = _load_jsonl(os.path.join(args.data_dir, "oscar_satellites.jsonl"))
    eoportal = _load_jsonl(os.path.join(args.data_dir, "eoportal_satellites.jsonl"))
    zh_translations = _load_jsonl(os.path.join(args.data_dir, "eoportal_satellites_zh.jsonl"))
    zh_by_slug = {r.get("slug"): r for r in zh_translations if r.get("slug")}

    merged: Dict[str, Dict[str, Any]] = {}

    for rec in oscar:
        n = rec.get("acronym") or ""
        if not n:
            continue
        k = _key(n)
        merged.setdefault(k, {})
        merged[k]["oscar"] = {
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
        merged[k].setdefault("display", n)

    eoportal_with_detail = 0
    eoportal_with_zh = 0
    for rec in eoportal:
        n = rec.get("name") or ""
        if not n:
            continue
        k = _key(n)
        slug = rec.get("slug")
        d = rec.get("detail")
        eo_entry: Dict[str, Any] = {
            "name": n,
            "slug": slug,
            "url": rec.get("url"),
            "taxonomy": rec.get("taxonomy") or [],
        }
        if d:
            eo_entry.update({
                "agency": d.get("agency"),
                "country": d.get("country"),
                "launch_date": d.get("launch_date"),
                "end_of_life": d.get("end_of_life"),
                "status": d.get("status"),
                "summary": d.get("summary"),
                "applications": d.get("applications") or [],
                "instruments": d.get("instruments") or [],
                "measurement_domain": d.get("measurement_domain") or [],
                "faq": d.get("faq") or [],
                "last_updated": d.get("last_updated"),
            })
            eoportal_with_detail += 1
        # Overlay Chinese translations
        if slug and slug in zh_by_slug:
            zt = zh_by_slug[slug]
            if zt.get("name_zh"):
                eo_entry["name_zh"] = zt["name_zh"]
            if zt.get("agency_zh"):
                eo_entry["agency_zh"] = zt["agency_zh"]
            if zt.get("status_zh"):
                eo_entry["status_zh"] = zt["status_zh"]
            if zt.get("summary_zh") and eo_entry.get("summary"):
                eo_entry["summary_zh"] = zt["summary_zh"]
                eo_entry["summary_en"] = eo_entry["summary"]
            if zt.get("applications_zh") and eo_entry.get("applications"):
                eo_entry["applications_zh"] = list(zt["applications_zh"])
                eo_entry["applications_en"] = list(eo_entry["applications"])
            if zt.get("faq_zh") and eo_entry.get("faq"):
                eo_entry["faq_zh"] = list(zt["faq_zh"])
                eo_entry["faq_en"] = list(eo_entry["faq"])
            eoportal_with_zh += 1
        merged.setdefault(k, {})
        merged[k]["eoportal"] = eo_entry
        merged[k].setdefault("display", n)

    out_path = os.path.join(args.data_dir, "merged_index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))

    if not args.quiet:
        n_total = len(merged)
        print(f"OK: {n_total} unique satellite keys -> {out_path}")
        print(f"  with eoportal detail: {eoportal_with_detail}")
        print(f"  with Chinese translation: {eoportal_with_zh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
