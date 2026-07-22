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
    p = _run(["info", "xxxnotasatellite999"])
    # The command returns 1 on no match (we do print a message)
    assert p.returncode == 1
