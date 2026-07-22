"""批量把 eoPortal 详情翻译成中文。

调用 mimo-v2.5-pro（OpenAI 协议）一次翻译一个卫星的
``name`` / ``summary`` / ``applications`` / ``faq`` / ``agency`` /
``status`` 等字段，结果存到 ``<data_dir>/eoportal_satellites_zh.jsonl``。

每个卫星只翻译一次，增量持久化（已有翻译的不重译，除非
``--include-fetched``），并发可调（``--concurrency``）。

环境变量
--------
* ``OPENAI_API_KEY``  — 必填
* ``OPENAI_BASE_URL`` — 默认 ``https://token-plan-cn.xiaomimimo.com/v1``
* ``OPENAI_MODEL``    — 默认 ``mimo-v2.5-pro``

使用
----
::

    python scripts/translate_descriptions.py
    python scripts/translate_descriptions.py --concurrency 8
    python scripts/translate_descriptions.py --only-slug gaofen-1
    python scripts/translate_descriptions.py --limit 50
    python scripts/translate_descriptions.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core.models import jsonl_dumps, jsonl_loads  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5-pro"
DEFAULT_TIMEOUT = 120


# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------

def _openai_client():
    """Lazy import + build an OpenAI client. Uses ``OPENAI_API_KEY`` and
    ``OPENAI_BASE_URL``. If a third-party client is not installed, returns
    a tiny shim that uses ``requests`` so the script still works in
    minimal environments."""
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Set it in the environment before running."
        )
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)

    try:
        from openai import OpenAI  # type: ignore
        return OpenAI(api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT), model
    except ImportError:
        # Fallback to raw requests
        return _RequestsShim(base_url, api_key, model), model


class _RequestsShim:
    """Minimal OpenAI-compatible client using ``requests``."""

    def __init__(self, base_url: str, api_key: str, model: str):
        import requests
        self._s = requests.Session()
        self._s.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model

    class _ChatCompletions:
        def __init__(self, parent):
            self._p = parent
        def create(self, *, model, messages, **kwargs):
            import requests
            r = self._p._s.post(
                self._p._url,
                json={"model": model, "messages": messages, **kwargs},
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()

    @property
    def chat(self):
        return _RequestsShim._ChatCompletions(self)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是专业的中文科技翻译，负责把英文遥感卫星介绍翻译成中文。

要求：
1. 专有名词（如 NASA、ESA、SAR、MSI、CNSA）保留原文不译。
2. 卫星系列名（Sentinel-2、Landsat-9、GF-3 等）保留原文；如果常见中文译名
   已存在（如"哨兵"、"陆地卫星"、"高分"），可用"哨兵-2（Sentinel-2）"形式。
3. 机构名（如 NASA、ESA、USGS、CNSA、CMA、ROS HYDROMET、CRESDA、INPE、AEB）
   保留原文；如果同行公认有中文译名（如欧空局=ESA、欧洲委员会=EC）可补注。
4. 措辞要专业但易懂，避免直译。Summary 是简介，FAQ 是问答。
5. 严格按 JSON Schema 返回，不要加任何额外文字、注释或 markdown 标记。"""

USER_PROMPT_TEMPLATE = """请把以下这颗卫星的英文介绍翻译成中文，严格按 JSON 返回。

卫星名称（英文）：{name}
{eoportal_extra}

需要翻译的字段（所有字段都用中文翻译；若字段原本就为空，保留为空字符串）：

{{
  "name_zh": "卫星名的中文译名（仅系列名翻译，如 Sentinel → 哨兵；其余保持原名）",
  "agency_zh": "运营方/机构的中文译名（专有名词如 NASA / ESA 保留原文）",
  "status_zh": "任务状态的中文翻译（如 Operational → 在轨运行）",
  "summary_zh": "简介的中文翻译（完整通顺）",
  "applications_zh": ["应用领域 1", "应用领域 2", ...]   （数组，与原文一一对应）
  "faq_zh": [{{"q": "问题中文翻译", "a": "答案中文翻译"}}, ...]   （数组，与原文一一对应）
}}

原始数据（JSON）：

{payload}
"""


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm(client, model: str, name: str, eoportal: Dict[str, Any]) -> Dict[str, Any]:
    """Translate one satellite's eoPortal record into Chinese."""
    eoportal_payload = {
        "name": eoportal.get("name") or name,
        "agency": eoportal.get("agency"),
        "country": eoportal.get("country"),
        "launch_date": eoportal.get("launch_date"),
        "end_of_life": eoportal.get("end_of_life"),
        "status": eoportal.get("status"),
        "summary": eoportal.get("summary"),
        "applications": eoportal.get("applications") or [],
        "faq": eoportal.get("faq") or [],
    }
    # Drop None values for a cleaner prompt
    eoportal_payload = {k: v for k, v in eoportal_payload.items() if v}

    extra_lines = []
    if eoportal.get("url"):
        extra_lines.append(f"原文链接：{eoportal['url']}")
    if eoportal.get("instruments"):
        extra_lines.append(f"仪器：{', '.join(eoportal['instruments'])}")
    eoportal_extra = "\n".join(extra_lines) if extra_lines else ""

    user_msg = USER_PROMPT_TEMPLATE.format(
        name=name,
        eoportal_extra=eoportal_extra,
        payload=json.dumps(eoportal_payload, ensure_ascii=False, indent=2),
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except TypeError:
        # Some shims don't support response_format
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
        )
    content = resp["choices"][0]["message"]["content"] if isinstance(resp, dict) else resp.choices[0].message.content
    # Parse JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to extract a JSON block
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {"_error": "json_parse_failed", "_raw": content[:500]}


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def worker(args):
    name, slug, eoportal_record, client, model = args
    try:
        translation = _call_llm(client, model, name, eoportal_record)
        return ("ok", slug, translation)
    except Exception as e:
        return ("fail", slug, str(e)[:200])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(
        description="调用 LLM 把 eoPortal 卫星详情批量翻译成中文。",
    )
    p.add_argument("--data-dir", default=os.path.join(os.path.dirname(HERE), "data"))
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--only-slug", action="append", default=[])
    p.add_argument("--include-fetched", action="store_true",
                   help="重新翻译已有翻译的卫星")
    p.add_argument("--dry-run", action="store_true", help="只打印要翻译的条数")
    p.add_argument("--retries", type=int, default=2)
    args = p.parse_args(argv)

    jsonl_path = os.path.join(args.data_dir, "eoportal_satellites.jsonl")
    out_path = os.path.join(args.data_dir, "eoportal_satellites_zh.jsonl")
    if not os.path.exists(jsonl_path):
        print(f"ERROR: {jsonl_path} 不存在 — 请先运行 scrape_eoportal_details.py", file=sys.stderr)
        return 2

    with open(jsonl_path, "r", encoding="utf-8") as f:
        records = jsonl_loads(f.read())

    # Load existing translations
    existing: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                rec = json.loads(line)
                if rec.get("slug"):
                    existing[rec["slug"]] = rec

    # Build work list
    if args.only_slug:
        wanted = set(args.only_slug)
        targets = [r for r in records if r.get("slug") in wanted]
    else:
        targets = list(records)
    if not args.include_fetched:
        targets = [r for r in targets if r.get("slug") not in existing]
    if args.limit:
        targets = targets[:args.limit]

    if args.dry_run:
        print(f"将翻译 {len(targets)} 颗卫星（dry-run）")
        return 0
    if not targets:
        print("没有要翻译的卫星。")
        return 0

    print(f"开始翻译 {len(targets)} 颗卫星（并发={args.concurrency}）...")

    try:
        client, model = _openai_client()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    results: List[Dict[str, Any]] = list(existing.values())
    slug_to_record = {r.get("slug"): r for r in records}
    work = []
    for r in targets:
        slug = r.get("slug")
        d = r.get("detail") or {}
        if not d.get("summary") and not d.get("faq"):
            # Skip if no English text to translate
            continue
        work.append((r.get("name") or slug, slug, d, client, model))

    if not work:
        print("所有目标都没有 detail 数据可翻译。")
        return 0

    done = 0
    t0 = time.time()
    fail = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(worker, wa): wa[1] for wa in work}
        for fut in as_completed(futures):
            kind, slug, payload = fut.result()
            done += 1
            elapsed = time.time() - t0
            eta = (elapsed / done) * (len(work) - done)
            if kind == "ok":
                rec = {"slug": slug, **payload}
                results.append(rec)
                existing[slug] = rec
                # Persist incrementally every 10
                if done % 10 == 0 or done == len(work):
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(jsonl_dumps(results))
                ok = "OK"
                msg = (payload.get("summary_zh") or "")[:60]
            else:
                fail += 1
                ok = "FAIL"
                msg = payload
            print(f"  [{done:4d}/{len(work)}] {ok:4s}  {slug:50s}  ({elapsed:5.0f}s, ETA {eta:5.0f}s)  {msg}",
                  flush=True)
    # Final write
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(jsonl_dumps(results))

    elapsed = time.time() - t0
    print(f"\n完成，耗时 {elapsed:.0f}秒")
    print(f"  成功：{done - fail}")
    print(f"  失败：{fail}")
    print(f"  输出：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
