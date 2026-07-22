"""Batch eoPortal detail scraper.

Uses Playwright with stealth measures to fetch one detail page per
catalogue entry, persists results incrementally so the run can be resumed
after a crash.

Outputs
-------
* ``<data_dir>/eoportal_satellites.jsonl``       — UPDATED in place; the
  list-only records get a ``detail: {...}`` key appended when a successful
  fetch happens, so future `info` calls can use the rich data.
* ``<data_dir>/eoportal_details_failed.jsonl``   — slugs that could not be
  fetched after all retries, so a follow-up pass (or web_search fallback)
  can target them.

Usage
-----
    python scripts/scrape_eoportal_details.py
    python scripts/scrape_eoportal_details.py --concurrency 4 --retries 5
    python scripts/scrape_eoportal_details.py --only-slug landsat-9
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

# Make the scripts/ package importable when run directly.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core.models import jsonl_dumps, jsonl_loads  # type: ignore  # noqa: E402


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")

# Stealth: hide webdriver, mock Chrome runtime, plugins, languages, WebGL.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = {
    runtime: { onMessage: { addListener: () => {}, removeListener: () => {} },
               sendMessage: () => {}, connect: () => ({ onMessage: { addListener: () => {} } }) },
    loadTimes: function() { return { requestTime: Date.now()/1000, startLoadTime: Date.now()/1000 }; },
    csi: function() { return { startE: Date.now(), onloadT: Date.now() }; },
    app: { isInstalled: false, InstallState: { DISABLED: 'disabled' },
           RunningState: { RUNNING: 'running' } },
};
const _q = window.navigator.permissions.query.bind(window.navigator.permissions);
window.navigator.permissions.query = (p) => (
    p.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        _q(p)
);
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5].map(i => ({name:'Plugin '+i, filename:'p'+i+'.dll'})) });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
const _gp = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return _gp.call(this, p);
};
"""


# ---------------------------------------------------------------------------
# Per-page fetch (one browser context per worker)
# ---------------------------------------------------------------------------

def _parse_detail(pg, slug: str, url: str) -> Optional[Dict[str, Any]]:
    """Pull the structured fields from a rendered detail page."""
    title = pg.title()
    if "Page not found" in title or "Just a" in title:
        return None
    if "504" in title or "Error" in title.lower():
        return None

    body = pg.inner_text("body") or ""

    # Quick facts key/value pairs
    qf = _extract_quick_facts(body)

    # First summary sentence
    summary = _extract_first_sentence(body)

    # FAQ + Article JSON-LD
    faq: List[Dict[str, str]] = []
    last_updated: Optional[str] = None
    for s in pg.query_selector_all('script[type="application/ld+json"]'):
        try:
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
                    ans = (ent.get("acceptedAnswer") or {}).get("text")
                    if q and ans:
                        faq.append({"q": q, "a": ans})
            if tp == "Article":
                pub = it.get("datePublished")
                if pub and not last_updated:
                    last_updated = str(pub)

    # Display name from h1
    name = ""
    for h in pg.query_selector_all("h1"):
        t = (h.inner_text() or "").strip()
        if t and t.upper() != "OSCAR":
            name = t
            break

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
    out: Dict[str, str] = {}
    idx = body.find("Quick facts")
    if idx < 0:
        idx = 0
    chunk = body[idx: idx + 4000]
    pairs = re.findall(r"([A-Z][A-Za-z /]+?)\t([^\n|]+?)(?=(?:[A-Z][A-Za-z /]+?\t)|[\n|]|$)", chunk)
    for k, v in pairs:
        k = k.strip(); v = v.strip()
        if k and v and len(k) < 60 and len(v) < 400:
            out[k] = v
    return out


def _split_csv(s: str) -> List[str]:
    if not s:
        return []
    return [p.strip() for p in re.split(r"[,;]+", s) if p.strip()]


def _extract_first_sentence(body: str) -> Optional[str]:
    for marker in ["Quick facts", "Summary", "Overview", "Mission Status"]:
        i = body.find(marker)
        if i > 0:
            head = body[:i]
            m = re.search(r"([A-Z][^.]{30,400}\.)\s*$", head)
            if m:
                return m.group(1).strip()
    m = re.match(r"\s*([A-Z][^.]{30,400}\.)", body)
    if m:
        return m.group(1).strip()
    return None


# Worker (each thread holds its own browser)
def worker(args):
    from playwright.sync_api import sync_playwright
    from core import scraper  # for _use_proxy etc.

    slug, retries, proxy, only_uncached = args
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"],
        )
        ctx = browser.new_context(user_agent=UA, locale="en-US", timezone_id="America/New_York")
        ctx.add_init_script(STEALTH_JS)
        pg = ctx.new_page()
        url = f"https://www.eoportal.org/satellite-missions/{slug}"
        last_err: Optional[str] = None
        for attempt in range(retries + 1):
            try:
                pg.goto(url, timeout=45000, wait_until="domcontentloaded")
                pg.wait_for_timeout(2000)
                rec = _parse_detail(pg, slug, url)
                if rec is not None:
                    return ("ok", slug, rec)
                last_err = "not_found_or_504"
            except Exception as e:
                last_err = str(e)[:120]
            if attempt < retries:
                wait = min(2 ** attempt + random.uniform(0, 1.5), 20)
                time.sleep(wait)
        browser.close()
        return ("fail", slug, last_err or "unknown")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Batch fetch eoPortal detail pages.")
    p.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "data"))
    p.add_argument("--concurrency", type=int, default=3,
                   help="How many parallel Playwright browsers to run")
    p.add_argument("--retries", type=int, default=4)
    p.add_argument("--only-slug", action="append", default=[],
                   help="Only fetch these slugs (repeatable)")
    p.add_argument("--skip-uncached", action="store_true",
                   help="(unused — the script always skips records that already have a `detail` field)")
    p.add_argument("--limit", type=int, default=0,
                   help="If >0, only fetch the first N (useful for testing)")
    p.add_argument("--shuffle", action="store_true",
                   help="Shuffle the queue — useful for evading rate limits on hot slugs")
    args = p.parse_args(argv)

    jsonl_path = os.path.join(args.data_dir, "eoportal_satellites.jsonl")
    failed_path = os.path.join(args.data_dir, "eoportal_details_failed.jsonl")
    if not os.path.exists(jsonl_path):
        print(f"ERROR: {jsonl_path} not found — run scrape_eoportal.py first", file=sys.stderr)
        return 2

    with open(jsonl_path, "r", encoding="utf-8") as f:
        records = jsonl_loads(f.read())

    # Build the work list
    if args.only_slug:
        targets = [r for r in records if r.get("slug") in set(args.only_slug)]
    else:
        targets = list(records)
    if args.shuffle:
        random.shuffle(targets)
    if args.limit and args.limit > 0:
        targets = targets[:args.limit]

    # Skip already-detailed
    todo = [r for r in targets if not r.get("detail")]
    if not todo:
        print("Nothing to do — all targeted records already have a `detail` field.")
        return 0

    print(f"Fetching {len(todo)} eoPortal detail pages (concurrency={args.concurrency}, retries={args.retries})...")

    # Run with a thread pool — each worker holds its own Playwright browser.
    work_args = [(r["slug"], args.retries, None, None) for r in todo]
    results_ok: List[Tuple[str, Dict[str, Any]]] = []
    results_fail: List[Tuple[str, str]] = []
    slug_to_index = {r["slug"]: i for i, r in enumerate(records)}
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(worker, wa): wa[0] for wa in work_args}
        for fut in as_completed(futures):
            kind, slug, payload = fut.result()
            done += 1
            if kind == "ok":
                results_ok.append((slug, payload))
                # patch record
                idx = slug_to_index.get(slug)
                if idx is not None:
                    records[idx]["detail"] = payload
            else:
                results_fail.append((slug, payload if isinstance(payload, str) else "unknown"))
            elapsed = time.time() - t0
            eta = (elapsed / done) * (len(todo) - done)
            print(f"  [{done:4d}/{len(todo)}] {kind:4s}  {slug:50s}  ({elapsed:5.0f}s, ETA {eta:5.0f}s)",
                  flush=True)
            # Persist incrementally every 10 records
            if done % 10 == 0 or done == len(todo):
                with open(jsonl_path, "w", encoding="utf-8") as f:
                    f.write(jsonl_dumps(records))

    # Final write
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(jsonl_dumps(records))
    if results_fail:
        with open(failed_path, "w", encoding="utf-8") as f:
            f.write(jsonl_dumps([{"slug": s, "error": e} for s, e in results_fail]))

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s")
    print(f"  ok:   {len(results_ok)}")
    print(f"  fail: {len(results_fail)}")
    if results_fail:
        print(f"  failed slugs written to {failed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
