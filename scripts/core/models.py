"""Data models for the satellite_search skill.

The skill ships five kinds of records:

* ``EoportalRecord`` — a single satellite entry from the eoPortal
  (https://www.eoportal.org) catalogue. The bundled index stores name + URL
  for every catalogue entry (~700+ missions); the optional ``summary``,
  ``agency``, ``status``, ``launch_date``, ``instruments`` are only filled
  after a per-satellite detail fetch.

* ``OscarRecord`` — a single satellite entry from WMO OSCAR
  (https://space.oscar.wmo.int) export. The bundled index covers all
  ~1000 missions and contains orbit / launch / status / instruments / agency.

* ``CelestrakRecord`` — a single entry from the CelesTrak SATCAT
  (https://celestrak.org/pub/satcat.csv). The full catalogue covers 70k+
  objects (1957 → present), most of which are debris / rocket bodies; the
  active-payloads subset (~16k records) is the useful part. Fields are
  NORAD_CAT_ID, OBJECT_NAME, OBJECT_TYPE, OPS_STATUS_CODE, OWNER,
  LAUNCH_DATE, LAUNCH_SITE, DECAY_DATE, PERIOD, INCLINATION, APOGEE,
  PERIGEE, ORBIT_CENTER, ORBIT_TYPE.

* ``SatnogsRecord`` — a single entry from the SatNOGS DB
  (https://db.satnogs.org/api/satellites/) — a community catalogue of
  amateur / small / university satellites. Fields include norad_cat_id,
  name, status, launched, deployed, operator, countries, website, citation.

* ``UcsRecord`` — a single entry from the Union of Concerned Scientists
  Satellite Database (https://www.ucs.org/resources/satellite-database) —
  a curated list of ~7,500 currently-active satellites, with rich
  metadata (operator, type, purpose, launch mass, orbit class, etc.).

* ``MergedRecord`` — what ``info`` returns: a unified view combining all
  available sources, plus a ``merged`` sub-dict with the consensus headline.

All are simple ``dataclass``-es so they can be serialized to JSON without
custom encoders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_EOPORTAL = "eoportal"
SOURCE_OSCAR = "oscar"
SOURCE_CELESTRAK = "celestrak"
SOURCE_SATNOGS = "satnogs"
SOURCE_UCS = "ucs"
ALL_SOURCES = (
    SOURCE_EOPORTAL,
    SOURCE_OSCAR,
    SOURCE_CELESTRAK,
    SOURCE_SATNOGS,
    SOURCE_UCS,
)


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
class CelestrakRecord:
    """One CelesTrak SATCAT entry.

    The CelesTrak SATCAT covers all cataloged space objects (payloads,
    rocket bodies, debris) since 1957. ``OBJECT_TYPE`` is one of:
    ``PAY`` (payload), ``R/B`` (rocket body), ``DEB`` (debris),
    ``UNK`` (unknown). A record with a non-empty ``DECAY_DATE`` has
    already re-entered the atmosphere and is no longer in orbit.

    Country code in ``OWNER`` is a 3-letter code (ISO 3166-1 alpha-3
    when known; ``CIS`` for the former Soviet Union, ``PRC`` for China,
    ``ESA`` for the European Space Agency). See ``i18n.COUNTRY_ZH``.
    """

    name: str
    norad_id: int
    intl_designator: Optional[str] = None  # e.g. "1998-067A"
    object_type: Optional[str] = None  # PAY / R/B / DEB / UNK
    ops_status: Optional[str] = None  # operational status code
    owner: Optional[str] = None  # 3-letter country code
    launch_date: Optional[str] = None  # ISO 8601 date
    launch_site: Optional[str] = None  # e.g. "TYMSC" for Baikonur
    decay_date: Optional[str] = None  # ISO 8601 date or None
    period_min: Optional[float] = None  # orbital period in minutes
    inclination_deg: Optional[float] = None
    apogee_km: Optional[float] = None
    perigee_km: Optional[float] = None
    rcs_m2: Optional[float] = None  # radar cross section
    orbit_center: Optional[str] = None  # EA / MO / JU / ...
    orbit_type: Optional[str] = None  # ORB / IMP / LAN / ...

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_compact(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "norad_id": self.norad_id,
            "intl_designator": self.intl_designator,
            "object_type": self.object_type,
            "owner": self.owner,
            "launch_date": self.launch_date,
            "launch_site": self.launch_site,
            "decay_date": self.decay_date,
            "period_min": self.period_min,
            "inclination_deg": self.inclination_deg,
            "apogee_km": self.apogee_km,
            "perigee_km": self.perigee_km,
            "orbit_center": self.orbit_center,
            "orbit_type": self.orbit_type,
        }

    @property
    def is_active_payload(self) -> bool:
        return self.object_type == "PAY" and not self.decay_date


@dataclass
class SatnogsRecord:
    """One SatNOGS DB satellite entry.

    SatNOGS tracks amateur / small / university satellites observed by the
    SatNOGS ground-station network. ``norad_cat_id`` is the cross-reference
    to CelesTrak and the public SATCAT. ``status`` is one of
    ``alive`` / ``dead`` / ``re-entered`` / ``future`` / ``unknown``.
    ``countries`` is a comma-separated list of ISO 3166-1 alpha-2 country
    codes (the field is a plain string in the API).
    """

    name: str
    sat_id: str  # SatNOGS internal id, e.g. "SCHX-0895-2361-9925-0309"
    norad_cat_id: Optional[int] = None
    status: Optional[str] = None  # alive / dead / re-entered / future / unknown
    launched: Optional[str] = None  # ISO 8601 timestamp
    deployed: Optional[str] = None
    operator: Optional[str] = None
    countries: Optional[str] = None  # ISO 3166-1 alpha-2 codes, comma-separated
    website: Optional[str] = None
    citation: Optional[str] = None  # long string of reference URLs
    image: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_compact(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "sat_id": self.sat_id,
            "norad_cat_id": self.norad_cat_id,
            "status": self.status,
            "operator": self.operator,
            "countries": self.countries,
            "launched": self.launched,
            "website": self.website,
        }


@dataclass
class UcsRecord:
    """One UCS Satellite Database entry.

    The UCS database is a curated list of currently-active satellites. The
    field names are preserved verbatim from the original tab-delimited
    file so users can cross-reference the source.

    Notable fields: ``Name``, ``NORAD Number``, ``Country of
    Operator/Owner``, ``Operator/Owner``, ``Users``, ``Purpose``,
    ``Class of Orbit``, ``Type of Orbit``, ``Longitude of GEO (degrees)``,
    ``Perigee (km)``, ``Apogee (km)``, ``Eccentricity``, ``Inclination
    (degrees)``, ``Period (minutes)``, ``Launch Mass (kg)``, ``Dry Mass
    (kg)``, ``Power (Watts)``, ``Date of Launch``, ``Expected Lifetime
    (yrs)``, ``Contractor``, ``Country of Contractor``, ``Launch Site``,
    ``Launch Vehicle``, ``COSPAR Number``, ``NORAD Number``.
    """

    name: str
    norad_number: Optional[int] = None
    country: Optional[str] = None
    operator: Optional[str] = None
    users: Optional[str] = None
    purpose: Optional[str] = None
    orbit_class: Optional[str] = None
    orbit_type: Optional[str] = None
    perigee_km: Optional[float] = None
    apogee_km: Optional[float] = None
    eccentricity: Optional[float] = None
    inclination_deg: Optional[float] = None
    period_min: Optional[float] = None
    launch_mass_kg: Optional[float] = None
    dry_mass_kg: Optional[float] = None
    power_w: Optional[float] = None
    launch_date: Optional[str] = None
    expected_lifetime_yrs: Optional[float] = None
    contractor: Optional[str] = None
    contractor_country: Optional[str] = None
    launch_site: Optional[str] = None
    launch_vehicle: Optional[str] = None
    cospar_number: Optional[str] = None
    comments: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_compact(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "norad_number": self.norad_number,
            "country": self.country,
            "operator": self.operator,
            "purpose": self.purpose,
            "orbit_class": self.orbit_class,
            "launch_date": self.launch_date,
            "launch_mass_kg": self.launch_mass_kg,
        }


@dataclass
class MergedRecord:
    """The output of ``info``: a single satellite with all available sources
    merged, plus a ``merged`` headline summary.
    """

    name: str
    name_zh: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    norad_id: Optional[int] = None  # cross-source canonical NORAD catalog id
    eoportal: Optional[Dict[str, Any]] = None
    oscar: Optional[Dict[str, Any]] = None
    celestrak: Optional[Dict[str, Any]] = None
    satnogs: Optional[Dict[str, Any]] = None
    ucs: Optional[Dict[str, Any]] = None
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
