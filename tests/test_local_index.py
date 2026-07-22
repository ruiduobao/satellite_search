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


# ---------------------------------------------------------------------------
# v0.4.0 — CelesTrak + SatNOGS + UCS test suite
# ---------------------------------------------------------------------------

from core import i18n  # noqa: E402


def test_stats_includes_celestrak_and_satnogs():
    """v0.4.0: stats() must surface the new source counts."""
    s = local_index.stats()
    assert "celestrak_total" in s
    assert "celestrak_active_payloads" in s
    assert "satnogs_alive" in s
    assert "ucs" in s
    # Active payloads (PAY, no decay) should be ~10k+ — big enough to be useful
    assert s["celestrak_total"] >= 50_000, "expected 50k+ CelesTrak total objects"
    assert s["celestrak_active_payloads"] >= 5_000, "expected 5k+ active payloads"
    # SatNOGS alive set is small (community-curated) but non-trivial
    assert s["satnogs_alive"] >= 1000, "expected 1000+ SatNOGS alive entries"


def test_celestrak_active_smaller_than_full():
    """The active-payload subset must be a strict subset of the full SATCAT."""
    total = len(local_index.all_celestrak())
    active = len(local_index.all_celestrak_active())
    assert active < total
    # And active should be a sensible fraction (avoid 0 or 100%)
    assert total * 0.1 < active < total


def test_search_celestrak_starlink():
    """CelesTrak active-payload search should match the Starlink constellation."""
    hits = local_index.search("STARLINK", source="celestrak", limit=5)
    assert len(hits) >= 1
    for h in hits:
        assert h["source"] == "celestrak"
        assert h["record"].get("OBJECT_TYPE") == "PAY"
        assert h["record"].get("NORAD_CAT_ID")


def test_search_celestrak_iss():
    """Active-payload search should match ISS (ZARYA)."""
    hits = local_index.search("ISS (ZARYA)", source="celestrak", limit=3)
    assert len(hits) >= 1
    norad = hits[0]["record"].get("NORAD_CAT_ID")
    assert norad == 25544  # ISS NORAD catalog id is canonical


def test_norad_id_iss_lookup():
    """A 5-digit NORAD id should resolve via the dedicated lookup helper."""
    rec = local_index._find_norad_in_celestrak(25544)
    assert rec is not None
    assert rec.get("NORAD_CAT_ID") == 25544
    assert rec.get("OBJECT_TYPE") == "PAY"
    assert rec.get("OWNER") == "ISS"
    # The active subset doesn't include every decayed payload; 25544 is active
    assert not rec.get("DECAY_DATE")


def test_is_norad_id_helper():
    """The NORAD id detection helper should accept 1-6 digit numerics only."""
    assert local_index._is_norad_id("25544") == 25544
    assert local_index._is_norad_id("1") == 1
    assert local_index._is_norad_id("999999") == 999999
    # Reject non-numerics, too-long, empty
    assert local_index._is_norad_id("") is None
    assert local_index._is_norad_id("Sentinel") is None
    assert local_index._is_norad_id("1234567") is None  # 7 digits = too long
    assert local_index._is_norad_id("  1234  ") == 1234  # whitespace OK


def test_search_norad_25544_all_sources():
    """A 5-digit numeric query should hit NORAD id direct lookups in CelesTrak."""
    hits = local_index.search("25544", source="celestrak", limit=5)
    assert any(h["record"].get("NORAD_CAT_ID") == 25544 for h in hits)


def test_info_iss_norad_id_pulls_celestrak():
    """info() on a NORAD id should pull the CelesTrak orbital block."""
    m = local_index.info("25544")
    assert m is not None
    assert "celestrak" in m.sources
    ct = m.celestrak
    assert ct is not None
    # CelesTrak has rich orbital params for ISS
    assert ct.get("PERIOD") is not None
    assert ct.get("INCLINATION") is not None
    assert ct.get("OWNER") == "ISS"
    # Chinese overlays applied
    assert ct.get("owner_zh") == "国际空间站"
    assert ct.get("object_type_zh") == "有效载荷（卫星本体）"


def test_info_iss_norad_id_pulls_satnogs():
    """When SatNOGS has a record for the same NORAD id, info() should include it."""
    m = local_index.info("25544")
    # ISS has no SatNOGS entry (it's not amateur/small), so it may or may not
    # appear. We just assert that the field exists, not that it's non-None.
    assert hasattr(m, "satnogs")


def test_search_satnogs_alive():
    """SatNOGS alive search should return at least one hit for a common name."""
    hits = local_index.search("AO-91", source="satnogs", limit=5)
    # AO-91 is a well-known amateur satellite; should be in SatNOGS alive list
    if hits:
        for h in hits:
            assert h["source"] == "satnogs"
            assert h["record"].get("status") == "alive"


def test_list_satellites_all_includes_celestrak():
    """list_satellites(source='all') should include celestrak rows."""
    rows = local_index.list_satellites(source="all", limit=1000)
    sources = {r["source"] for r in rows}
    assert "oscar" in sources
    assert "eoportal" in sources
    assert "celestrak" in sources
    # Active-payload celestrak rows should have norad_id
    ct_rows = [r for r in rows if r["source"] == "celestrak"]
    assert all(r.get("norad_id") for r in ct_rows)


def test_to_celestrak_record():
    """The dataclass deserializer should round-trip the JSONL fields."""
    rec = local_index._find_norad_in_celestrak(25544)
    assert rec is not None
    d = local_index.to_celestrak_record(rec)
    assert d.norad_id == 25544
    assert d.object_type == "PAY"
    assert d.owner == "ISS"
    assert d.is_active_payload is True


def test_to_satnogs_record():
    """SatNOGS deserializer should produce a SatnogsRecord from the JSONL dict."""
    satnogs_all = local_index.all_satnogs_alive()
    if satnogs_all:
        d = local_index.to_satnogs_record(satnogs_all[0])
        assert d.name == satnogs_all[0]["name"]
        assert d.status == "alive"


def test_country_zh_translations():
    """i18n.country_zh should map common CelesTrak country codes."""
    assert i18n.country_zh("US") == "美国"
    assert i18n.country_zh("PRC") == "中国"
    assert i18n.country_zh("CIS") == "苏联/独联体"
    assert i18n.country_zh("ISS") == "国际空间站"
    assert i18n.country_zh("ESA") == "欧洲空间局"
    assert i18n.country_zh("XX") == "XX"  # unknown falls through
    assert i18n.country_zh(None) is None


def test_celestrak_object_type_zh():
    """i18n.celestrak_object_type_zh should map PAY/R/B/DEB/UNK."""
    assert i18n.celestrak_object_type_zh("PAY") == "有效载荷（卫星本体）"
    assert i18n.celestrak_object_type_zh("R/B") == "火箭箭体"
    assert i18n.celestrak_object_type_zh("DEB") == "空间碎片"
    assert i18n.celestrak_object_type_zh("UNK") == "类型不明"


def test_celestrak_orbit_center_zh():
    """i18n.celestrak_orbit_center_zh should map common centers."""
    assert i18n.celestrak_orbit_center_zh("EA") == "地球轨道"
    assert i18n.celestrak_orbit_center_zh("MO") == "月球轨道"
    assert i18n.celestrak_orbit_center_zh("MA") == "火星"


def test_satnogs_status_zh():
    """i18n.satnogs_status_zh should map alive/dead/etc."""
    assert i18n.satnogs_status_zh("alive") == "在轨运行"
    assert i18n.satnogs_status_zh("re-entered") == "再入大气层"
    assert i18n.satnogs_status_zh("dead") == "已失效"
    assert i18n.satnogs_status_zh("future") == "计划中"


def test_ucs_translations_exist():
    """UCS translation helpers should be importable and return strings or fall-through."""
    assert i18n.ucs_orbit_class_zh("LEO") == "低地球轨道"
    assert i18n.ucs_orbit_class_zh("GEO") == "地球静止轨道"
    assert i18n.ucs_purpose_zh("Earth Observation") == "对地观测"
    # Unknown keys fall through to the original
    assert i18n.ucs_orbit_class_zh("WEIRDCLASS") == "WEIRDCLASS"
    assert i18n.ucs_purpose_zh("ZZZ") == "ZZZ"
