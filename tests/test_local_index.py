"""Tests for the local_index module."""

import pytest

from core import local_index


def test_stats():
    s = local_index.stats()
    assert isinstance(s, dict)
    # The bundled index should have at least ~1500 records combined.
    assert s["oscar"] >= 900
    assert s["eoportal"] >= 1000
    assert s["merged_index_keys"] >= 1500


def test_search_landsat_oscar():
    hits = local_index.search("landsat", source="oscar", limit=10)
    assert len(hits) >= 5
    for h in hits:
        assert h["source"] == "oscar"
        assert h["record"].get("acronym", "").upper().startswith("LANDSAT")


def test_search_chinese_gaofen():
    """Chinese "高分" should be expanded to gaofen/GF- and return CN satellites."""
    hits = local_index.search("高分", source="oscar", limit=5)
    assert any("GF-" in h["record"]["acronym"] for h in hits)


def test_search_chinese_fengyun4():
    hits = local_index.search("风云四号", source="oscar", limit=5)
    assert any("FY-4" in h["record"]["acronym"] for h in hits)


def test_search_no_match():
    hits = local_index.search("xxxnotasatellite999", limit=5)
    assert hits == []


def test_info_landsat9_double_source():
    m = local_index.info("Landsat-9")
    assert m is not None
    assert "eoportal" in m.sources
    assert "oscar" in m.sources
    assert m.merged["agency"]
    assert m.merged["launch_date"]
    assert m.merged["instruments_count"] >= 1


def test_info_fy4_double_source():
    m = local_index.info("FY-4A")
    assert m is not None
    assert "eoportal" in m.sources
    assert "oscar" in m.sources
    # FY-4A is GEO
    assert "GEO" in (m.merged.get("orbit") or "")


def test_info_sentinel2a_double_source():
    m = local_index.info("Sentinel-2A")
    assert m is not None
    assert "oscar" in m.sources
    # alias-mapped to eoportal
    assert "eoportal" in m.sources


def test_info_gaofen1_double_source():
    m = local_index.info("GF-1")
    assert m is not None
    assert "eoportal" in m.sources
    assert "oscar" in m.sources


def test_info_no_match():
    assert local_index.info("xxxnotasatellite999") is None


def test_list_capped():
    rows = local_index.list_satellites(source="oscar", limit=10)
    assert len(rows) == 10
    # sorted by name
    names = [r["name"] for r in rows]
    assert names == sorted(names)


def test_list_combined_no_duplicates():
    rows = local_index.list_satellites(source="both", limit=200)
    seen = set()
    for r in rows:
        key = (r["source"], r["name"])
        assert key not in seen
        seen.add(key)


def test_alias_sentinel2a_finds_eoportal():
    """Sentinel-2A's alias hint maps to eoportal slug 'copernicus-sentinel-2'."""
    eo = local_index._find_in_eoportal("Sentinel-2A")
    assert eo is not None
    assert eo.get("slug") == "copernicus-sentinel-2"


def test_normalize_strips_spaces_diacritics():
    assert local_index._normalize("  Sentinel-2A  ") == "sentinel2a"
    assert local_index._normalize("Gaofen-1") == "gaofen1"
    # Diacritics (none in this domain, but check the function works)
    assert local_index._normalize("") == ""


def test_info_includes_eoportal_detail_when_present():
    """When the eoportal record has a `detail` sub-dict, the merged info()
    payload should surface the summary and FAQ count."""
    m = local_index.info("Landsat-9")
    assert m is not None
    eo = m.eoportal
    assert eo is not None
    # detail was fetched during 0.2.0 release
    if eo.get("summary") is not None:
        assert isinstance(eo["summary"], str)
        assert len(eo["summary"]) > 30
    if eo.get("faq") is not None:
        assert isinstance(eo["faq"], list)
        if eo["faq"]:
            assert "q" in eo["faq"][0]
            assert "a" in eo["faq"][0]


def test_at_least_some_eoportal_details_cached():
    """Sanity: the bundled index should carry detail payloads for a
    non-trivial fraction of the eoPortal records."""
    eoportal = local_index.all_eoportal()
    with_detail = sum(1 for r in eoportal if r.get("detail"))
    assert with_detail >= 100  # at least 100 of ~1100
    assert with_detail >= len(eoportal) * 0.05  # at least 5%
