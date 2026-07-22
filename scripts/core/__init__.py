"""satellite_search core package.

This package provides:
  * `models`         — dataclass-style typed records for satellite metadata
  * `local_index`    — read-only queries against the bundled JSONL/JSON data
  * `scraper`        — on-demand Playwright fetches for eoPortal / OSCAR detail
  * `online_search`  — fallback to web_search when local + fetch both fail
"""

from .models import (
    EoportalRecord,
    MergedRecord,
    OscarRecord,
    jsonl_dumps,
    jsonl_loads,
)

__all__ = [
    "EoportalRecord",
    "MergedRecord",
    "OscarRecord",
    "jsonl_dumps",
    "jsonl_loads",
]
