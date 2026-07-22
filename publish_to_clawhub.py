"""Publish a new version of satellite-search skill to ClawHub.

Usage
-----
::
    CLAWHUB_TOKEN=... python publish_to_clawhub.py
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sys

import requests


def collect_files(root: str = ".") -> list[str]:
    """Walk the repo and return a list of file paths to upload.

    Skips:
    * Anything under .git, __pycache__, .pytest_cache
    * Scratch files in data/_* (per .gitignore)
    * data/celestrak_satellites.jsonl (25 MB full SATCAT) — too large for
      the bundle; users run ``update --source celestrak`` on first install
      to fetch the fresh full SATCAT. The active_payloads subset (7 MB)
      is bundled and covers all common search/lookup needs.
    """
    out = []
    for dirpath, dirs, files in os.walk(root):
        # Prune noise dirs in place
        dirs[:] = [
            d for d in dirs
            if d not in (".git", "__pycache__", ".pytest_cache")
        ]
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        for fn in files:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            # Skip data/_* scratch files
            if rel.startswith("data/_"):
                continue
            # Skip the 25 MB full CelesTrak SATCAT — use the active subset instead
            if rel == "data/celestrak_satellites.jsonl":
                continue
            # Skip the publish script itself — internal tooling
            if rel == "publish_to_clawhub.py":
                continue
            out.append(rel)
    return sorted(out)


def file_meta(path: str) -> dict:
    sz = os.path.getsize(path)
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    c, _ = mimetypes.guess_type(path)
    return {
        "path": path,
        "size": sz,
        "sha256": h,
        "contentType": c or "application/octet-stream",
    }


def main() -> int:
    token = os.environ.get("CLAWHUB_TOKEN")
    if not token:
        print("ERROR: CLAWHUB_TOKEN env var is required", file=sys.stderr)
        return 1

    api = "https://clawhub.ai/api/v1"
    slug = "satellite-search"
    version = "0.4.0"

    file_paths = collect_files(".")
    files_meta = [file_meta(p) for p in file_paths]
    total_size = sum(f["size"] for f in files_meta)
    print(f"Files to upload: {len(file_paths)} ({total_size/1e6:.1f} MB)")

    payload = {
        "slug": slug,
        "displayName": "卫星参数查询",
        "version": version,
        "changelog": (
            "**v0.4.0: 4-source satellite search (eoPortal + OSCAR + CelesTrak + SatNOGS) — 22,189 records total**\n\n"
            "- **New: CelesTrak SATCAT integration** — 70,006 total / 19,627 active payloads (NORAD catalog). "
            "Adds orbital period, inclination, apogee, perigee, launch site, owner country, object type, orbit center.\n"
            "- **New: SatNOGS DB integration** — 1,688 alive + 1,016 re-entered amateur/cubesat satellites. "
            "Adds operator, website, citation.\n"
            "- **New: NORAD id direct lookup** — 1-6 digit numeric queries now resolve across all 4 sources. "
            "Try `info 25544` (ISS).\n"
            "- **New: 5 i18n enum tables** — CelesTrak country codes (US/CIS/PRC/ISS/ESA), object types "
            "(PAY/R/B/DEB/UNK), orbit centers, SatNOGS status, UCS orbit class + purpose.\n"
            "- **New: 18 tests** for the new sources (CelesTrak search, NORAD id lookup, country translation, "
            "dataclass deserialization). 42/42 tests pass.\n"
            "- **CLI extensions** — `search --source celestrak|satnogs|ucs|all`, `list --source all`, "
            "`update --source all` auto-rebuilds merged index.\n"
            "- **Bug fix** — `update --source eoportal` no longer wipes the v0.2.0 detail payloads (now "
            "preserves `detail` field when re-scraping the list).\n"
            "- **Total bundled** — ~21,000 unique records, ~39 MB.\n"
            "- **UCS** — Database model + helpers are in place but the source S3 bucket returns 403; "
            "planned for v0.5.0.\n\n"
            "中文：新增 CelesTrak NORAD 目录 70k+ 条 + SatNOGS 业余/立方星 1.7k+ 条；通过 1-6 位数字 "
            "NORAD 目录号跨 4 源自动关联，本地秒级查询。"
        ),
        "tags": [
            "gis", "remote-sensing", "satellite", "eoportal", "oscar", "wmo",
            "celestrak", "satnogs", "norad", "earth-observation", "params", "中文",
        ],
        "files": files_meta,
    }
    payload_str = json.dumps(payload, ensure_ascii=False)
    print(f"Payload size: {len(payload_str)/1e3:.1f} KB")

    # Multipart: payload as a JSON string field, files as binary
    mp_files = [("payload", (None, payload_str, "application/json"))]
    for p in file_paths:
        mp_files.append(("files", (p, open(p, "rb"), mimetypes.guess_type(p)[0] or "application/octet-stream")))

    print("Uploading...")
    r = requests.post(
        f"{api}/skills",
        headers={"Authorization": f"Bearer {token}"},
        files=mp_files,
        timeout=600,
    )
    print(f"POST /skills status: {r.status_code}")
    print("body:", r.text[:1500])
    return 0 if r.status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
