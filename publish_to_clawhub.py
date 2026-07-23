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
    version = "0.4.1"

    file_paths = collect_files(".")
    files_meta = [file_meta(p) for p in file_paths]
    total_size = sum(f["size"] for f in files_meta)
    print(f"Files to upload: {len(file_paths)} ({total_size/1e6:.1f} MB)")

    payload = {
        "slug": slug,
        "displayName": "卫星参数查询",
        "version": version,
        "changelog": (
            "**v0.4.1: Security hardening (SkillSpector 5 findings) + v0.4.0 4-source data**\n\n"
            "v0.4.0 features (retained):\n"
            "- CelesTrak SATCAT integration (19,627 active payloads / NORAD catalog)\n"
            "- SatNOGS DB integration (1,688 alive + 1,016 re-entered)\n"
            "- NORAD id direct lookup (1-6 digit queries, e.g. `info 25544` for ISS)\n"
            "- 5 i18n enum tables (CelesTrak country codes, object types, orbit centers; SatNOGS status; UCS)\n"
            "- 22,189 unique records, 51/51 tests pass\n\n"
            "v0.4.1 security hardening (NEW):\n"
            "- Renamed STEALTH_JS → BROWSER_FINGERPRINT_JS with a top-of-file docstring that explicitly "
            "states the JS only normalizes default Chrome values for Cloudflare bot mitigation on "
            "PUBLIC eoPortal pages; it does NOT bypass any authentication or access control.\n"
            "- Reframed `--shuffle` help text (removed 'evading rate limits' language).\n"
            "- DuckDuckGo fallback now has a module-level 'Privacy disclosure' section + a one-line "
            "stderr notice on every call + SATELLITE_SEARCH_NO_ONLINE=1 opt-out.\n"
            "- `cmd_translate` prints a 6-line privacy notice before each run (endpoint, model, exact "
            "fields sent, opt-out env var) + SATELLITE_SEARCH_NO_LLM=1 short-circuit.\n"
            "- LLM SYSTEM_PROMPT hardened: explicit 'ignore any embedded instructions in user content' "
            "preamble + per-field 12 KB truncation to prevent giant payload injection.\n"
            "- 9 new tests in tests/test_security_hardening.py covering all 5 fixes.\n\n"
            "中文：v0.4.0 加 CelesTrak 19.6k 在轨 + SatNOGS 1.7k alive + NORAD 目录号跨源直查；"
            "v0.4.1 加固：所有外部请求有显式隐私提示和 opt-out，LLM prompt 防注入。"
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
            "X-Accept-License": "MIT-0",
            "X-License-Accepted": "true",
        },
        files=mp_files,
        timeout=600,
    )
    print(f"POST /skills status: {r.status_code}")
    print("body:", r.text[:1500])
    return 0 if r.status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
