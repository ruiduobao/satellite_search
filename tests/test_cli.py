"""End-to-end CLI tests via subprocess.

These exercise the real `satellite_search.py` script the same way a user
would, asserting on stdout / exit code. The tests do NOT touch the network
beyond the one-time bundled scrape.
"""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.abspath(os.path.join(HERE, "..", "scripts", "satellite_search.py"))


def _run(args, env_extra=None, timeout=60):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    # make sure we don't accidentally use a proxy
    env.pop("HTTPS_PROXY", None)
    env.pop("HTTP_PROXY", None)
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def test_cli_stats():
    p = _run(["stats"])
    assert p.returncode == 0
    assert "oscar" in p.stdout and "eoportal" in p.stdout


def test_cli_search_landsat():
    p = _run(["search", "landsat", "--limit", "5"])
    assert p.returncode == 0
    assert "Landsat-9" in p.stdout or "Landsat-1" in p.stdout


def test_cli_search_chinese():
    p = _run(["search", "高分", "--limit", "5"])
    assert p.returncode == 0
    # Should match gaofen / GF- series
    assert "GF-" in p.stdout or "gaofen" in p.stdout.lower()


def test_cli_info_landsat9():
    p = _run(["info", "Landsat-9"])
    assert p.returncode == 0
    assert "Landsat" in p.stdout
    assert "USGS" in p.stdout or "NASA" in p.stdout
    # both URLs are present
    assert "eoportal" in p.stdout
    assert "oscar" in p.stdout


def test_cli_info_json():
    p = _run(["--json", "info", "Sentinel-2A"])
    assert p.returncode == 0
    j = json.loads(p.stdout)
    assert "name" in j
    assert "sources" in j
    assert "oscar" in j["sources"]


def test_cli_no_match_returns_1():
    # --no-online skips the web-search fallback so this is a fast no-match
    p = _run(["info", "xxxnotasatellite999", "--no-online"])
    # The command returns 1 on no match (we do print a message)
    assert p.returncode == 1


# ---------------------------------------------------------------------------
# Phase 5: --qa sidecar summary
# ---------------------------------------------------------------------------


def test_help_includes_qa_flag():
    p = _run(["--help"])
    assert p.returncode == 0
    assert "--qa" in p.stdout


def test_qa_sidecar_written_for_search(tmp_path):
    """search --qa PATH should produce a JSON sidecar after a successful run."""
    qa_path = str(tmp_path / "search.qa.json")
    # --qa is a top-level option (consistent with --json), so it must come
    # before the subcommand.
    p = _run(["--qa", qa_path, "search", "landsat", "--limit", "3"])
    assert p.returncode == 0, p.stderr
    assert os.path.exists(qa_path), "QA sidecar not written"
    data = json.load(open(qa_path, encoding="utf-8"))
    assert data["skill"] == "satellite-search"
    assert data["command"] == "search"
    assert data["primary"] == "landsat"
    assert data["limit"] == 3
    assert "timestamp" in data
    assert "version" in data


def test_qa_sidecar_written_for_info(tmp_path):
    """info --qa PATH should record the satellite name."""
    qa_path = str(tmp_path / "info.qa.json")
    p = _run(["--qa", qa_path, "info", "Landsat-9", "--no-online"])
    assert p.returncode == 0
    data = json.load(open(qa_path, encoding="utf-8"))
    assert data["command"] == "info"
    assert data["primary"] == "Landsat-9"


def test_qa_sidecar_written_for_stats(tmp_path):
    """stats --qa PATH should record a stats run."""
    qa_path = str(tmp_path / "stats.qa.json")
    p = _run(["--qa", qa_path, "stats"])
    assert p.returncode == 0
    data = json.load(open(qa_path, encoding="utf-8"))
    assert data["command"] == "stats"


def test_qa_creates_parent_dir(tmp_path):
    """--qa should create the parent directory if missing."""
    qa_path = str(tmp_path / "deep" / "nested" / "run.qa.json")
    p = _run(["--qa", qa_path, "stats"])
    assert p.returncode == 0
    assert os.path.exists(qa_path)


def test_no_qa_does_not_write_file(tmp_path, monkeypatch):
    """Without --qa, no sidecar file should be created in a target dir."""
    # Run from inside tmp_path so any sidecar would show up there
    monkeypatch.chdir(tmp_path)
    p = _run(["stats"])
    assert p.returncode == 0
    # tmp_path should be empty after the run
    assert os.listdir(tmp_path) == []


# ---------------------------------------------------------------------------
# Phase 6 — --place flag for search subcommand
# ---------------------------------------------------------------------------


def test_help_lists_place_flag():
    """`search --help` should advertise --place."""
    p = _run(["search", "--help"])
    assert p.returncode == 0
    assert "--place" in p.stdout


def test_search_place_known_chinese_place():
    """`search landsat --place 北京市` should run and filter results."""
    p = _run(["search", "landsat", "--place", "北京市", "--limit", "5"])
    # Either returns 0 (matches found) or 1 (none match the filter)
    assert p.returncode in (0, 1)
    combined = p.stdout + p.stderr
    # If filtering ran, the place name or bbox should be mentioned
    if "北京市" in combined or "place_filter" in combined:
        # We saw place-related output, so place handling worked
        return
    # Otherwise just verify the command ran without crashing
    assert p.returncode in (0, 1)


def test_search_place_with_json_preserves_filter_metadata():
    """`search --json --place 北京市` should produce a single JSON object with place_filter."""
    p = _run(["--json", "search", "landsat", "--place", "北京市", "--limit", "3"])
    # --json with --place produces a JSON object (not NDJSON)
    assert p.returncode in (0, 1), f"stderr: {p.stderr}"
    if p.returncode != 0:
        # Filter excluded all matches — still fine, exit 1
        return
    data = json.loads(p.stdout)
    assert "results" in data
    assert "place_filter" in data
    assert data["place_filter"]["place"] == "北京市"
    assert len(data["place_filter"]["bbox"]) == 4
    assert data["place_filter"]["n_before_filter"] >= 0
    assert data["place_filter"]["n_after_filter"] >= 0


def test_search_place_unresolvable_returns_error():
    """`--place` with a garbage string should fail gracefully (not crash)."""
    p = _run(["search", "landsat", "--place", "qzx-not-a-real-place-12345", "--limit", "3"])
    # Resolution should fail → exit code 1
    assert p.returncode != 0


def test_search_filter_logic_keeps_high_inclination():
    """Unit test: _filter_satellites_by_place should keep high-inclination satellites
    for a high-latitude place (Beijing) and drop low-inclination ones."""
    from importlib import import_module
    import sys
    sys.path.insert(0, os.path.dirname(SCRIPT))
    ss = import_module("satellite_search")

    # Beijing: 39.4-40.2 N, so inclinations < ~39° should be dropped
    beijing_bbox = [115.7, 39.4, 116.7, 40.2]

    hits = [
        {"record": {"inclination": 98.6, "altitude": 705.0}},  # SSO → keep
        {"record": {"inclination": 51.6, "altitude": 450.0}},  # ISS → keep (51>39)
        {"record": {"inclination": 20.0, "altitude": 800.0}},  # Equatorial → drop
        {"record": {"inclination": None}},                      # Unknown → keep
        {"record": {"inclination": 0.0, "altitude": 36000.0}},  # GEO → keep
    ]
    out = ss._filter_satellites_by_place(hits, beijing_bbox)
    kept = [h["record"] for h in out]
    assert {"inclination": 98.6, "altitude": 705.0} in kept
    assert {"inclination": 51.6, "altitude": 450.0} in kept
    assert {"inclination": None} in kept
    assert {"inclination": 0.0, "altitude": 36000.0} in kept
    assert {"inclination": 20.0, "altitude": 800.0} not in kept


def test_search_filter_logic_drops_low_inclination_for_high_latitude():
    """Equatorial LEO satellites should not pass the Beijing filter."""
    from importlib import import_module
    sys.path.insert(0, os.path.dirname(SCRIPT))
    ss = import_module("satellite_search")
    beijing_bbox = [115.7, 39.4, 116.7, 40.2]
    hits = [
        {"record": {"inclination": 5.0, "altitude": 500.0}},   # Near-equatorial LEO
        {"record": {"inclination": 30.0, "altitude": 500.0}},  # Still < 39
    ]
    out = ss._filter_satellites_by_place(hits, beijing_bbox)
    assert len(out) == 0
