"""Data models for the satellite_search skill.

The skill ships three kinds of records:

* ``EoportalRecord`` — a single satellite entry from the eoPortal
  (https://www.eoportal.org) catalogue. The bundled index stores name + URL
  for every catalogue entry (~700+ missions); the optional ``summary``,
  ``agency``, ``status``, ``launch_date``, ``instruments`` are only filled
  after a per-satellite detail fetch.

* ``OscarRecord`` — a single satellite entry from WMO OSCAR
  (https://space.oscar.wmo.int) export. The bundled index covers all
  ~1000 missions and contains orbit / launch / status / instruments / agency.

* ``MergedRecord`` — what ``info`` returns: a unified view combining both
  sources, plus a ``merged`` sub-dict with the consensus headline.

All three are simple ``dataclass``-es so they can be serialized to JSON
without custom encoders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_EOPORTAL = "eoportal"
SOURCE_OSCAR = "oscar"
ALL_SOURCES = (SOURCE_EOPORTAL, SOURCE_OSCAR)


@dataclass
class EoportalRecord:
    """One eoPortal catalogue entry."""

    name: str
    slug: str
    url: str
    # Optional fields populated only after a per-satellite detail fetch.
    agency: Optional[str] = None
    country: Optional[str] = None
    launch_date: Optional[str] = None
    end_of_life: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    applications: List[str] = field(default_factory=list)
    instruments: List[str] = field(default_factory=list)
    measurement_domain: List[str] = field(default_factory=list)
    faq: List[Dict[str, str]] = field(default_factory=list)  # [{"q":..., "a":...}]
    last_updated: Optional[str] = None  # datePublished from JSON-LD

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_compact(self) -> Dict[str, Any]:
        """Compact representation used in the merged index — only fields that
        are populated from the list page (no detail fetched)."""
        return {
            "name": self.name,
            "slug": self.slug,
            "url": self.url,
        }


@dataclass
class OscarRecord:
    """One OSCAR catalogue entry.

    Field names match the OSCAR XLSX export header. ``agencies`` is the
    list of space agencies (one satellite may be operated by several,
    e.g. CBERS is CRESDA + INPE / AEB). ``instruments`` is parsed from the
    ``Payload`` column, which is a ``"\\n"``-separated list of instrument
    names with optional ``(spacecraft-suffix)`` clarifications.
    """

    acronym: str
    sat_id: int
    launch: Optional[str] = None  # raw text, e.g. "25 Aug 1997" or "TBD"
    eol: Optional[str] = None  # raw text, e.g. "≥2027" or "TBD"
    programme: Optional[str] = None
    agencies: List[str] = field(default_factory=list)
    orbit: Optional[str] = None  # "SunSync" / "GEO" / "L1" / ...
    altitude: Optional[str] = None  # raw text, e.g. "786 km" or "1.5e+06 km"
    longitude: Optional[str] = None
    inclination: Optional[str] = None
    ect: Optional[str] = None  # Equatorial Crossing Time, e.g. "10:30 desc"
    status: Optional[str] = None  # "Operational" / "Mission complete" / ...
    instruments: List[str] = field(default_factory=list)
    detail_url: Optional[str] = None  # e.g. https://space.oscar.wmo.int/satellites/view/454
    last_update: Optional[str] = None  # ISO timestamp from export

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_compact(self) -> Dict[str, Any]:
        return {
            "name": self.acronym,
            "sat_id": self.sat_id,
            "url": self.detail_url,
            "agency": ", ".join(self.agencies) if self.agencies else None,
            "launch": self.launch,
            "eol": self.eol,
            "programme": self.programme,
            "orbit": self.orbit,
            "altitude": self.altitude,
            "inclination": self.inclination,
            "ect": self.ect,
            "status": self.status,
            "instruments": self.instruments,
        }


@dataclass
class MergedRecord:
    """The output of ``info``: a single satellite with both sources if
    available, plus a ``merged`` headline summary.
    """

    name: str
    aliases: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    eoportal: Optional[Dict[str, Any]] = None
    oscar: Optional[Dict[str, Any]] = None
    merged: Dict[str, Any] = field(default_factory=dict)
    merge_hint: Optional[str] = None  # shown if only one source was found

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------

def jsonl_dumps(records: List[Dict[str, Any]]) -> str:
    """Serialize a list of dicts to JSON Lines (one record per line)."""
    return "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records) + "\n"


def jsonl_loads(text: str) -> List[Dict[str, Any]]:
    """Parse a JSON Lines string into a list of dicts; skips blank lines."""
    out: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out
