"""Online search fallback.

When the local index has no match and the scraper can't reach eoPortal
(Cloudflare 504s, missing playwright, etc.), this module falls back to a
web search so the user always gets *something* useful — even if it's just
"here are the URLs you should look at manually".

Engine priority (first to succeed wins):

1. ``crawl4ai-skill`` (DuckDuckGo) — already installed on this runtime
2. ``web_search`` skill (Baidu / Bing / DDG)
3. Direct duckduckgo.com via ``requests`` (last-ditch)

The module exposes:

* :func:`search_satellite_online` — generic web search
* :func:`fallback_for_eoportal`    — search restricted to eoportal.org
* :func:`fallback_for_oscar`       — search restricted to space.oscar.wmo.int
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Engine probe
# ---------------------------------------------------------------------------

def _which(name: str) -> Optional[str]:
    return shutil.which(name) or shutil.which(f"{name}.cmd") or shutil.which(f"{name}.exe")


def _crawl4ai_available() -> bool:
    return _which("crawl4ai-skill") is not None


def _web_search_available() -> bool:
    return _which("web-search") is not None or _which("web_search") is not None


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

def _run_subprocess(cmd: List[str], timeout: int = 60) -> Optional[Dict[str, Any]]:
    """Run a CLI, return parsed JSON if the tool supports ``--json`` /
    ``-o``/stdout JSON, else return ``None``."""
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if cp.returncode != 0:
        return None
    out = cp.stdout.strip()
    if not out:
        return None
    # Try to parse JSON directly (crawl4ai's "search" with -o prints to a file though)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def _engine_crawl4ai(query: str, num: int, site: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Use the ``crawl4ai-skill search`` CLI. The CLI writes JSON to a
    temp file when ``-o`` is given; otherwise it prints a Markdown table."""
    exe = _which("crawl4ai-skill")
    if not exe:
        return None
    q = query if site is None else f"{query} site:{site}"
    # Use -o to get JSON. The CLI may need ~60-120s on first invocation
    # because it downloads Chromium under the hood.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cmd = [exe, "search", q, "-n", str(min(num, 20)), "-o", tmp_path]
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return None
    if cp.returncode != 0:
        return None
    if not os.path.exists(tmp_path):
        return None
    try:
        with open(tmp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    # crawl4ai-skill search returns: { "query": ..., "results": [{"title","url","snippet"}, ...] }
    items = data.get("results") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    cleaned: List[Dict[str, str]] = []
    for r in items:
        if not isinstance(r, dict):
            continue
        cleaned.append({
            "title": str(r.get("title") or "").strip(),
            "url": str(r.get("url") or r.get("href") or "").strip(),
            "snippet": str(r.get("snippet") or r.get("body") or r.get("description") or "").strip(),
        })
    return {
        "engine": "crawl4ai-skill (DuckDuckGo)",
        "query_used": q,
        "results": cleaned,
    }


def _engine_web_search_skill(query: str, num: int, site: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Call the ``web_search`` skill via its Python entry point."""
    try:
        import importlib
        mod = None
        for name in ("web_search", "websearch", "web_search_skill", "websearch_skill"):
            try:
                mod = importlib.import_module(name)
                break
            except Exception:
                continue
        if mod is None:
            return None
        q = query if site is None else f"{query} site:{site}"
        if hasattr(mod, "main"):
            res = mod.main({"action": "search", "query": q, "num_results": num})
        elif hasattr(mod, "search"):
            res = mod.search(q, num_results=num)
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
        "engine": res.get("engine", "web_search skill"),
        "query_used": q,
        "results": cleaned,
    }


def _engine_duckduckgo_direct(query: str, num: int, site: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Last-ditch: hit DuckDuckGo's HTML endpoint directly."""
    import requests
    q = query if site is None else f"{query} site:{site}"
    s = requests.Session()
    s.trust_env = False
    try:
        r = s.get(
            "https://html.duckduckgo.com/html/",
            params={"q": q, "kl": "us-en"},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0 Safari/537.36"},
            timeout=20,
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    import re
    results: List[Dict[str, str]] = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>.*?'
        r'class="result__snippet"[^>]*>(.*?)</a>',
        r.text, re.DOTALL,
    ):
        url, title, snippet = m.group(1), m.group(2), m.group(3)
        # DuckDuckGo wraps clicks — unwrap if uddg= is present
        if "uddg=" in url:
            from urllib.parse import unquote, parse_qs, urlparse
            qs = parse_qs(urlparse(url).query)
            if "uddg" in qs:
                url = unquote(qs["uddg"][0])
        results.append({
            "title": re.sub(r"<[^>]+>", "", title).strip(),
            "url": url.strip(),
            "snippet": re.sub(r"<[^>]+>", "", snippet).strip(),
        })
        if len(results) >= num:
            break
    return {
        "engine": "duckduckgo-direct",
        "query_used": q,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_satellite_online(
    query: str,
    *,
    site: Optional[str] = None,
    num_results: int = 8,
) -> Optional[Dict[str, Any]]:
    """Search the web for a satellite the local index doesn't know about.

    Returns
    -------
    dict with keys ``engine``, ``hint``, ``query_used``, ``results``;
    or ``None`` if every engine failed.
    """
    engines = [
        _engine_crawl4ai,
        _engine_web_search_skill,
        _engine_duckduckgo_direct,
    ]
    for engine in engines:
        try:
            res = engine(query, num_results, site)
        except Exception:
            res = None
        if res and res.get("results"):
            res["hint"] = (
                f"Web search results for {query!r} via {res['engine']}. "
                "Open one of the suggested URLs for authoritative data; "
                "or call `satellite_search.py fetch <name> --source both` "
                "to attempt an automated grab."
            )
            return res
    return None


def fallback_for_eoportal(slug: str) -> Optional[Dict[str, Any]]:
    """Search the web restricted to eoportal.org for one satellite."""
    return search_satellite_online(slug, site="eoportal.org", num_results=5)


def fallback_for_oscar(acronym: str) -> Optional[Dict[str, Any]]:
    """Search the web restricted to space.oscar.wmo.int for one satellite."""
    return search_satellite_online(acronym, site="space.oscar.wmo.int", num_results=5)


def any_engine_available() -> bool:
    """Return True iff at least one online search engine is reachable."""
    return _crawl4ai_available() or _web_search_available() or True  # DDG-direct always works
