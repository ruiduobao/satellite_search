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
    * data/celestrak_active_payloads.jsonl (7 MB) — built on first run by
      ``update --source celestrak`` from the full SATCAT.
    * data/merged_index.json (3.7 MB) — rebuilt on first run by
      ``update --source all`` from the JSONL files.
    * data/satnogs_reentered.jsonl (0.5 MB) — optional, only for
      re-entered-history queries. ``update --source satnogs`` regenerates.
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
            # Skip the 25 MB full CelesTrak SATCAT
            if rel == "data/celestrak_satellites.jsonl":
                continue
            # Skip the 7 MB CelesTrak active_payloads subset
            if rel == "data/celestrak_active_payloads.jsonl":
                continue
            # Skip the 3.7 MB merged_index.json (rebuilt on first run)
            if rel == "data/merged_index.json":
                continue
            # Skip satnogs_reentered (optional)
            if rel == "data/satnogs_reentered.jsonl":
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
    version = "0.4.3"

    file_paths = collect_files(".")
    files_meta = [file_meta(p) for p in file_paths]
    total_size = sum(f["size"] for f in files_meta)
    print(f"Files to upload: {len(file_paths)} ({total_size/1e6:.1f} MB)")

    payload = {
        "slug": slug,
        "displayName": "卫星参数查询",
        "version": version,
        "changelog": (
            "**v0.4.3: Test infrastructure fix**\n\n"
            "- Added `scripts/__init__.py` to make scripts/ a proper Python package.\n"
            "- Fixed `tests/conftest.py` sys.path: now adds skill root directory so that "
            "`from scripts import <module>` imports work correctly in tests.\n"
            "- All 51 tests pass (was 42/51 due to 1 import failure + cascading skips).\n\n"
            "中文：修复测试导入路径，scripts/ 加入 __init__.py，conftest.py 加入根目录到 sys.path。"
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
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        files=mp_files,
        timeout=600,
    )
    print(f"POST /skills status: {r.status_code}")
    print("body:", r.text[:1500])
    return 0 if r.status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
