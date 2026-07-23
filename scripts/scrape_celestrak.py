"""Scrape the CelesTrak SATCAT (Space Command satellite catalog) bulk CSV.

CelesTrak publishes the full SATCAT — every cataloged space object since
Sputnik 1 (1957) — as a single ~7 MB CSV. The download is anonymous,
unauthenticated, and the data is in the public domain.

This script

1. Downloads ``https://celestrak.org/pub/satcat.csv`` to ``data/_satcat.csv``
   (skipped if the file already exists locally; pass ``--force`` to re-fetch).
2. Parses the CSV (RFC 4180) and writes two JSONL files to ``data/``:

   - ``celestrak_satellites.jsonl``       — all 70k+ objects (debris + payloads)
   - ``celestrak_active_payloads.jsonl``  — filtered to currently-active payloads
                                           (OBJECT_TYPE=PAY and no DECAY_DATE)
                                           ≈ 16,000 satellites

The ``OBJECT_TYPE`` codes (PAY / R/B / DEB / UNK) and ``OPS_STATUS_CODE``
follow the values documented at https://celestrak.org/satcat/satcat-format.php.

We bypass the system proxy by setting ``requests.trust_env = False`` so
the connection goes directly to celestrak.org.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

# Bypass system proxy env vars — direct connection works for CelesTrak
requests.trust_env = False

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA_DIR = os.path.join(SKILL_ROOT, "data")
RAW_CSV = os.path.join(DATA_DIR, "_satcat.csv")
ALL_JSONL = os.path.join(DATA_DIR, "celestrak_satellites.jsonl")
ACTIVE_JSONL = os.path.join(DATA_DIR, "celestrak_active_payloads.jsonl")

USER_AGENT = "satellite_search/0.4 (+https://github.com/ruiduobao/satellite_search)"


def download_csv(force: bool = False) -> str:
    """Download the SATCAT CSV. Returns the local path."""
    if not force and os.path.exists(RAW_CSV) and os.path.getsize(RAW_CSV) > 1_000_000:
        size_mb = os.path.getsize(RAW_CSV) / 1024 / 1024
        print(f"[celestrak] using cached {RAW_CSV} ({size_mb:.2f} MB)", file=sys.stderr)
        return RAW_CSV
    print(f"[celestrak] downloading {SATCAT_URL} ...", file=sys.stderr)
    t0 = time.time()
    with requests.get(SATCAT_URL, headers={"User-Agent": USER_AGENT}, stream=True, timeout=180) as r:
        r.raise_for_status()
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(RAW_CSV, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB
                f.write(chunk)
    elapsed = time.time() - t0
    size_mb = os.path.getsize(RAW_CSV) / 1024 / 1024
    print(f"[celestrak] downloaded {size_mb:.2f} MB in {elapsed:.1f}s", file=sys.stderr)
    return RAW_CSV


def _to_int(v: Any) -> Optional[int]:
    if v in (None, "", "null", "None"):
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _to_float(v: Any) -> Optional[float]:
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def parse_csv(csv_path: str) -> List[Dict[str, Any]]:
    """Parse the SATCAT CSV into a list of dicts. Numeric fields are
    converted to ``int``/``float`` where appropriate. Empty strings become
    ``None`` for cleaner JSON."""
    out: List[Dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec: Dict[str, Any] = {}
            for k, v in row.items():
                v = (v or "").strip()
                if v == "" or v.lower() == "null":
                    rec[k] = None
                else:
                    rec[k] = v
            # Convert numeric fields
            for nk in ("NORAD_CAT_ID",):
                if rec.get(nk) is not None:
                    rec[nk] = _to_int(rec[nk])
            for fk in ("PERIOD", "INCLINATION", "APOGEE", "PERIGEE", "RCS"):
                if rec.get(fk) is not None:
                    rec[fk] = _to_float(rec[fk])
            out.append(rec)
    return out


def filter_active_payloads(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the subset of records that are *currently active payloads*:
    OBJECT_TYPE=PAY and no DECAY_DATE (still in orbit). ~16k satellites."""
    out = []
    for r in records:
        if r.get("OBJECT_TYPE") != "PAY":
            continue
        if r.get("DECAY_DATE"):  # has a decay date → already re-entered
            continue
        out.append(r)
    return out


def write_jsonl(records: List[Dict[str, Any]], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            import json
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Scrape CelesTrak SATCAT bulk CSV")
    p.add_argument("--force", action="store_true", help="Re-download the CSV even if cached")
    p.add_argument(
        "--no-filter",
        action="store_true",
        help="Skip writing the active-payloads subset",
    )
    args = p.parse_args()

    csv_path = download_csv(force=args.force)
    print("[celestrak] parsing CSV ...", file=sys.stderr)
    t0 = time.time()
    records = parse_csv(csv_path)
    print(f"[celestrak] parsed {len(records):,} records in {time.time()-t0:.1f}s", file=sys.stderr)

    # Quick stats
    type_counts: Dict[str, int] = {}
    for r in records:
        t = r.get("OBJECT_TYPE") or "UNK"
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"[celestrak] by OBJECT_TYPE: {type_counts}", file=sys.stderr)

    active = filter_active_payloads(records)
    print(f"[celestrak] active payloads (PAY + no decay): {len(active):,}", file=sys.stderr)

    # Write
    write_jsonl(records, ALL_JSONL)
    print(f"[celestrak] wrote {len(records):,} records to {ALL_JSONL}", file=sys.stderr)
    if not args.no_filter:
        write_jsonl(active, ACTIVE_JSONL)
        print(f"[celestrak] wrote {len(active):,} active payloads to {ACTIVE_JSONL}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
