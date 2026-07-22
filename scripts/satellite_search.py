"""CLI 入口 — satellite_search skill

子命令
-------
* ``list``    — 列出本地索引中所有卫星
* ``search``  — 模糊搜索（中文 + 英文）
* ``info``    — 多源合并的详细参数（默认中文输出）
* ``fetch``   — 在线抓取单个卫星并更新本地索引
* ``stats``   — 查看索引统计
* ``update``  — 重新抓取 OSCAR / eoPortal 列表
* ``translate`` — 用 LLM 翻译 eoPortal 介绍到中文

输出模式
--------
* 默认          — 人类可读文本（表格 / 单行）
* ``--json``    — JSON 行（每行一个对象）
* ``--lang``    — ``zh``（默认）/ ``en`` / ``both`` 控制 info 字段的语言
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import i18n, local_index, online_search, scraper  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# 输出辅助
# ---------------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _print_row_table(rows: List[Dict[str, Any]], columns: List[tuple]) -> None:
    width = 100
    widths: List[int] = []
    for header, key, _ in columns:
        max_w = len(header)
        for r in rows:
            v = r.get(key)
            if v is None:
                continue
            s = str(v)
            if len(s) > max_w:
                max_w = len(s)
        widths.append(min(max_w, 40))
    line = "  ".join(h.ljust(widths[i]) for i, (h, _, _) in enumerate(columns))
    print(line)
    print("-" * len(line))
    for r in rows:
        cells = []
        for i, (_, key, fmt) in enumerate(columns):
            v = r.get(key)
            if v is None:
                v = ""
            s = str(v)
            w = widths[i]
            if len(s) > w:
                if fmt == "l":
                    s = "..." + s[-w + 3:]
                else:
                    s = s[:w - 1] + "…"
            cells.append(s.ljust(w))
        print("  ".join(cells))


def _zh(en: Optional[str], translated: Optional[str], lang: str) -> str:
    """Return the appropriate text based on language preference."""
    if lang == "en":
        return en or "-"
    if lang == "both":
        if en and translated and en != translated:
            return f"{translated}（{en}）"
        return translated or en or "-"
    # default: zh
    if translated:
        return translated
    return en or "-"


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    rows = local_index.list_satellites(source=args.source, limit=args.limit)
    if args.json:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        return 0
    if not rows:
        print("（本地索引为空，请先运行 `update` 抓取数据）")
        return 0
    cols = [
        ("数据源", "source", "s"),
        ("名称", "name", "l"),
        ("运营方", "agency", "l"),
        ("发射", "launch", "s"),
        ("轨道", "orbit", "s"),
        ("状态", "status", "s"),
    ]
    _print_row_table(rows, cols)
    print(f"\n共 {len(rows)} 颗")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    hits = local_index.search(args.keyword, source=args.source, limit=args.limit)
    if args.json:
        for h in hits:
            print(json.dumps(h, ensure_ascii=False))
        return 0
    if not hits:
        print(f"本地未找到与 {args.keyword!r} 匹配的卫星。")
        online = online_search.search_satellite_online(args.keyword, num_results=5)
        if online:
            print(f"\n{online['hint']}\n")
            for r in online["results"][:5]:
                print(f"  - {r['title']}\n    {r['url']}\n    {r['snippet'][:120]}")
        return 1
    print(f"{args.keyword!r} 的 {len(hits)} 条最匹配结果（数据源={args.source}）：\n")
    for i, h in enumerate(hits, 1):
        rec = h["record"]
        if h["source"] == "oscar":
            agency = ", ".join(rec.get("agencies") or []) or "-"
            prog_zh = i18n.programme_zh(rec.get("programme")) or rec.get("programme", "-")
            orbit_zh = i18n.orbit_zh(rec.get("orbit")) or rec.get("orbit", "-")
            print(f"  {i:2d}. [OSCAR]    {rec.get('acronym'):20s} | {prog_zh:20s} | {agency} | 发射={rec.get('launch','-')} | 轨道={orbit_zh}")
        else:
            name_zh = (rec.get("name_zh") or rec.get("name") or rec.get("slug", ""))
            print(f"  {i:2d}. [EOPORTAL] {name_zh:50s} | slug={rec.get('slug')}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    merged = local_index.info(args.name)
    if merged is None:
        print(f"本地未找到与 {args.name!r} 匹配的卫星。")
        if not args.no_online:
            online = online_search.search_satellite_online(args.name, num_results=5)
            if online:
                print(f"\n{online['hint']}\n")
                for r in online["results"][:5]:
                    print(f"  - {r['title']}\n    {r['url']}\n    {r['snippet'][:120]}")
        return 1
    payload = merged.to_dict()
    if args.json:
        _print_json(payload)
        return 0
    lang = getattr(args, "lang", "zh")
    eo = payload.get("eoportal") or {}
    oscar = payload.get("oscar") or {}
    m = payload.get("merged") or {}

    # 标题：name（中文/英文）
    name_display = _zh(payload.get("name"), payload.get("name_zh"), lang)
    print(f"# {name_display}")
    if payload.get("aliases"):
        print(f"  别名：{', '.join(payload['aliases'])}")
    print(f"  数据源：{', '.join(payload.get('sources', []))}")

    if m.get("agency"):
        print(f"  运营方：{m['agency']}")
    if m.get("launch_date"):
        print(f"  发射：{m['launch_date']}")
    if m.get("end_of_life"):
        print(f"  退役：{m['end_of_life']}")
    status_text = _zh(m.get("status"), m.get("status_zh"), lang)
    if status_text and status_text != "-":
        print(f"  状态：{status_text}")
    orbit_text = _zh(m.get("orbit"), m.get("orbit_zh"), lang)
    if orbit_text and orbit_text != "-":
        print(f"  轨道：{orbit_text}")
    if m.get("instruments"):
        print(f"  仪器（{len(m['instruments'])} 个）：{', '.join(m['instruments'][:10])}{' ...' if len(m['instruments']) > 10 else ''}")
    print(f"  覆盖：{m.get('sources_count', len(payload.get('sources', [])))}/2 个数据源")
    if payload.get("merge_hint"):
        print(f"  提示：{payload['merge_hint']}")

    # eoPortal 详情（中文优先）
    summary_text = _zh(eo.get("summary_en") or eo.get("summary"),
                        eo.get("summary_zh"), lang)
    if summary_text and summary_text != "-":
        print(f"\n  简介（{eo.get('url')}）：")
        s = summary_text
        if len(s) > 500:
            s = s[:500].rstrip() + "..."
        print(f"    {s}")

    apps_zh = eo.get("applications_zh") or []
    apps_en = eo.get("applications") or []
    if apps_zh or apps_en:
        if lang == "zh" and apps_zh:
            print(f"  应用领域：{', '.join(apps_zh)}")
        elif lang == "en" and apps_en:
            print(f"  应用领域：{', '.join(apps_en)}")
        else:
            # both: zip
            parts = []
            for en, zh in zip(apps_en, apps_zh):
                parts.append(f"{zh}（{en}）")
            print(f"  应用领域：{', '.join(parts)}")

    faq_zh = eo.get("faq_zh") or []
    faq_en = eo.get("faq_en") or eo.get("faq") or []
    if faq_zh or faq_en:
        if lang == "zh" and faq_zh:
            faqs = faq_zh
        elif lang == "en" and faq_en:
            faqs = faq_en
        else:
            faqs = faq_zh or faq_en
        print(f"  FAQ（{len(faqs)} 条）：")
        for qa in faqs[:3]:
            q = qa.get("q", "")[:100]
            a = (qa.get("a") or "").strip()
            if len(a) > 250:
                a = a[:250].rstrip() + "..."
            print(f"    Q：{q}")
            print(f"    A：{a}")

    if eo.get("last_updated"):
        print(f"  eoPortal 最后更新：{eo['last_updated']}")

    # URL
    if payload.get("eoportal") and payload["eoportal"].get("url"):
        print(f"\n  eoPortal：{payload['eoportal']['url']}")
    if payload.get("oscar") and payload["oscar"].get("detail_url"):
        print(f"  OSCAR：{payload['oscar']['detail_url']}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    source = args.source
    out: Dict[str, Any] = {"query": args.name, "source": source, "found": {}}
    target_path = os.path.join(local_index._data_dir(), "eoportal_satellites.jsonl")
    existing = local_index.all_eoportal()
    existing_slugs = {r.get("slug"): r for r in existing}

    if source in ("oscar", "both"):
        rec = local_index._find_in_oscar(args.name)
        if rec:
            out["found"]["oscar"] = rec
    if source in ("eoportal", "both"):
        rec = local_index._find_in_eoportal(args.name)
        if rec:
            out["found"]["eoportal"] = rec
    if args.no_live:
        if not out["found"]:
            print(f"本地未找到 {args.name!r}（已指定 --no-live）。")
            return 1
        _print_json(out)
        return 0

    need_oscar = source in ("oscar", "both") and "oscar" not in out["found"]
    need_eo = source in ("eoportal", "both") and "eoportal" not in out["found"]

    if need_oscar:
        cand = None
        for r in local_index.all_oscar():
            if r.get("acronym", "").lower() == args.name.lower():
                cand = r
                break
        if cand is None:
            hits = local_index.search(args.name, source="oscar", limit=1)
            cand = hits[0]["record"] if hits else None
        if cand and cand.get("sat_id"):
            print(f"正在抓取 OSCAR 详情：{cand['acronym']} (id={cand['sat_id']}) ...")
            det = scraper.fetch_oscar_detail(int(cand["sat_id"]))
            if det:
                cand = {**cand, "detail": det}
                out["found"]["oscar"] = cand

    if need_eo:
        slug = None
        for r in existing:
            if r.get("name", "").lower() == args.name.lower():
                slug = r.get("slug")
                break
        if slug is None:
            hits = local_index.search(args.name, source="eoportal", limit=1)
            slug = hits[0]["record"].get("slug") if hits else None
        if slug is None:
            slug = args.name.lower().replace(" ", "-")
            slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-")
        if slug:
            print(f"正在抓取 eoPortal 详情：{slug} ...")
            det = scraper.fetch_eoportal_detail(slug)
            if det:
                old = existing_slugs.get(slug) or {}
                merged = {**old, **det, "source": "eoportal"}
                existing_slugs[slug] = merged
                with open(target_path, "w", encoding="utf-8") as f:
                    from core.models import jsonl_dumps  # type: ignore
                    f.write(jsonl_dumps(list(existing_slugs.values())))
                local_index._load_jsonl.cache_clear()
                out["found"]["eoportal"] = det
            else:
                out.setdefault("warnings", []).append(
                    f"eoPortal 详情抓取失败：{slug}（Cloudflare 504 或页面不存在）"
                )
                if not args.no_online_fallback:
                    print(f"  详情抓取失败，正在搜索原始出处：{slug} ...")
                    fallback = online_search.fallback_for_eoportal(slug)
                    if fallback:
                        out["online_fallback"] = fallback

    if not out["found"]:
        print(f"未在 {source} 中找到 {args.name!r}。")
        online = online_search.search_satellite_online(args.name, num_results=3)
        if online:
            print(f"\n{online['hint']}\n")
            for r in online["results"][:3]:
                print(f"  - {r['title']} | {r['url']}")
        return 1

    if "eoportal" in out["found"] or "oscar" in out["found"]:
        merged = local_index.info(args.name)
        if merged is not None:
            out["merged"] = merged.to_dict()

    if args.json:
        _print_json(out)
    else:
        print(f"\n已为 {args.name!r} 抓取到：")
        for src, rec in out["found"].items():
            n = rec.get("acronym") or rec.get("name") or rec.get("slug")
            url = rec.get("detail_url") or rec.get("url")
            print(f"  [{src}] {n}  ->  {url}")
        if out.get("merged"):
            m = out["merged"]["merged"]
            print(f"\n  运营方：{m.get('agency')}")
            print(f"  状态：{m.get('status')}")
            print(f"  发射：{m.get('launch_date')}")
            print(f"  轨道：{m.get('orbit')}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    s = local_index.stats()
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    print("satellite_search 本地索引统计")
    print("-" * 40)
    for k, v in s.items():
        print(f"  {k:18s} : {v}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    sources: List[str] = []
    if args.source in ("oscar", "both"):
        sources.append("oscar")
    if args.source in ("eoportal", "both"):
        sources.append("eoportal")
    rc = 0
    for src in sources:
        print(f"\n=== 正在更新 {src} ===")
        t0 = time.time()
        if src == "oscar":
            xlsx = scraper.fetch_oscar_list()
            records = scraper.parse_oscar_xlsx(xlsx)
            from core.models import jsonl_dumps  # type: ignore
            out_path = os.path.join(local_index._data_dir(), "oscar_satellites.jsonl")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(jsonl_dumps([{**r, "source": "oscar"} for r in records]))
            print(f"  {len(records)} 条记录 -> {out_path}  ({time.time()-t0:.1f}秒)")
        elif src == "eoportal":
            records = scraper.fetch_eoportal_list()
            from core.models import jsonl_dumps  # type: ignore
            out_path = os.path.join(local_index._data_dir(), "eoportal_satellites.jsonl")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(jsonl_dumps([{**r, "source": "eoportal"} for r in records]))
            print(f"  {len(records)} 条记录 -> {out_path}  ({time.time()-t0:.1f}秒)")
    print("\n=== 重建 merged 索引 ===")
    from build_index import _load_jsonl, _key  # type: ignore
    import json as _json
    data_dir = local_index._data_dir()
    oscar = _load_jsonl(os.path.join(data_dir, "oscar_satellites.jsonl"))
    eoportal = _load_jsonl(os.path.join(data_dir, "eoportal_satellites.jsonl"))
    merged: Dict[str, Dict[str, Any]] = {}
    for rec in oscar:
        n = rec.get("acronym") or ""
        if not n: continue
        merged.setdefault(_key(n), {})
        merged[_key(n)]["oscar"] = {
            "name": n,
            "sat_id": rec.get("sat_id"),
            "agency": ", ".join(rec.get("agencies") or []),
            "launch": rec.get("launch"),
            "eol": rec.get("eol"),
            "programme": rec.get("programme"),
            "orbit": rec.get("orbit"),
            "altitude": rec.get("altitude"),
            "inclination": rec.get("inclination"),
            "ect": rec.get("ect"),
            "status": rec.get("status"),
            "instruments": rec.get("instruments") or [],
            "url": rec.get("detail_url"),
        }
        merged[_key(n)].setdefault("display", n)
    for rec in eoportal:
        n = rec.get("name") or ""
        if not n: continue
        merged.setdefault(_key(n), {})
        merged[_key(n)]["eoportal"] = {
            "name": n,
            "slug": rec.get("slug"),
            "url": rec.get("url"),
        }
        merged[_key(n)].setdefault("display", n)
    out_path = os.path.join(data_dir, "merged_index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {len(merged)} 个唯一键 -> {out_path}")
    return rc


def cmd_translate(args: argparse.Namespace) -> int:
    """调用 LLM 翻译 eoPortal 卫星介绍。委托给 translate_descriptions.py。"""
    from translate_descriptions import main as _main  # type: ignore
    argv = []
    if args.limit:
        argv += ["--limit", str(args.limit)]
    if args.concurrency:
        argv += ["--concurrency", str(args.concurrency)]
    if args.only_slug:
        argv += ["--only-slug", *args.only_slug]
    if args.include_fetched:
        argv += ["--include-fetched"]
    if args.dry_run:
        argv += ["--dry-run"]
    return _main(argv)


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="satellite_search",
        description="查询和获取遥感卫星参数（eoPortal ESA + WMO OSCAR），默认中文输出。",
    )
    p.add_argument("--json", action="store_true",
                   help="以 JSON 行格式输出（每行一个对象）")
    sub = p.add_subparsers(dest="cmd", required=True)

    # list
    sp = sub.add_parser("list", help="列出本地索引中的所有卫星。")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=cmd_list)

    # search
    sp = sub.add_parser("search", help="在本地索引中按名称模糊搜索。")
    sp.add_argument("keyword", help="卫星名称（支持中英文）")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    # info
    sp = sub.add_parser("info", help="查看某颗卫星的多源合并详细参数。")
    sp.add_argument("name", help="卫星名称（不区分大小写）")
    sp.add_argument("--no-online", action="store_true",
                    help="本地无结果时不调用 web search 兜底")
    sp.add_argument("--lang", default="zh", choices=["zh", "en", "both"],
                    help="输出语言（默认 zh：中文；en：英文；both：中英对照）")
    sp.set_defaults(func=cmd_info)

    # fetch
    sp = sub.add_parser("fetch",
                        help="在线抓取某颗卫星并追加到本地索引。")
    sp.add_argument("name", help="卫星名称（不区分大小写）")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.add_argument("--no-live", action="store_true",
                    help="仅查本地索引，不访问网络")
    sp.add_argument("--no-online-fallback", action="store_true",
                    help="在线抓取失败时不调用 web search 兜底")
    sp.set_defaults(func=cmd_fetch)

    # stats
    sp = sub.add_parser("stats", help="查看本地索引统计。")
    sp.set_defaults(func=cmd_stats)

    # update
    sp = sub.add_parser("update", help="重新抓取源数据库并重建索引。")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "both"])
    sp.set_defaults(func=cmd_update)

    # translate
    sp = sub.add_parser("translate", help="用 LLM 把 eoPortal 介绍翻译成中文。")
    sp.add_argument("--limit", type=int, default=0, help="只翻译前 N 条")
    sp.add_argument("--concurrency", type=int, default=4, help="并发 LLM 调用数")
    sp.add_argument("--only-slug", action="append", default=[], help="只翻译这些 slug")
    sp.add_argument("--include-fetched", action="store_true",
                    help="重新翻译已有翻译的卫星")
    sp.add_argument("--dry-run", action="store_true", help="只打印要翻译的条数")
    sp.set_defaults(func=cmd_translate)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
