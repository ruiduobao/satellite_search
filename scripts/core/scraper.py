"""Live fetcher for satellite metadata.

This module is the "online" side of the skill — it is the only module in
``core`` that touches the network. It is used by:

* ``satellite_search.py update``  — to rebuild the bundled ``data/`` files
* ``satellite_search.py fetch``   — to look up a single satellite on demand

Two sources are supported:

* **OSCAR** — https://space.oscar.wmo.int/satellites
  - List: POST the "Export" button to receive an XLSX with all ~1000 entries
  - Detail: GET /satellites/view/<sat_id> for a specific entry (HTML)
  - No JS rendering required.

* **eoPortal** — https://www.eoportal.org/satellite-missions
  - List: GET the catalogue page; the Next.js payload is in the initial
    HTML, so no Playwright is required for the list.
  - Detail: GET the satellite page; requires Playwright because the body
    text is hydrated by client-side JS.

Network policy
--------------
By default we connect directly. The skill supports two opt-in modes:

* ``SATELLITE_SEARCH_USE_PROXY=1``  — honour ``HTTP_PROXY`` / ``HTTPS_PROXY``
* ``SATELLITE_SEARCH_NO_PLAYWRIGHT=1`` — refuse to import Playwright; raise
  a clear error if eoPortal detail is requested.

Cloudflare note
---------------
eoPortal is behind Cloudflare. Detail pages will see occasional 504s and
timeouts; the helpers below retry with exponential backoff and will give
up after a configurable number of attempts.
"""

from __future__ import annotations

import io
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


EOPORTAL_LIST_URL = "https://www.eoportal.org/satellite-missions"
EOPORTAL_DETAIL_TMPL = "https://www.eoportal.org/satellite-missions/{slug}"

OSCAR_LIST_URL = "https://space.oscar.wmo.int/satellites"
OSCAR_DETAIL_TMPL = "https://space.oscar.wmo.int/satellites/view/{sat_id}"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def _use_proxy() -> bool:
    return os.environ.get("SATELLITE_SEARCH_USE_PROXY", "").lower() in ("1", "true", "yes")


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "en-US,en;q=0.9"})
    s.trust_env = _use_proxy()
    return s


# ---------------------------------------------------------------------------
# OSCAR — list (XLSX export)
# ---------------------------------------------------------------------------

def _normalize_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    # Replace non-breaking spaces (\xa0) with regular spaces
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _parse_agencies(raw: Optional[str]) -> List[str]:
    """OSCAR's Agencies cell is multi-line; split on newlines and strip."""
    if not raw:
        return []
    # First split on newlines (preserving each line), then normalize each.
    parts: List[str] = []
    for line in re.split(r"[\r\n]+", raw):
        s = _normalize_text(line)
        if s:
            parts.append(s)
    return parts


def _parse_payload(raw: Optional[str]) -> List[str]:
    """OSCAR's Payload cell is multi-line; one instrument per line, optionally
    followed by ``(spacecraft-suffix)`` like ``MSI (S2A)``."""
    if not raw:
        return []
    out: List[str] = []
    for line in re.split(r"[\r\n]+", raw):
        s = _normalize_text(line)
        if not s:
            continue
        # Strip a trailing "(SOMETHING)" only if it's a parenthetical suffix
        stripped = re.sub(r"\s*\(([^)]+)\)\s*$", "", s).strip()
        out.append(stripped or s)
    return out


def _parse_inclination(raw: Optional[str]) -> Optional[str]:
    """OSCAR sometimes writes inclination as "97.85°"; pass through as-is."""
    if raw is None:
        return None
    s = str(raw).replace("\xa0", " ").strip()
    return s or None


def fetch_oscar_list(timeout: int = 120, max_retries: int = 2) -> bytes:
    """Download the full OSCAR satellite list as an XLSX file (bytes)."""
    s = _new_session()
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            r = s.get(OSCAR_LIST_URL, timeout=30)
            r.raise_for_status()
            html = r.text
            csrf_m = re.search(r'name="_csrfToken" value="([^"]+)"', html)
            fields_m = re.search(r'name="_Token\[fields\]" value="([^"]+)"', html)
            unlocked_m = re.search(r'name="_Token\[unlocked\]" value="([^"]+)"', html)
            if not csrf_m:
                raise RuntimeError("CSRF token not found on OSCAR list page")
            data = {
                "_csrfToken": csrf_m.group(1),
                "showcurrent": "",
                "launch": "",
                "eol": "",
                "orbits": "",
                "spaceagencies": "",
                "message": "",
                "checkrequest": "",
                "Export": "Export",
                "_Token[fields]": fields_m.group(1) if fields_m else "",
                "_Token[unlocked]": unlocked_m.group(1) if unlocked_m else "",
            }
            r2 = s.post(OSCAR_LIST_URL, data=data, timeout=timeout)
            r2.raise_for_status()
            ct = r2.headers.get("Content-Type", "")
            if "spreadsheetml" not in ct and "excel" not in ct.lower() and "octet-stream" not in ct:
                raise RuntimeError(f"Unexpected OSCAR response Content-Type: {ct}")
            return r2.content
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(2 + attempt * 3)
                continue
            raise RuntimeError(f"OSCAR list fetch failed after {max_retries + 1} attempts: {e}") from e
    raise RuntimeError(f"OSCAR list fetch failed: {last_err}")


def parse_oscar_xlsx(xlsx_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse the OSCAR XLSX export into a list of dicts.

    The export has 16 columns; we use the standard header.
    """
    import openpyxl  # type: ignore
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = list(rows[0])
    out: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if all(v is None for v in row):
            continue
        d: Dict[str, Any] = {}
        for i, col in enumerate(header):
            if i >= len(row):
                break
            d[str(col).strip()] = row[i]
        # Normalize
        sat_id = d.get("Id") or d.get("SAT ID")
        try:
            sat_id_int = int(sat_id) if sat_id is not None else 0
        except (TypeError, ValueError):
            sat_id_int = 0
        rec = {
            "acronym": _normalize_text(str(d.get("Acronym") or "")) or "",
            "sat_id": sat_id_int,
            "launch": _normalize_text(d.get("Launch")),
            "eol": _normalize_text(d.get("(expected) EOL")),
            "programme": _normalize_text(d.get("Satellite Programme")),
            "agencies": _parse_agencies(d.get("Agencies")),
            "orbit": _normalize_text(d.get("Orbit")),
            "altitude": _normalize_text(d.get("Altitude")),
            "longitude": _normalize_text(d.get("Longitude")),
            "inclination": _parse_inclination(d.get("Inclination")),
            "ect": _normalize_text(d.get("Ect")),
            "status": _normalize_text(d.get("Sat status")),
            "instruments": _parse_payload(d.get("Payload")),
            "detail_url": OSCAR_DETAIL_TMPL.format(sat_id=sat_id_int) if sat_id_int else None,
            "last_update": _normalize_text(d.get("Last update")),
        }
        if rec["acronym"]:
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# eoPortal — list (no Playwright needed)
# ---------------------------------------------------------------------------

EOPORTAL_HREF_RE = re.compile(r'^/satellite-missions/([a-z0-9][a-z0-9-]+)/?$')

def fetch_eoportal_list(timeout: int = 60, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Fetch the eoPortal catalogue page and extract (slug, name) pairs.

    The Next.js payload contains a ``__NEXT_DATA__`` JSON blob. The
    catalogue lives at ``props.pageProps.groupedSatelliteMissionsList``,
    a list of 27 entries (A..Z) where each entry is ``{"letter": "A",
    "items": [{friendlyUrlPath, id, title, taxonomyCategoryBriefs}, ...]}``.
    """
    s = _new_session()
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            r = s.get(EOPORTAL_LIST_URL, timeout=timeout)
            r.raise_for_status()
            html = r.text
            m = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                html,
                re.DOTALL,
            )
            if not m:
                raise RuntimeError("eoPortal __NEXT_DATA__ not found")
            import json
            data = json.loads(m.group(1))
            page_props = data.get("props", {}).get("pageProps", {})
            groups = page_props.get("groupedSatelliteMissionsList") or []
            out: List[Dict[str, Any]] = []
            seen: set = set()
            for g in groups:
                if not isinstance(g, dict):
                    continue
                items = g.get("items") or []
                for m in items:
                    if not isinstance(m, dict):
                        continue
                    slug = (m.get("friendlyUrlPath") or "").strip()
                    name = (m.get("title") or "").strip()
                    sid = m.get("id")
                    if not slug or not name:
                        continue
                    if slug in seen:
                        continue
                    seen.add(slug)
                    # taxonomyCategoryBriefs gives us a pre-classified set of
                    # labels (status, agency, mission type, domain, ...) which
                    # is useful for the index even without a detail fetch.
                    briefs = m.get("taxonomyCategoryBriefs") or []
                    cat_names: List[str] = []
                    for b in briefs:
                        if isinstance(b, dict) and b.get("taxonomyCategoryName"):
                            cat_names.append(str(b["taxonomyCategoryName"]))
                    out.append({
                        "name": name,
                        "slug": slug,
                        "url": f"https://www.eoportal.org/satellite-missions/{slug}",
                        "eoportal_id": sid,
                        "taxonomy": cat_names,
                    })
            if not out:
                # Fallback: extract from the rendered card list
                out = _extract_eoportal_cards_from_html(html)
            return out
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(2 + attempt * 3)
                continue
            raise RuntimeError(f"eoPortal list fetch failed after {max_retries + 1} attempts: {e}") from e
    raise RuntimeError(f"eoPortal list fetch failed: {last_err}")


def _extract_eoportal_cards_from_html(html: str) -> List[Dict[str, Any]]:
    """Fallback: pull (name, slug) from rendered card <a> elements."""
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for m in re.finditer(r'<a[^>]+href="(/satellite-missions/([a-z0-9][a-z0-9-]+))"[^>]*>([^<]+)</a>', html):
        slug = m.group(2)
        name = m.group(3).strip()
        if slug in seen or not name:
            continue
        # skip the bare /satellite-missions landing page
        if slug == "" or name.lower() == "satellite missions":
            continue
        seen.add(slug)
        out.append({
            "name": name,
            "slug": slug,
            "url": f"https://www.eoportal.org/satellite-missions/{slug}",
        })
    return out


# ---------------------------------------------------------------------------
# eoPortal — detail (Playwright required)
# ---------------------------------------------------------------------------

def fetch_eoportal_detail(slug: str, timeout_ms: int = 45000, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Fetch and parse one eoPortal satellite detail page.

    Returns a dict with the following fields when successful::

        {
            "name": str,
            "slug": str,
            "url": str,
            "agency": Optional[str],
            "country": Optional[str],
            "launch_date": Optional[str],
            "end_of_life": Optional[str],
            "status": Optional[str],
            "summary": Optional[str],
            "applications": List[str],
            "instruments": List[str],
            "measurement_domain": List[str],
            "faq": List[Dict[str, str]],
            "last_updated": Optional[str],
        }

    Returns ``None`` when the page could not be loaded after retries (e.g.
    Cloudflare 504). Raises ``RuntimeError`` if Playwright is not available
    and ``SATELLITE_SEARCH_NO_PLAYWRIGHT=1`` is set.
    """
    if os.environ.get("SATELLITE_SEARCH_NO_PLAYWRIGHT", "").lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "Playwright disabled via SATELLITE_SEARCH_NO_PLAYWRIGHT=1; "
            "eoPortal detail fetches are not available."
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright not installed. Install with: pip install playwright && playwright install chromium"
        ) from e

    url = EOPORTAL_DETAIL_TMPL.format(slug=slug)
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox"])
                ctx = browser.new_context(user_agent=DEFAULT_UA)
                pg = ctx.new_page()
                pg.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                pg.wait_for_timeout(2500)
                title = pg.title()
                if "504" in title or "Error" in title.lower() or "Just a" in title:
                    raise RuntimeError(f"eoPortal returned {title!r}")
                rec = _parse_eoportal_detail_html(pg, slug=slug, url=url)
                browser.close()
                return rec
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(3 + attempt * 4)
                continue
            # exhausted
            return None
    return None


def _parse_eoportal_detail_html(pg, slug: str, url: str) -> Dict[str, Any]:
    """Parse a Playwright page object into the standard detail dict."""
    # Title is the h1 — but the page <title> includes the site name; use the
    # first meaningful h1 instead.
    name = ""
    for h in pg.query_selector_all("h1"):
        t = (h.inner_text() or "").strip()
        if t and t.upper() != "OSCAR":
            name = t
            break

    body = pg.inner_text("body") or ""

    # Quick-facts key-value pairs (a <table> usually appears near the top of
    # the article). We scan a chunk of body text for tab-separated pairs.
    qf = _extract_quick_facts(body)

    # First paragraph ("Launched in ... is ...") as summary.
    summary = _extract_first_sentence(body)

    # FAQ Q&A from JSON-LD (most reliable across the site)
    faq: List[Dict[str, str]] = []
    last_updated: Optional[str] = None
    for s in pg.query_selector_all('script[type="application/ld+json"]'):
        try:
            import json
            j = json.loads(s.inner_text() or "")
        except Exception:
            continue
        items = j if isinstance(j, list) else [j]
        for it in items:
            if not isinstance(it, dict):
                continue
            tp = it.get("@type")
            if tp == "FAQPage":
                for ent in it.get("mainEntity") or []:
                    q = ent.get("name")
                    ans = ent.get("acceptedAnswer", {}).get("text") if isinstance(ent.get("acceptedAnswer"), dict) else None
                    if q and ans:
                        faq.append({"q": q, "a": ans})
            if tp == "Article":
                pub = it.get("datePublished")
                if pub and not last_updated:
                    last_updated = str(pub)

    return {
        "name": name or slug,
        "slug": slug,
        "url": url,
        "agency": qf.get("Agency"),
        "country": qf.get("Country"),
        "launch_date": qf.get("Launch date"),
        "end_of_life": qf.get("End of life date"),
        "status": qf.get("Mission status"),
        "summary": summary,
        "applications": _split_csv(qf.get("Applications") or ""),
        "instruments": _split_csv(qf.get("Instruments") or ""),
        "measurement_domain": _split_csv(qf.get("Measurement domain") or ""),
        "faq": faq,
        "last_updated": last_updated,
    }


def _extract_quick_facts(body: str) -> Dict[str, str]:
    """Extract key/value pairs from the eoPortal "Quick facts" block.

    The body text has a region that looks like:
        Agency\tNASA, USGS | Mission status\tOperational ...
    separated by tabs and ``|``.
    """
    out: Dict[str, str] = {}
    # Look for the well-known "Quick facts" marker
    idx = body.find("Quick facts")
    if idx < 0:
        idx = 0
    chunk = body[idx: idx + 4000]
    # Split on tab + line breaks
    pairs = re.findall(r"([A-Z][A-Za-z /]+?)\t([^\n|]+?)(?=(?:[A-Z][A-Za-z /]+?\t)|[\n|]|$)", chunk)
    for k, v in pairs:
        k = k.strip()
        v = v.strip()
        if k and v and len(k) < 60 and len(v) < 400:
            out[k] = v
    return out


def _split_csv(s: str) -> List[str]:
    if not s:
        return []
    return [p.strip() for p in re.split(r"[,;]+", s) if p.strip()]


def _extract_first_sentence(body: str) -> Optional[str]:
    """Pull the first sentence (a complete one, ending with a period)."""
    # Look for the first sentence after "Summary" or "Overview" markers
    for marker in ["Quick facts", "Summary", "Overview", "Mission Status"]:
        i = body.find(marker)
        if i > 0:
            # back up to find the previous sentence (look for ". " before)
            head = body[:i]
            # find the last complete sentence before this marker
            m = re.search(r"([A-Z][^.]{30,400}\.)\s*$", head)
            if m:
                return m.group(1).strip()
    # Fallback: very first sentence
    m = re.match(r"\s*([A-Z][^.]{30,400}\.)", body)
    if m:
        return m.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# OSCAR — detail (HTML; no JS needed)
# ---------------------------------------------------------------------------

def fetch_oscar_detail(sat_id: int, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """Fetch one OSCAR satellite detail page. Returns a small dict with
    extra fields (instruments, bands, etc.) found on the page; ``None`` on
    failure. Pure requests, no Playwright.
    """
    s = _new_session()
    url = OSCAR_DETAIL_TMPL.format(sat_id=sat_id)
    try:
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
    except Exception:
        return None
    text = r.text
    # Pull instrument list and basic facts
    return {
        "sat_id": sat_id,
        "url": url,
        "instruments_detailed": _parse_oscar_instruments(text),
        "spectral_bands": _parse_oscar_spectral_bands(text),
    }


def _parse_oscar_instruments(html: str) -> List[Dict[str, Any]]:
    """Light-touch parse of the instruments list. Best effort."""
    out: List[Dict[str, Any]] = []
    m = re.search(r"<h2[^>]*>Instruments</h2>(.+?)</div>", html, re.DOTALL | re.IGNORECASE)
    if not m:
        return out
    block = m.group(1)
    for li in re.findall(r"<li[^>]*>(.+?)</li>", block, re.DOTALL):
        # strip tags
        text = re.sub(r"<[^>]+>", " ", li)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append({"name": text})
    return out


def _parse_oscar_spectral_bands(html: str) -> List[Dict[str, Any]]:
    """Light-touch parse of any spectral band table that appears."""
    out: List[Dict[str, Any]] = []
    # Heuristic: look for a table whose header row mentions "Wavelength" or "Band"
    for tbl in re.findall(r"<table[^>]*>(.+?)</table>", html, re.DOTALL | re.IGNORECASE):
        if not re.search(r"wavelength|band", tbl, re.IGNORECASE):
            continue
        rows = re.findall(r"<tr[^>]*>(.+?)</tr>", tbl, re.DOTALL | re.IGNORECASE)
        if not rows:
            continue
        out.append({"raw_rows": len(rows)})
    return out
