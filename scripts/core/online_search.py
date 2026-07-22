"""Online search fallback.

When ``local_index`` has no match and ``scraper`` can't fetch (e.g. Playwright
not installed, or eoPortal 504s forever), this module falls back to a generic
web search via the ``web_search`` skill (when present on the runtime).

The runtime contract is intentionally simple: this module returns a
``{"hint": str, "results": [...]}`` payload that the CLI can display to the
user as "where to look next". It does NOT attempt to parse the search
results — the user (or the calling agent) can decide whether to fetch one
of the suggested URLs through ``scraper``.

If the ``web_search`` skill is not available on the current runtime, the
functions in this module return ``None`` and the caller is expected to
handle that case gracefully (i.e. report "no online source available").
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional


def _web_search_skill_available() -> bool:
    """Return True iff the local-runtime ``web_search`` skill is installed."""
    # The skill is exposed via a CLI wrapper named ``web-search`` (or
    # ``web_search``). We do a best-effort check; the actual call is made
    # by spawning the skill's main script.
    for exe in ("web-search", "web_search", "websearch"):
        if shutil.which(exe):
            return True
    # Also check the OpenClaw skill install path on Windows
    for d in (
        os.path.expandvars(r"%USERPROFILE%\.codex\skills\web-search-ex-skill"),
        os.path.expandvars(r"%USERPROFILE%\.codex\skills\web-search"),
    ):
        if os.path.isdir(d):
            return True
    return False


def search_satellite_online(
    query: str,
    *,
    source_hint: Optional[str] = None,
    num_results: int = 8,
) -> Optional[Dict[str, Any]]:
    """Search the web for a satellite the local index doesn't know about.

    Parameters
    ----------
    query : str
        The satellite name (e.g. "高分三号", "Iceye X-32").
    source_hint : str, optional
        Restrict the search to a specific source domain
        (e.g. "site:eoportal.org", "site:space.oscar.wmo.int").
    num_results : int
        Cap the number of results.

    Returns
    -------
    dict with keys ``hint`` (human-readable summary) and ``results``
    (list of {title, url, snippet}); or ``None`` if the web_search skill
    is not available on the current runtime.
    """
    if not _web_search_skill_available():
        return None

    # Build a query that biases toward satellite parameter sites
    site = source_hint or ""
    q = query if site else f"{query} satellite parameters resolution"
    if site:
        q = f"{q} {site}"
    q = f"{q} satellite"

    # Try to invoke the web-search skill via the Python entry point. The
    # skill exposes a ``main()`` function accepting a dict with ``action``,
    # ``query``, ``num_results``. We import lazily so this module loads even
    # when the skill is not on the Python path.
    try:
        import importlib
        # Try a few candidate module names; first one to import wins.
        mod = None
        for name in ("web_search", "websearch", "web_search_skill", "websearch_skill"):
            try:
                mod = importlib.import_module(name)
                break
            except Exception:
                continue
        if mod is None:
            return None
        if hasattr(mod, "main"):
            res = mod.main({"action": "search", "query": q, "num_results": num_results})
        elif hasattr(mod, "search"):
            res = mod.search(q, num_results=num_results)
        else:
            return None
    except Exception:
        return None

    if not isinstance(res, dict):
        return None
    items = res.get("results") or res.get("data") or []
    cleaned: List[Dict[str, str]] = []
    for r in items:
        if not isinstance(r, dict):
            continue
        cleaned.append({
            "title": str(r.get("title") or "").strip(),
            "url": str(r.get("url") or r.get("href") or "").strip(),
            "snippet": str(r.get("snippet") or r.get("body") or "").strip(),
        })
    return {
        "hint": (
            f"Web search results for {query!r}. The local index has no entry — "
            "open one of the suggested URLs in your browser for the authoritative "
            "data, or call `satellite_search.py fetch <name> --source both` to "
            "attempt an automated grab."
        ),
        "query_used": q,
        "results": cleaned,
    }
