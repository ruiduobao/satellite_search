"""Read-only access to the bundled satellite data files.

The skill ships three data files under ``data/``:

* ``oscar_satellites.jsonl``     — one record per line, the OSCAR catalogue
* ``eoportal_satellites.jsonl``  — one record per line, the eoPortal catalogue
* ``merged_index.json``          — JSON dict of ``name -> {compact fields}``,
                                   used for fast cross-source lookup

This module loads them once (lazily) and exposes lookup helpers.

Network policy
--------------
This module never touches the network. The ``scraper`` and ``online_search``
modules are responsible for live fetches.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    EoportalRecord,
    MergedRecord,
    OscarRecord,
    jsonl_loads,
)


# ---------------------------------------------------------------------------
# Data directory resolution
# ---------------------------------------------------------------------------

DEFAULT_DATA_SUBDIR = "data"

# Heuristic name normalization for cross-source matching. "Sentinel-2A" and
# "S2A" are different strings; we try a few canonicalization rules and
# fall back to substring matching when nothing else works.

def _normalize(s: str) -> str:
    """Lowercase, strip whitespace + punctuation, drop diacritics."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[\s\-_/.()\[\]]+", "", s)
    return s


def _is_chinese(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in s)


def _data_dir() -> str:
    """Resolve the data directory.

    Resolution order:

    1. ``SATELLITE_SEARCH_DATA_DIR`` env var (absolute path)
    2. The package's sibling ``data/`` (typical skill layout)
    """
    override = os.environ.get("SATELLITE_SEARCH_DATA_DIR")
    if override and os.path.isdir(override):
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    # scripts/core/local_index.py -> skill root is ../../../
    skill_root = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(skill_root, DEFAULT_DATA_SUBDIR)


# ---------------------------------------------------------------------------
# JSONL / JSON loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_jsonl(filename: str) -> List[Dict[str, Any]]:
    p = os.path.join(_data_dir(), filename)
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        text = f.read()
    return jsonl_loads(text)


@lru_cache(maxsize=1)
def _load_merged_index() -> Dict[str, Dict[str, Any]]:
    p = os.path.join(_data_dir(), "merged_index.json")
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def all_oscar() -> List[Dict[str, Any]]:
    """Return all OSCAR records as raw dicts (cached)."""
    return _load_jsonl("oscar_satellites.jsonl")


def all_eoportal() -> List[Dict[str, Any]]:
    """Return all eoPortal records as raw dicts (cached)."""
    return _load_jsonl("eoportal_satellites.jsonl")


def stats() -> Dict[str, int]:
    """Quick stats for the ``stats`` CLI command."""
    o = all_oscar()
    e = all_eoportal()
    m = _load_merged_index()
    return {
        "oscar": len(o),
        "eoportal": len(e),
        "merged_index_keys": len(m),
        "data_dir": _data_dir(),
    }


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

# Aliases used to make common cross-source pairings work without web search.
# Keys are normalized names; values are lists of (source, canonical_name) hints.
ALIAS_HINTS: Dict[str, List[Tuple[str, str]]] = {
    _normalize("Sentinel-2A"): [("oscar", "S2A"), ("eoportal", "copernicus-sentinel-2")],
    _normalize("Sentinel-2B"): [("oscar", "S2B"), ("eoportal", "copernicus-sentinel-2")],
    _normalize("Sentinel-2"):  [("oscar", "S2A"), ("eoportal", "copernicus-sentinel-2")],
    _normalize("Sentinel-1A"): [("oscar", "S1A"), ("eoportal", "copernicus-sentinel-1")],
    _normalize("Sentinel-1B"): [("oscar", "S1B"), ("eoportal", "copernicus-sentinel-1")],
    _normalize("Sentinel-1"):  [("oscar", "S1A"), ("eoportal", "copernicus-sentinel-1")],
    _normalize("Sentinel-3A"): [("oscar", "S3A"), ("eoportal", "copernicus-sentinel-3")],
    _normalize("Sentinel-3B"): [("oscar", "S3B"), ("eoportal", "copernicus-sentinel-3")],
    _normalize("Landsat-9"):  [("oscar", "LS9")],
    _normalize("Landsat-8"):  [("oscar", "LS8")],
    _normalize("高分一号"):    [("eoportal", "gaofen-1"), ("oscar", "GF-1")],
    _normalize("GF-1"):        [("eoportal", "gaofen-1"), ("oscar", "GF-1")],
    _normalize("高分三号"):    [("eoportal", "gaofen-3"), ("oscar", "GF-3")],
    _normalize("GF-3"):        [("eoportal", "gaofen-3"), ("oscar", "GF-3")],
    _normalize("风云四号"):    [("eoportal", "fy-4"), ("oscar", "FY-4A")],
    _normalize("FY-4A"):       [("eoportal", "fy-4"), ("oscar", "FY-4A")],
    _normalize("资源三号"):    [("eoportal", "ziyuan-3"), ("oscar", "ZY-3-02")],
    _normalize("ZY-3"):        [("eoportal", "ziyuan-3"), ("oscar", "ZY-3-02")],
    _normalize("CBERS-4A"):    [("eoportal", "cbers-4a")],
}


def _score(query_norm: str, candidate_norm: str) -> int:
    """A simple matching score. Higher is better. 0 = no match.

    The matching is intentionally permissive: substring containment counts
    on both sides. This handles "高分" matching "高分一号", "Sentinel"
    matching "Sentinel-2A", "landsat" matching "Landsat-9", etc.
    """
    if not query_norm or not candidate_norm:
        return 0
    if query_norm == candidate_norm:
        return 1000
    if query_norm in candidate_norm or candidate_norm in query_norm:
        return 500
    # word-level for englishish names
    q_words = re.findall(r"[a-z0-9]+", query_norm)
    c_words = re.findall(r"[a-z0-9]+", candidate_norm)
    if q_words and c_words:
        common = set(q_words) & set(c_words)
        if common and len(common) >= 1 and len(common) / max(len(q_words), len(c_words)) >= 0.5:
            return 200
    return 0


def _search_records(query: str, records: List[Dict[str, Any]], name_keys: List[str], limit: int = 20) -> List[Tuple[int, Dict[str, Any]]]:
    """Generic: search records whose name-like field scores above 0."""
    qn = _normalize(query)
    out: List[Tuple[int, Dict[str, Any]]] = []
    for rec in records:
        best = 0
        for k in name_keys:
            v = rec.get(k) or ""
            if not isinstance(v, str):
                continue
            s = _score(qn, _normalize(v))
            if s > best:
                best = s
        if best > 0:
            out.append((best, rec))
    out.sort(key=lambda x: (-x[0], x[1].get(name_keys[0], "") or ""))
    return out[:limit]


def search(query: str, source: str = "both", limit: int = 20) -> List[Dict[str, Any]]:
    """Search the local index for a satellite by name (case-insensitive,
    diacritic-insensitive, allows substring match).

    Parameters
    ----------
    query : str
        The satellite name or partial name. Chinese is supported (e.g.
        "高分", "风云", "资源") — the search will expand the query to
        its English aliases (e.g. "高分" → "gaofen", "GF-").
    source : str
        One of ``"oscar"``, ``"eoportal"``, ``"both"`` (default).
    limit : int
        Max number of results per source.

    Returns
    -------
    list of dict
        Each dict has ``{"source": "oscar"|"eoportal", "score": int, "record": {...}}``.
    """
    queries = _expand_query(query)
    out: List[Dict[str, Any]] = []
    seen: set = set()
    if source in ("both", "oscar"):
        for q in queries:
            for score, rec in _search_records(q, all_oscar(), ["acronym", "programme"], limit):
                key = ("oscar", rec.get("acronym"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"source": "oscar", "score": score, "record": rec, "matched_query": q})
                if len([x for x in out if x["source"] == "oscar"]) >= limit:
                    break
    if source in ("both", "eoportal"):
        for q in queries:
            for score, rec in _search_records(q, all_eoportal(), ["name"], limit):
                key = ("eoportal", rec.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"source": "eoportal", "score": score, "record": rec, "matched_query": q})
                if len([x for x in out if x["source"] == "eoportal"]) >= limit:
                    break
    out.sort(key=lambda x: (-x["score"], x["record"].get("acronym") or x["record"].get("name", "")))
    return out


# Query expansion: Chinese / colloquial name -> list of alias strings to try.
# The list is ordered: try the user-supplied query first, then the
# expansions in order. Scores from the original query get a small boost.
_QUERY_EXPANSIONS: List[tuple] = [
    ("高分",   ["gaofen", "gf-", "gao fen"]),
    ("高分一号", ["gaofen-1", "gf-1", "gaofen1"]),
    ("高分二号", ["gaofen-2", "gf-2"]),
    ("高分三号", ["gaofen-3", "gf-3"]),
    ("高分四号", ["gaofen-4", "gf-4"]),
    ("高分五号", ["gaofen-5", "gf-5"]),
    ("风云",   ["fengyun", "fy-", "feng-yun"]),
    ("风云一号", ["fengyun-1", "fy-1"]),
    ("风云二号", ["fengyun-2", "fy-2"]),
    ("风云三号", ["fengyun-3", "fy-3"]),
    ("风云四号", ["fengyun-4", "fy-4"]),
    ("资源",   ["ziyuan", "zy-", "zi yuan"]),
    ("资源一号", ["ziyuan-1", "zy-1"]),
    ("资源三号", ["ziyuan-3", "zy-3"]),
    ("环境",   ["huanjing", "hj-"]),
    ("中巴",   ["cbers"]),
    ("哨兵",   ["sentinel", "s2a", "s1a"]),
    ("陆地卫星", ["landsat"]),
    ("斯波特", ["spot"]),
    ("行星",   ["planet"]),
    ("快鸟",   ["quickbird"]),
    ("世界观测", ["worldview"]),
    ("锁眼",   ["keyhole", "kh-"]),
    ("宇宙",   ["cosmos"]),
    ("地球",   ["earth"]),
    ("太阳",   ["solar", "soho"]),
    ("月球",   ["lunar", "moon", "luna"]),
    ("火星",   ["mars", "mro"]),
    ("木星",   ["jupiter", "juno"]),
    ("土星",   ["saturn", "cassini"]),
]


def _expand_query(query: str) -> List[str]:
    q = query.strip()
    out = [q]
    qn = q.lower()
    for key, expansions in _QUERY_EXPANSIONS:
        if key in q or key.lower() in qn:
            for e in expansions:
                if e not in out:
                    out.append(e)
            # also try the prefix-stripped version
            tail = q.replace(key, "").replace(key.lower(), "").strip()
            if tail and tail not in out:
                out.append(tail)
    return out


def _find_in_oscar(query: str) -> Optional[Dict[str, Any]]:
    qn = _normalize(query)
    hints = ALIAS_HINTS.get(qn, [])
    # Try alias hints first (cross-source name normalization)
    for src, cand in hints:
        if src != "oscar":
            continue
        for rec in all_oscar():
            if _normalize(rec.get("acronym", "")) == _normalize(cand):
                return rec
            if _normalize(rec.get("programme", "")) == _normalize(cand):
                return rec
    # Then direct match
    for rec in all_oscar():
        if _normalize(rec.get("acronym", "")) == qn:
            return rec
    # Then substring
    hits = _search_records(query, all_oscar(), ["acronym", "programme"], 5)
    return hits[0][1] if hits else None


def _find_in_eoportal(query: str) -> Optional[Dict[str, Any]]:
    qn = _normalize(query)
    hints = ALIAS_HINTS.get(qn, [])
    for src, cand in hints:
        if src != "eoportal":
            continue
        for rec in all_eoportal():
            if _normalize(rec.get("slug", "")) == _normalize(cand):
                return rec
            if _normalize(rec.get("name", "")) == _normalize(cand):
                return rec
    for rec in all_eoportal():
        if _normalize(rec.get("name", "")) == qn:
            return rec
    hits = _search_records(query, all_eoportal(), ["name"], 5)
    return hits[0][1] if hits else None


def info(query: str) -> Optional[MergedRecord]:
    """Look up a single satellite across both sources and merge them.

    Returns ``None`` if neither source has a match.

    If the eoportal record has a ``detail`` sub-dict (from a successful
    detail-page fetch), its fields are surfaced so ``info`` shows
    summary, FAQ, applications, etc. without re-fetching.
    """
    oscar = _find_in_oscar(query)
    eoportal = _find_in_eoportal(query)

    if oscar is None and eoportal is None:
        return None

    sources: List[str] = []
    if eoportal:
        sources.append("eoportal")
    if oscar:
        sources.append("oscar")

    # If the eoportal record carries a detail payload, lift it onto the
    # top-level eoportal dict so the rest of the merger can use it.
    eoportal_effective = eoportal
    if eoportal and eoportal.get("detail"):
        d = eoportal["detail"]
        for k in ("agency", "country", "launch_date", "end_of_life", "status",
                  "summary", "applications", "instruments", "measurement_domain",
                  "faq", "last_updated"):
            if d.get(k) is not None and not eoportal.get(k):
                eoportal = {**eoportal, k: d[k]}
        eoportal_effective = eoportal

    # Build a "merged" headline
    agency: Optional[str] = None
    if oscar and oscar.get("agencies"):
        agency = ", ".join(oscar["agencies"])
    elif eoportal_effective and eoportal_effective.get("agency"):
        agency = eoportal_effective["agency"]

    launch: Optional[str] = None
    if oscar and oscar.get("launch"):
        launch = oscar["launch"]
    elif eoportal_effective and eoportal_effective.get("launch_date"):
        launch = eoportal_effective["launch_date"]

    eol: Optional[str] = None
    if oscar and oscar.get("eol"):
        eol = oscar["eol"]
    elif eoportal_effective and eoportal_effective.get("end_of_life"):
        eol = eoportal_effective["end_of_life"]

    status: Optional[str] = None
    if oscar and oscar.get("status"):
        status = oscar["status"]
    elif eoportal_effective and eoportal_effective.get("status"):
        status = eoportal_effective["status"]

    orbit_bits: List[str] = []
    if oscar and oscar.get("orbit"):
        orbit_bits.append(str(oscar["orbit"]))
    if oscar and oscar.get("altitude"):
        orbit_bits.append(f"alt {oscar['altitude']}")
    if oscar and oscar.get("inclination"):
        orbit_bits.append(f"inc {oscar['inclination']}")
    orbit_str = ", ".join(orbit_bits) if orbit_bits else None

    instruments: List[str] = []
    if oscar and oscar.get("instruments"):
        instruments = list(oscar["instruments"])
    elif eoportal_effective and eoportal_effective.get("instruments"):
        instruments = list(eoportal_effective["instruments"])

    # The merged payload keeps the full eoportal entry (including
    # summary/faq/etc. if present) so downstream code can introspect it.
    payload_eoportal = None
    if eoportal_effective:
        payload_eoportal = {
            k: eoportal_effective[k] for k in (
                "name", "slug", "url", "agency", "country", "launch_date",
                "end_of_life", "status", "summary", "applications",
                "instruments", "measurement_domain", "faq", "last_updated",
                "taxonomy",
            ) if k in eoportal_effective
        }

    # Add merged-level extras
    payload_eoportal = payload_eoportal or None
    merged: Dict[str, Any] = {
        "agency": agency,
        "launch_date": launch,
        "end_of_life": eol,
        "status": status,
        "orbit": orbit_str,
        "instruments": instruments,
        "instruments_count": len(instruments),
        "sources_count": len(sources),
    }
    if eoportal_effective and eoportal_effective.get("summary"):
        merged["summary"] = eoportal_effective["summary"]
    if eoportal_effective and eoportal_effective.get("faq"):
        merged["faq_count"] = len(eoportal_effective["faq"])

    # Pick a canonical name
    if eoportal_effective and oscar:
        name = eoportal_effective.get("name") or oscar.get("acronym")
    elif eoportal_effective:
        name = eoportal_effective.get("name") or query
    else:
        name = oscar.get("acronym") or query

    aliases: List[str] = []
    if eoportal_effective and oscar:
        eo_name = eoportal_effective.get("name")
        os_name = oscar.get("acronym")
        if eo_name and os_name and eo_name != os_name and os_name not in aliases:
            aliases.append(os_name)
        prog = oscar.get("programme")
        if prog and prog not in aliases and prog != name:
            aliases.append(prog)

    merge_hint: Optional[str] = None
    if len(sources) == 1:
        if sources[0] == "eoportal" and not oscar:
            merge_hint = "Not in OSCAR. Search 'https://space.oscar.wmo.int' for more."
        elif sources[0] == "oscar" and not eoportal:
            merge_hint = "Not in eoPortal. Search 'https://www.eoportal.org' for more."

    return MergedRecord(
        name=name,
        aliases=aliases,
        sources=sources,
        eoportal=payload_eoportal,
        oscar=oscar,
        merged=merged,
        merge_hint=merge_hint,
    )


# ---------------------------------------------------------------------------
# List helpers
# ---------------------------------------------------------------------------

def list_satellites(source: str = "both", limit: Optional[int] = None, sort_by: str = "name") -> List[Dict[str, Any]]:
    """List satellites from the local index.

    Parameters
    ----------
    source : str
        ``"oscar"``, ``"eoportal"`` or ``"both"`` (default). When ``"both"``,
        returns the union, de-duplicated by lowercased name.
    limit : int, optional
        Cap the number of returned records.
    sort_by : str
        ``"name"`` (default) or ``"launch"`` (OSCAR only, best-effort).
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()
    if source in ("both", "oscar"):
        for rec in all_oscar():
            key = ("oscar", _normalize(rec.get("acronym", "")))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "source": "oscar",
                "name": rec.get("acronym"),
                "agency": ", ".join(rec.get("agencies") or []) or None,
                "launch": rec.get("launch"),
                "status": rec.get("status"),
                "orbit": rec.get("orbit"),
                "url": rec.get("detail_url"),
            })
    if source in ("both", "eoportal"):
        for rec in all_eoportal():
            key = ("eoportal", _normalize(rec.get("name", "")))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "source": "eoportal",
                "name": rec.get("name"),
                "agency": None,
                "launch": None,
                "status": None,
                "orbit": None,
                "url": rec.get("url"),
            })
    if sort_by == "launch":
        out.sort(key=lambda r: (r.get("launch") or "9999", r.get("name") or ""))
    else:
        out.sort(key=lambda r: r.get("name") or "")
    if limit is not None:
        out = out[:limit]
    return out


# ---------------------------------------------------------------------------
# Record-to-record deserialization
# ---------------------------------------------------------------------------

def to_eoportal_record(d: Dict[str, Any]) -> EoportalRecord:
    return EoportalRecord(
        name=d.get("name", ""),
        slug=d.get("slug", ""),
        url=d.get("url", ""),
        agency=d.get("agency"),
        country=d.get("country"),
        launch_date=d.get("launch_date"),
        end_of_life=d.get("end_of_life"),
        status=d.get("status"),
        summary=d.get("summary"),
        applications=list(d.get("applications") or []),
        instruments=list(d.get("instruments") or []),
        measurement_domain=list(d.get("measurement_domain") or []),
        faq=list(d.get("faq") or []),
        last_updated=d.get("last_updated"),
    )


def to_oscar_record(d: Dict[str, Any]) -> OscarRecord:
    return OscarRecord(
        acronym=d.get("acronym", ""),
        sat_id=int(d.get("sat_id") or 0),
        launch=d.get("launch"),
        eol=d.get("eol"),
        programme=d.get("programme"),
        agencies=list(d.get("agencies") or []),
        orbit=d.get("orbit"),
        altitude=d.get("altitude"),
        longitude=d.get("longitude"),
        inclination=d.get("inclination"),
        ect=d.get("ect"),
        status=d.get("status"),
        instruments=list(d.get("instruments") or []),
        detail_url=d.get("detail_url"),
        last_update=d.get("last_update"),
    )
