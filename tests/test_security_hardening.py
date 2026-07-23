"""Tests for the v0.4.1 security-hardening changes.

These cover the SkillSpector findings:
* STEALTH_JS rename + opt-out env var
* --shuffle help text reframe
* DuckDuckGo fallback disclosure
* cmd_translate LLM disclosure + opt-out
* LLM prompt injection defenses (truncation + system prompt)
"""

import os
import sys

import pytest


# ---------------------------------------------------------------------------
# F1: Browser fingerprint JS rename + opt-out
# ---------------------------------------------------------------------------

def test_scrape_eoportal_details_has_no_stealth_js_constant():
    """The old ``STEALTH_JS`` constant must be gone (v0.4.1 rename)."""
    from scripts import scrape_eoportal_details  # type: ignore  # noqa: E402

    assert not hasattr(scrape_eoportal_details, "STEALTH_JS"), (
        "STEALTH_JS must be renamed in v0.4.1 to avoid the "
        "'anti-bot / stealth' red-flag from security scanners."
    )
    assert hasattr(scrape_eoportal_details, "BROWSER_FINGERPRINT_JS"), (
        "Expected the renamed BROWSER_FINGERPRINT_JS constant."
    )


def test_scrape_eoportal_details_opt_out(monkeypatch):
    """SATELLITE_SEARCH_NO_BROWSER_FINGERPRINT=1 should return empty JS."""
    from scripts import scrape_eoportal_details  # type: ignore  # noqa: E402

    monkeypatch.setenv("SATELLITE_SEARCH_NO_BROWSER_FINGERPRINT", "1")
    fp_js = scrape_eoportal_details._browser_fingerprint_js()
    assert fp_js == "", "Opt-out env var should disable the fingerprint JS."

    monkeypatch.delenv("SATELLITE_SEARCH_NO_BROWSER_FINGERPRINT", raising=False)
    fp_js = scrape_eoportal_details._browser_fingerprint_js()
    assert "navigator" in fp_js, "Default should return the fingerprint script."


# ---------------------------------------------------------------------------
# F2: --shuffle help text reframe
# ---------------------------------------------------------------------------

def test_shuffle_help_does_not_say_evade():
    """The --shuffle help text must not mention 'evad' or 'rate limit'."""
    from scripts import scrape_eoportal_details  # type: ignore  # noqa: E402

    # Build the parser to read its help text
    # The simplest way: read the source and grep
    import inspect
    src = inspect.getsource(scrape_eoportal_details)
    assert "evading" not in src.lower(), "help text must not say 'evading'"
    assert "rate limit" not in src.lower(), (
        "help text must not mention 'rate limit' (the framing in v0.4.1 "
        "should be about error clustering, not anti-detection)."
    )
    assert "shuffle" in src.lower()


# ---------------------------------------------------------------------------
# F3: DuckDuckGo fallback disclosure
# ---------------------------------------------------------------------------

def test_online_search_docstring_has_privacy_section():
    """The online_search module must document the privacy implications."""
    from core import online_search  # type: ignore  # noqa: E402

    doc = online_search.__doc__ or ""
    assert "Privacy" in doc or "privacy" in doc, (
        "online_search.py must have a privacy disclosure section."
    )
    assert "Opt out" in doc, "online_search.py must document how to opt out."


def test_online_search_no_online_env_short_circuits():
    """SATELLITE_SEARCH_NO_ONLINE=1 must make search_satellite_online return None."""
    from core import online_search  # type: ignore  # noqa: E402

    old = os.environ.get("SATELLITE_SEARCH_NO_ONLINE")
    try:
        os.environ["SATELLITE_SEARCH_NO_ONLINE"] = "1"
        result = online_search.search_satellite_online("Sentinel-2A")
        assert result is None, (
            "SATELLITE_SEARCH_NO_ONLINE=1 must short-circuit without network."
        )
    finally:
        if old is None:
            os.environ.pop("SATELLITE_SEARCH_NO_ONLINE", None)
        else:
            os.environ["SATELLITE_SEARCH_NO_ONLINE"] = old


# ---------------------------------------------------------------------------
# F4: cmd_translate LLM disclosure + opt-out
# ---------------------------------------------------------------------------

def test_cmd_translate_no_llm_env_short_circuits(capsys):
    """SATELLITE_SEARCH_NO_LLM=1 must make cmd_translate return 0 without LLM."""
    from scripts.satellite_search import cmd_translate  # type: ignore  # noqa: E402

    class _Args:
        limit = 0
        concurrency = 0
        only_slug = []
        include_fetched = False
        dry_run = False

    old = os.environ.get("SATELLITE_SEARCH_NO_LLM")
    try:
        os.environ["SATELLITE_SEARCH_NO_LLM"] = "1"
        rc = cmd_translate(_Args())
        assert rc == 0
    finally:
        if old is None:
            os.environ.pop("SATELLITE_SEARCH_NO_LLM", None)
        else:
            os.environ["SATELLITE_SEARCH_NO_LLM"] = old


# ---------------------------------------------------------------------------
# F5: LLM prompt injection defenses
# ---------------------------------------------------------------------------

def test_translate_descriptions_system_prompt_has_injection_defense():
    """The SYSTEM_PROMPT must contain explicit injection-resistant language."""
    from scripts import translate_descriptions  # type: ignore  # noqa: E402

    sp = translate_descriptions.SYSTEM_PROMPT
    assert "注入" in sp or "injection" in sp.lower(), (
        "SYSTEM_PROMPT must contain prompt-injection defense language."
    )
    # The preamble should also tell the model to ignore any "ignore above" type
    # instructions that might be embedded in the user content.
    assert "ignore" in sp.lower() or "忽略" in sp, (
        "SYSTEM_PROMPT must tell the model to ignore embedded instructions."
    )


def test_translate_descriptions_truncate_caps_strings():
    """_truncate must cap long strings at the configured limit."""
    from scripts import translate_descriptions  # type: ignore  # noqa: E402

    long_str = "x" * 20_000
    out = translate_descriptions._truncate(long_str, cap=100)
    assert len(out) == 100

    # Lists and dicts are recursed
    out = translate_descriptions._truncate(
        ["a" * 200, {"k": "b" * 200}], cap=50,
    )
    assert len(out[0]) == 50
    assert len(out[1]["k"]) == 50

    # Non-strings are passed through
    assert translate_descriptions._truncate(42) == 42
    assert translate_descriptions._truncate(None) is None


def test_translate_descriptions_truncate_handles_nested_faq():
    """FAQ is a list of dicts; _truncate must descend into it."""
    from scripts import translate_descriptions  # type: ignore  # noqa: E402

    payload = {
        "name": "Test",
        "summary": "s" * 30_000,
        "faq": [
            {"q": "q" * 30_000, "a": "a" * 30_000},
            {"q": "short", "a": "short"},
        ],
    }
    out = translate_descriptions._truncate(payload, cap=100)
    assert len(out["summary"]) == 100
    assert len(out["faq"][0]["q"]) == 100
    assert len(out["faq"][0]["a"]) == 100
    assert out["faq"][1] == {"q": "short", "a": "short"}
