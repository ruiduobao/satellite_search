"""Read-only access to the bundled satellite data files.

The skill ships data files under ``data/``:

* ``oscar_satellites.jsonl``           — WMO OSCAR export (~1k missions)
* ``eoportal_satellites.jsonl``        — eoPortal catalogue (~700+ missions,
  with optional detail fields)
* ``celestrak_satellites.jsonl``       — CelesTrak SATCAT full (~70k objects,
  1957 → present)
* ``celestrak_active_payloads.jsonl``  — CelesTrak SATCAT active-payload subset
  (~16k satellites still in orbit)
* ``satnogs_all.jsonl``                — SatNOGS DB all records (~3k amateur
  / small / university satellites)
* ``satnogs_alive.jsonl``              — SatNOGS DB status=alive subset
* ``ucs_satellites.jsonl``             — UCS Satellite Database (~7.5k active)
* ``merged_index.json``                — JSON dict of ``name -> {compact
  fields}``, used for fast cross-source lookup
* ``eoportal_satellites_zh.jsonl``     — Chinese overlay for eoPortal

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
    CelestrakRecord,
    EoportalRecord,
    MergedRecord,
    OscarRecord,
    SatnogsRecord,
    UcsRecord,
    jsonl_loads,
)
from . import i18n  # noqa: E402  (for status_zh / orbit_zh in merged headline)


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
def _load_zh_translations() -> Dict[str, Dict[str, Any]]:
    """Load Chinese translations keyed by slug. Falls back to empty dict
    when the file does not exist (i.e. `translate_descriptions.py` has
    not been run yet)."""
    p = os.path.join(_data_dir(), "eoportal_satellites_zh.jsonl")
    if not os.path.exists(p):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for rec in _load_jsonl("eoportal_satellites_zh.jsonl"):
        if rec.get("slug"):
            out[rec["slug"]] = rec
    return out


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


def all_celestrak() -> List[Dict[str, Any]]:
    """Return all CelesTrak SATCAT records as raw dicts (cached)."""
    return _load_jsonl("celestrak_satellites.jsonl")


def all_celestrak_active() -> List[Dict[str, Any]]:
    """Return only CelesTrak SATCAT entries that are *active payloads*
    (OBJECT_TYPE=PAY, no DECAY_DATE). Useful for the satellite_search CLI
    to avoid listing 70k+ debris items."""
    return _load_jsonl("celestrak_active_payloads.jsonl")


def all_satnogs() -> List[Dict[str, Any]]:
    """Return all SatNOGS DB records (cached)."""
    return _load_jsonl("satnogs_all.jsonl")


def all_satnogs_alive() -> List[Dict[str, Any]]:
    """Return only SatNOGS DB entries with status=alive (cached)."""
    return _load_jsonl("satnogs_alive.jsonl")


def all_ucs() -> List[Dict[str, Any]]:
    """Return all UCS Satellite Database records as raw dicts (cached)."""
    return _load_jsonl("ucs_satellites.jsonl")


def stats() -> Dict[str, Any]:
    """Quick stats for the ``stats`` CLI command."""
    return {
        "oscar": len(all_oscar()),
        "eoportal": len(all_eoportal()),
        "celestrak_total": len(all_celestrak()),
        "celestrak_active_payloads": len(all_celestrak_active()),
        "satnogs_total": len(all_satnogs()),
        "satnogs_alive": len(all_satnogs_alive()),
        "ucs": len(all_ucs()),
        "merged_index_keys": len(_load_merged_index()),
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
    _normalize("高分二号"):    [("eoportal", "gaofen-2"), ("oscar", "GF-2")],
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


def _is_norad_id(s: str) -> Optional[int]:
    """If the query looks like a NORAD catalog number (5-6 digits), return it.
    Otherwise return None."""
    if not s:
        return None
    s = s.strip()
    if s.isdigit() and 1 <= len(s) <= 6:
        return int(s)
    return None


def search(query: str, source: str = "all", limit: int = 20) -> List[Dict[str, Any]]:
    """Search the local index for a satellite by name (case-insensitive,
    diacritic-insensitive, allows substring match).

    Parameters
    ----------
    query : str
        The satellite name or partial name. Chinese is supported (e.g.
        "高分", "风云", "资源") — the search will expand the query to
        its English aliases (e.g. "高分" → "gaofen", "GF-").

        If the query is a 1-6 digit number, it is treated as a NORAD
        catalog id and matched against ``norad_id`` / ``norad_cat_id`` /
        ``norad_number`` across all sources.

    source : str
        One of ``"all"`` (default), ``"oscar"``, ``"eoportal"``,
        ``"celestrak"``, ``"satnogs"``, ``"ucs"`` — limits the search to
        the chosen source. ``"all"`` searches every source.
    limit : int
        Max number of results per source.

    Returns
    -------
    list of dict
        Each dict has ``{"source": "<name>", "score": int, "record": {...},
        "matched_query": "<expanded query that hit>"}``.
    """
    queries = _expand_query(query)
    out: List[Dict[str, Any]] = []
    seen: set = set()
    norad_q = _is_norad_id(query)

    def _push(source_name: str, key: tuple, score: int, rec: dict, q: str) -> None:
        if key in seen:
            return
        seen.add(key)
        out.append({"source": source_name, "score": score, "record": rec, "matched_query": q})

    # OSCAR
    if source in ("all", "oscar"):
        for q in queries:
            for score, rec in _search_records(q, all_oscar(), ["acronym", "programme"], limit):
                _push("oscar", ("oscar", rec.get("acronym")), score, rec, q)
                if len([x for x in out if x["source"] == "oscar"]) >= limit:
                    break
    # eoPortal
    if source in ("all", "eoportal"):
        for q in queries:
            for score, rec in _search_records(q, all_eoportal(), ["name"], limit):
                _push("eoportal", ("eoportal", rec.get("name")), score, rec, q)
                if len([x for x in out if x["source"] == "eoportal"]) >= limit:
                    break
    # CelesTrak (active payloads only — much faster than searching 70k debris)
    if source in ("all", "celestrak"):
        # First try name match (limited to active payloads to stay snappy)
        for q in queries:
            for score, rec in _search_records(q, all_celestrak_active(), ["OBJECT_NAME"], limit):
                _push("celestrak", ("celestrak", rec.get("NORAD_CAT_ID")), score, rec, q)
                if len([x for x in out if x["source"] == "celestrak"]) >= limit:
                    break
        # Also try NORAD id direct lookup (works for both active and decayed)
        if norad_q is not None:
            for rec in all_celestrak():
                if rec.get("NORAD_CAT_ID") == norad_q:
                    _push("celestrak", ("celestrak", norad_q), 1000, rec, query)
                    break
    # SatNOGS (alive only)
    if source in ("all", "satnogs"):
        for q in queries:
            for score, rec in _search_records(q, all_satnogs_alive(), ["name"], limit):
                _push("satnogs", ("satnogs", rec.get("sat_id")), score, rec, q)
                if len([x for x in out if x["source"] == "satnogs"]) >= limit:
                    break
        if norad_q is not None:
            for rec in all_satnogs():
                if rec.get("norad_cat_id") == norad_q:
                    _push("satnogs", ("satnogs", rec.get("sat_id")), 1000, rec, query)
                    break
    # UCS
    if source in ("all", "ucs"):
        for q in queries:
            for score, rec in _search_records(q, all_ucs(), ["Name"], limit):
                _push("ucs", ("ucs", rec.get("NORAD Number") or rec.get("Name")), score, rec, q)
                if len([x for x in out if x["source"] == "ucs"]) >= limit:
                    break
        if norad_q is not None:
            for rec in all_ucs():
                if rec.get("NORAD Number") == norad_q:
                    _push("ucs", ("ucs", rec.get("NORAD Number")), 1000, rec, query)
                    break

    out.sort(key=lambda x: (-x["score"], x["record"].get("acronym") or x["record"].get("name") or x["record"].get("Name") or x["record"].get("OBJECT_NAME") or ""))
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
    for src, cand in hints:
        if src != "oscar":
            continue
        for rec in all_oscar():
            if _normalize(rec.get("acronym", "")) == _normalize(cand):
                return rec
            if _normalize(rec.get("programme", "")) == _normalize(cand):
                return rec
    for rec in all_oscar():
        if _normalize(rec.get("acronym", "")) == qn:
            return rec
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
    zh = _load_zh_translations()
    for rec in all_eoportal():
        zt = zh.get(rec.get("slug", ""), {})
        if zt.get("name_zh") and _normalize(zt["name_zh"]) == qn:
            return rec
    hits = _search_records(query, all_eoportal(), ["name"], 5)
    if not hits and zh:
        cands = []
        for rec in all_eoportal():
            zt = zh.get(rec.get("slug", ""), {})
            if zt.get("name_zh") and _normalize(zt["name_zh"]) == qn:
                cands.append(rec)
        if cands:
            return cands[0]
    return hits[0][1] if hits else None


def _find_norad_in_celestrak(norad_id: int) -> Optional[Dict[str, Any]]:
    """NORAD-id direct lookup in the full CelesTrak SATCAT (70k entries)."""
    for rec in all_celestrak():
        if rec.get("NORAD_CAT_ID") == norad_id:
            return rec
    return None


def _find_norad_in_satnogs(norad_id: int) -> Optional[Dict[str, Any]]:
    """NORAD-id direct lookup in SatNOGS DB."""
    for rec in all_satnogs():
        if rec.get("norad_cat_id") == norad_id:
            return rec
    return None


def _find_norad_in_ucs(norad_id: int) -> Optional[Dict[str, Any]]:
    """NORAD-id direct lookup in UCS Satellite Database."""
    for rec in all_ucs():
        if rec.get("NORAD Number") == norad_id:
            return rec
    return None


def _find_in_celestrak(query: str) -> Optional[Dict[str, Any]]:
    """Find a CelesTrak record by name (limited to active payloads) or by
    NORAD id. Returns the record dict or None."""
    norad = _is_norad_id(query)
    if norad is not None:
        rec = _find_norad_in_celestrak(norad)
        if rec:
            return rec
    # Substring search against active payloads first
    hits = _search_records(query, all_celestrak_active(), ["OBJECT_NAME"], 3)
    if hits:
        return hits[0][1]
    return None


def _find_in_satnogs(query: str) -> Optional[Dict[str, Any]]:
    norad = _is_norad_id(query)
    if norad is not None:
        rec = _find_norad_in_satnogs(norad)
        if rec:
            return rec
    hits = _search_records(query, all_satnogs_alive(), ["name"], 3)
    return hits[0][1] if hits else None


def _find_in_ucs(query: str) -> Optional[Dict[str, Any]]:
    norad = _is_norad_id(query)
    if norad is not None:
        rec = _find_norad_in_ucs(norad)
        if rec:
            return rec
    hits = _search_records(query, all_ucs(), ["Name"], 3)
    return hits[0][1] if hits else None


def info(query: str) -> Optional[MergedRecord]:
    """Look up a single satellite across all sources and merge them.

    Returns ``None`` if no source has a match.

    The search order is: eoPortal → OSCAR → CelesTrak (NORAD id) →
    SatNOGS (NORAD id) → UCS (NORAD id). When the initial name-based
    search hits one of the rich-content sources (eoPortal / OSCAR) and
    that record has a NORAD id, we additionally pull CelesTrak / SatNOGS /
    UCS by NORAD id so the merged payload has orbital parameters, owner
    country, amateur-sat details, etc.

    Chinese translations (``eoportal_satellites_zh.jsonl``) are overlaid
    on top of the eoPortal record when present, so the merged payload
    always has both ``*_zh`` (preferred) and ``*_en`` (original) fields.
    """
    oscar = _find_in_oscar(query)
    eoportal = _find_in_eoportal(query)
    celestrak = _find_in_celestrak(query)
    satnogs = _find_in_satnogs(query)
    ucs = _find_in_ucs(query)

    # If we hit eoPortal or OSCAR but didn't get celestrak/satnogs/ucs by
    # name, try the NORAD-id cross-reference. This is the key win of
    # having all five sources — the rich content from eoPortal/OSCAR gets
    # combined with the orbital/owner data from CelesTrak.
    norad_hint: Optional[int] = None
    if eoportal and eoportal.get("norad_id"):
        try:
            norad_hint = int(eoportal["norad_id"])
        except (ValueError, TypeError):
            pass
    if not norad_hint and oscar:
        # OSCAR sat_id is the WMO internal id, not NORAD. We try a name
        # search in CelesTrak with the OSCAR acronym as a fallback.
        oscar_name = oscar.get("acronym")
        if oscar_name and not celestrak:
            celestrak = _find_in_celestrak(oscar_name)
        if oscar_name and not satnogs:
            satnogs = _find_in_satnogs(oscar_name)
    if norad_hint:
        if not celestrak:
            celestrak = _find_norad_in_celestrak(norad_hint)
        if not satnogs:
            satnogs = _find_norad_in_satnogs(norad_hint)
        if not ucs:
            ucs = _find_norad_in_ucs(norad_hint)

    # If still nothing in celestrak but we have a name match from
    # satnogs/ucs/celestrak, propagate the NORAD id for the cross-ref.
    if not norad_hint:
        for r in (celestrak, satnogs, ucs):
            if r:
                rid = r.get("NORAD_CAT_ID") or r.get("norad_cat_id") or r.get("NORAD Number")
                if rid:
                    norad_hint = int(rid)
                    break

    if not any([oscar, eoportal, celestrak, satnogs, ucs]):
        return None

    sources: List[str] = []
    for s_name, s_val in (("eoportal", eoportal), ("oscar", oscar),
                          ("celestrak", celestrak), ("satnogs", satnogs),
                          ("ucs", ucs)):
        if s_val:
            sources.append(s_name)

    eoportal_effective = eoportal
    if eoportal and eoportal.get("detail"):
        d = eoportal["detail"]
        for k in ("agency", "country", "launch_date", "end_of_life", "status",
                  "summary", "applications", "instruments", "measurement_domain",
                  "faq", "last_updated"):
            if d.get(k) is not None and not eoportal.get(k):
                eoportal = {**eoportal, k: d[k]}
        eoportal_effective = eoportal

    # Overlay Chinese translations (eoportal_satellites_zh.jsonl)
    zh_rec: Dict[str, Any] = {}
    if eoportal_effective:
        slug = eoportal_effective.get("slug")
        if slug:
            zh_rec = _load_zh_translations().get(slug, {})

    if zh_rec and eoportal_effective:
        zh_overlay: Dict[str, Any] = {}
        if zh_rec.get("name_zh") and not eoportal_effective.get("name_zh"):
            zh_overlay["name_zh"] = zh_rec["name_zh"]
        if zh_rec.get("agency_zh"):
            zh_overlay["agency_zh"] = zh_rec["agency_zh"]
        if zh_rec.get("status_zh"):
            zh_overlay["status_zh"] = zh_rec["status_zh"]
        if zh_rec.get("summary_zh") and eoportal_effective.get("summary"):
            zh_overlay["summary_zh"] = zh_rec["summary_zh"]
            zh_overlay["summary_en"] = eoportal_effective["summary"]
        if zh_rec.get("applications_zh") and eoportal_effective.get("applications"):
            zh_overlay["applications_zh"] = list(zh_rec["applications_zh"])
            zh_overlay["applications_en"] = list(eoportal_effective["applications"])
        if zh_rec.get("faq_zh") and eoportal_effective.get("faq"):
            zh_overlay["faq_zh"] = list(zh_rec["faq_zh"])
            zh_overlay["faq_en"] = list(eoportal_effective["faq"])
        eoportal_effective = {**eoportal_effective, **zh_overlay}

    # Build a "merged" headline
    agency: Optional[str] = None
    if oscar and oscar.get("agencies"):
        agency = ", ".join(oscar["agencies"])
    elif ucs and ucs.get("Operator/Owner"):
        agency = ucs["Operator/Owner"]
    elif eoportal_effective and eoportal_effective.get("agency"):
        agency = eoportal_effective["agency"]

    launch: Optional[str] = None
    if oscar and oscar.get("launch"):
        launch = oscar["launch"]
    elif eoportal_effective and eoportal_effective.get("launch_date"):
        launch = eoportal_effective["launch_date"]
    elif ucs and ucs.get("Date of Launch"):
        launch = ucs["Date of Launch"]
    elif celestrak and celestrak.get("LAUNCH_DATE"):
        launch = celestrak["LAUNCH_DATE"]

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
    elif satnogs and satnogs.get("status"):
        status = satnogs["status"]
    elif celestrak and celestrak.get("OPS_STATUS_CODE"):
        status = celestrak["OPS_STATUS_CODE"]

    orbit_bits: List[str] = []
    if oscar and oscar.get("orbit"):
        orbit_bits.append(str(oscar["orbit"]))
    if oscar and oscar.get("altitude"):
        orbit_bits.append(f"alt {oscar['altitude']}")
    if oscar and oscar.get("inclination"):
        orbit_bits.append(f"inc {oscar['inclination']}")
    if not orbit_bits and celestrak:
        if celestrak.get("ORBIT_CENTER"):
            oc = celestrak["ORBIT_CENTER"]
            orbit_bits.append(f"center={oc}")
        if celestrak.get("PERIOD"):
            orbit_bits.append(f"period={celestrak['PERIOD']}min")
        if celestrak.get("INCLINATION"):
            orbit_bits.append(f"inc={celestrak['INCLINATION']}°")
    if not orbit_bits and ucs:
        if ucs.get("Class of Orbit"):
            orbit_bits.append(str(ucs["Class of Orbit"]))
        if ucs.get("Perigee (km)") and ucs.get("Apogee (km)"):
            orbit_bits.append(f"perigee={ucs['Perigee (km)']}km apogee={ucs['Apogee (km)']}km")
    orbit_str = ", ".join(orbit_bits) if orbit_bits else None

    if status:
        status_zh = i18n.status_zh(status) if status else None
    else:
        status_zh = None
    if orbit_str:
        first = orbit_str.split(",")[0].strip()
        translated = i18n.orbit_zh(first) or first
        orbit_str_zh = orbit_str.replace(first, translated, 1) if translated != first else orbit_str
    else:
        orbit_str_zh = None

    instruments: List[str] = []
    if oscar and oscar.get("instruments"):
        instruments = list(oscar["instruments"])
    elif eoportal_effective and eoportal_effective.get("instruments"):
        instruments = list(eoportal_effective["instruments"])

    # Build per-source payloads
    payload_eoportal = None
    if eoportal_effective:
        payload_eoportal = {
            k: eoportal_effective[k] for k in (
                "name", "name_zh", "slug", "url", "agency", "agency_zh",
                "country", "launch_date", "end_of_life",
                "status", "status_zh", "summary", "summary_zh", "summary_en",
                "applications", "applications_zh", "applications_en",
                "instruments", "measurement_domain",
                "faq", "faq_zh", "faq_en", "last_updated", "taxonomy",
            ) if k in eoportal_effective
        }

    payload_celestrak = None
    if celestrak:
        # Build a compact, Chinese-friendly view
        owner_code = celestrak.get("OWNER")
        owner_zh = i18n.country_zh(owner_code)
        type_zh = i18n.celestrak_object_type_zh(celestrak.get("OBJECT_TYPE"))
        center_zh = i18n.celestrak_orbit_center_zh(celestrak.get("ORBIT_CENTER"))
        type_ot_zh = i18n.celestrak_orbit_type_zh(celestrak.get("ORBIT_TYPE"))
        payload_celestrak = dict(celestrak)  # keep all original fields
        payload_celestrak["owner_zh"] = owner_zh
        payload_celestrak["object_type_zh"] = type_zh
        payload_celestrak["orbit_center_zh"] = center_zh
        payload_celestrak["orbit_type_zh"] = type_ot_zh
        payload_celestrak["is_active_payload"] = (
            celestrak.get("OBJECT_TYPE") == "PAY" and not celestrak.get("DECAY_DATE")
        )

    payload_satnogs = None
    if satnogs:
        payload_satnogs = dict(satnogs)
        if satnogs.get("status"):
            payload_satnogs["status_zh"] = i18n.satnogs_status_zh(satnogs["status"])

    payload_ucs = None
    if ucs:
        payload_ucs = dict(ucs)
        if ucs.get("Class of Orbit"):
            payload_ucs["orbit_class_zh"] = i18n.ucs_orbit_class_zh(ucs["Class of Orbit"])
        if ucs.get("Purpose"):
            payload_ucs["purpose_zh"] = i18n.ucs_purpose_zh(ucs["Purpose"])

    merged: Dict[str, Any] = {
        "agency": agency,
        "launch_date": launch,
        "end_of_life": eol,
        "status": status,
        "status_zh": status_zh,
        "orbit": orbit_str,
        "orbit_zh": orbit_str_zh,
        "instruments": instruments,
        "instruments_count": len(instruments),
        "sources_count": len(sources),
    }
    if eoportal_effective:
        if eoportal_effective.get("summary_zh"):
            merged["summary_zh"] = eoportal_effective["summary_zh"]
        if eoportal_effective.get("summary_en"):
            merged["summary_en"] = eoportal_effective["summary_en"]
        if eoportal_effective.get("faq_zh"):
            merged["faq_zh_count"] = len(eoportal_effective["faq_zh"])
    # Country from any source
    if celestrak and celestrak.get("OWNER"):
        merged["owner_country"] = celestrak["OWNER"]
        merged["owner_country_zh"] = i18n.country_zh(celestrak["OWNER"])
    elif ucs and ucs.get("Country of Operator/Owner"):
        merged["owner_country"] = ucs["Country of Operator/Owner"]
    # NORAD id (if we have one)
    if norad_hint:
        merged["norad_id"] = norad_hint

    # Canonical name
    if eoportal_effective and oscar:
        name = eoportal_effective.get("name") or oscar.get("acronym")
    elif eoportal_effective:
        name = eoportal_effective.get("name") or query
    elif oscar:
        name = oscar.get("acronym") or query
    elif celestrak:
        name = celestrak.get("OBJECT_NAME") or query
    elif satnogs:
        name = satnogs.get("name") or query
    elif ucs:
        name = ucs.get("Name") or query
    else:
        name = query

    name_zh: Optional[str] = eoportal_effective.get("name_zh") if eoportal_effective else None

    aliases: List[str] = []
    for r, key in ((eoportal_effective, "name"), (oscar, "acronym"),
                    (celestrak, "OBJECT_NAME"), (satnogs, "name"),
                    (ucs, "Name")):
        if not r:
            continue
        v = r.get(key)
        if v and v != name and v not in aliases:
            aliases.append(v)

    merge_hint: Optional[str] = None
    if len(sources) == 1:
        if sources[0] == "eoportal":
            merge_hint = "OSCAR / CelesTrak / SatNOGS / UCS 中暂无对应记录"
        elif sources[0] == "oscar":
            merge_hint = "eoPortal / CelesTrak / SatNOGS / UCS 中暂无对应记录"
        elif sources[0] == "celestrak":
            merge_hint = "eoPortal / OSCAR 等详细目录中暂无对应记录"
        elif sources[0] == "satnogs":
            merge_hint = "eoPortal / OSCAR / CelesTrak / UCS 中暂无对应记录"
        elif sources[0] == "ucs":
            merge_hint = "eoPortal / OSCAR 等详细目录中暂无对应记录"

    return MergedRecord(
        name=name,
        name_zh=name_zh,
        aliases=aliases,
        sources=sources,
        norad_id=norad_hint,
        eoportal=payload_eoportal,
        oscar=oscar,
        celestrak=payload_celestrak,
        satnogs=payload_satnogs,
        ucs=payload_ucs,
        merged=merged,
        merge_hint=merge_hint,
    )


# ---------------------------------------------------------------------------
# List helpers
# ---------------------------------------------------------------------------

def list_satellites(source: str = "both", limit: Optional[int] = None,
                    sort_by: str = "name") -> List[Dict[str, Any]]:
    """List satellites from the local index.

    Parameters
    ----------
    source : str
        ``"both"`` (default) for the curated eoPortal+OSCAR list, or
        one of the explicit source names: ``"oscar"``, ``"eoportal"``,
        ``"celestrak"`` (active payloads), ``"satnogs"`` (alive), ``"ucs"``,
        or ``"all"`` to include every source.
    limit : int, optional
        Cap the number of returned records.
    sort_by : str
        ``"name"`` (default) or ``"launch"`` (best-effort).
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()

    if source in ("both", "all", "oscar"):
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
    if source in ("both", "all", "eoportal"):
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
    if source in ("all", "celestrak"):
        for rec in all_celestrak_active():
            key = ("celestrak", rec.get("NORAD_CAT_ID"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "source": "celestrak",
                "name": rec.get("OBJECT_NAME"),
                "norad_id": rec.get("NORAD_CAT_ID"),
                "agency": rec.get("OWNER"),
                "launch": rec.get("LAUNCH_DATE"),
                "status": "active" if not rec.get("DECAY_DATE") else "decayed",
                "orbit": rec.get("ORBIT_CENTER"),
                "url": f"https://celestrak.org/satcat/records.php?CATNR={rec.get('NORAD_CAT_ID')}",
            })
    if source in ("all", "satnogs"):
        for rec in all_satnogs_alive():
            key = ("satnogs", rec.get("sat_id"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "source": "satnogs",
                "name": rec.get("name"),
                "norad_id": rec.get("norad_cat_id"),
                "agency": rec.get("operator"),
                "launch": rec.get("launched"),
                "status": rec.get("status"),
                "orbit": None,
                "url": f"https://db.satnogs.org/satellite/{rec.get('sat_id')}",
            })
    if source in ("all", "ucs"):
        for rec in all_ucs():
            key = ("ucs", rec.get("NORAD Number") or rec.get("Name"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "source": "ucs",
                "name": rec.get("Name"),
                "norad_id": rec.get("NORAD Number"),
                "agency": rec.get("Operator/Owner"),
                "launch": rec.get("Date of Launch"),
                "status": "active",
                "orbit": rec.get("Class of Orbit"),
                "url": f"https://www.ucs.org/resources/satellite-database",
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


def to_celestrak_record(d: Dict[str, Any]) -> CelestrakRecord:
    return CelestrakRecord(
        name=d.get("OBJECT_NAME", d.get("name", "")),
        norad_id=int(d.get("NORAD_CAT_ID") or d.get("norad_id") or 0),
        intl_designator=d.get("OBJECT_ID") or d.get("intl_designator"),
        object_type=d.get("OBJECT_TYPE") or d.get("object_type"),
        ops_status=d.get("OPS_STATUS_CODE") or d.get("ops_status"),
        owner=d.get("OWNER") or d.get("owner"),
        launch_date=d.get("LAUNCH_DATE") or d.get("launch_date"),
        launch_site=d.get("LAUNCH_SITE") or d.get("launch_site"),
        decay_date=d.get("DECAY_DATE") or d.get("decay_date"),
        period_min=d.get("PERIOD") or d.get("period_min"),
        inclination_deg=d.get("INCLINATION") or d.get("inclination_deg"),
        apogee_km=d.get("APOGEE") or d.get("apogee_km"),
        perigee_km=d.get("PERIGEE") or d.get("perigee_km"),
        rcs_m2=d.get("RCS") or d.get("rcs_m2"),
        orbit_center=d.get("ORBIT_CENTER") or d.get("orbit_center"),
        orbit_type=d.get("ORBIT_TYPE") or d.get("orbit_type"),
    )


def to_satnogs_record(d: Dict[str, Any]) -> SatnogsRecord:
    return SatnogsRecord(
        name=d.get("name", ""),
        sat_id=d.get("sat_id", ""),
        norad_cat_id=d.get("norad_cat_id"),
        status=d.get("status"),
        launched=d.get("launched"),
        deployed=d.get("deployed"),
        operator=d.get("operator"),
        countries=d.get("countries"),
        website=d.get("website"),
        citation=d.get("citation"),
        image=d.get("image"),
    )


def to_ucs_record(d: Dict[str, Any]) -> UcsRecord:
    def _f(k: str) -> Optional[float]:
        v = d.get(k)
        if v in (None, "", "null", "None"):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None
    return UcsRecord(
        name=d.get("Name", ""),
        norad_number=d.get("NORAD Number"),
        country=d.get("Country of Operator/Owner"),
        operator=d.get("Operator/Owner"),
        users=d.get("Users"),
        purpose=d.get("Purpose"),
        orbit_class=d.get("Class of Orbit"),
        orbit_type=d.get("Type of Orbit"),
        perigee_km=_f("Perigee (km)"),
        apogee_km=_f("Apogee (km)"),
        eccentricity=_f("Eccentricity"),
        inclination_deg=_f("Inclination (degrees)"),
        period_min=_f("Period (minutes)"),
        launch_mass_kg=_f("Launch Mass (kg)"),
        dry_mass_kg=_f("Dry Mass (kg)"),
        power_w=_f("Power (Watts)"),
        launch_date=d.get("Date of Launch"),
        expected_lifetime_yrs=_f("Expected Lifetime (yrs)"),
        contractor=d.get("Contractor"),
        contractor_country=d.get("Country of Contractor"),
        launch_site=d.get("Launch Site"),
        launch_vehicle=d.get("Launch Vehicle"),
        cospar_number=d.get("COSPAR Number"),
        comments=d.get("Comments"),
    )
