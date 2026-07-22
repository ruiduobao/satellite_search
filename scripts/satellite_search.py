"""CLI 入口 — satellite_search skill

子命令
-------
* ``list``    — 列出本地索引中所有卫星
* ``search``  — 模糊搜索（中文 + 英文），支持 NORAD id 数字查询
* ``info``    — 多源合并的详细参数（默认中文输出）
* ``fetch``   — 在线抓取单个卫星并更新本地索引
* ``stats``   — 查看索引统计
* ``update``  — 重新抓取各数据源
* ``translate`` — 用 LLM 翻译 eoPortal 介绍到中文

数据源（v0.4+）
----------------
* ``eoportal``  — eoPortal ESA 详查目录（~1,100 条带详情）
* ``oscar``     — WMO OSCAR 气象卫星目录（~1,000 条）
* ``celestrak`` — CelesTrak SATCAT 美国国防部 太空目标目录（~70,000 条总，
  约 19,600 条为在轨有效载荷）
* ``satnogs``   — SatNOGS DB 业余 / 小卫星 / 立方星数据库（~1,700 条 alive）

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
    source = args.source
    limit = args.limit
    # Map `both` (legacy) to `all` to keep backwards compatibility
    if source == "both":
        source = "all"
    rows = local_index.list_satellites(source=source, limit=limit)
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
        ("NORAD", "norad_id", "s"),
        ("运营方", "agency", "l"),
        ("发射", "launch", "s"),
        ("轨道", "orbit", "s"),
        ("状态", "status", "s"),
    ]
    _print_row_table(rows, cols)
    print(f"\n共 {len(rows)} 颗")
    return 0


def _format_search_hit(h: Dict[str, Any], lang: str) -> str:
    """Pretty-print one search hit."""
    src = h["source"]
    rec = h["record"]
    score = h.get("score", 0)
    if src == "oscar":
        agency = ", ".join(rec.get("agencies") or []) or "-"
        prog_zh = i18n.programme_zh(rec.get("programme")) or rec.get("programme", "-")
        orbit_zh = i18n.orbit_zh(rec.get("orbit")) or rec.get("orbit", "-")
        return (f"  [OSCAR]    {rec.get('acronym'):20s} | {prog_zh:20s} | "
                f"{agency} | 发射={rec.get('launch','-')} | 轨道={orbit_zh} | score={score}")
    if src == "eoportal":
        name_zh = (rec.get("name_zh") or rec.get("name") or rec.get("slug", ""))
        return f"  [EOPORTAL] {name_zh:50s} | slug={rec.get('slug')} | score={score}"
    if src == "celestrak":
        norad = rec.get("NORAD_CAT_ID", "-")
        owner_code = rec.get("OWNER", "-")
        owner_zh = i18n.country_zh(owner_code) or owner_code
        obj_type = rec.get("OBJECT_TYPE", "-")
        type_zh = i18n.celestrak_object_type_zh(obj_type) or obj_type
        return (f"  [CELESTRAK] NORAD={norad} | {rec.get('OBJECT_NAME','-'):40s} | "
                f"{owner_zh} | {type_zh} | 发射={rec.get('LAUNCH_DATE','-')} | score={score}")
    if src == "satnogs":
        norad = rec.get("norad_cat_id", "-")
        status_zh = i18n.satnogs_status_zh(rec.get("status")) or rec.get("status", "-")
        return (f"  [SATNOGS]  NORAD={norad} | {rec.get('name','-'):40s} | "
                f"运营={rec.get('operator','-') or '-'} | 状态={status_zh} | score={score}")
    if src == "ucs":
        country = rec.get("Country of Operator/Owner", "-")
        purpose = rec.get("Purpose", "-")
        return (f"  [UCS]      NORAD={rec.get('NORAD Number','-')} | "
                f"{rec.get('Name','-'):40s} | {country} | 用途={purpose} | score={score}")
    return f"  [{src.upper()}] {rec.get('name') or rec.get('acronym') or rec.get('Name','-')} | score={score}"


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
    lang = getattr(args, "lang", "zh")
    print(f"{args.keyword!r} 的 {len(hits)} 条最匹配结果（数据源={args.source}）：\n")
    for i, h in enumerate(hits, 1):
        print(f"  {i:2d}.{_format_search_hit(h, lang)}")
    return 0


def _zh_status(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    # Try i18n across all known systems
    for fn in (i18n.status_zh, i18n.satnogs_status_zh):
        z = fn(s)
        if z and z != s:
            return z
    return s


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
    celestrak = payload.get("celestrak") or {}
    satnogs = payload.get("satnogs") or {}
    m = payload.get("merged") or {}

    # 标题：name（中文/英文）
    name_display = _zh(payload.get("name"), payload.get("name_zh"), lang)
    print(f"# {name_display}")
    if payload.get("aliases"):
        print(f"  别名：{', '.join(payload['aliases'])}")
    sources = payload.get("sources", [])
    print(f"  数据源：{', '.join(sources)}（共 {len(sources)} 个）")
    norad = payload.get("norad_id") or m.get("norad_id")
    if norad:
        print(f"  NORAD 目录号：{norad}")

    if m.get("agency"):
        print(f"  运营方：{m['agency']}")
    if m.get("owner_country"):
        owner = m["owner_country"]
        owner_zh = m.get("owner_country_zh")
        if owner_zh and owner_zh != owner and lang != "en":
            print(f"  运营方国家：{owner_zh}（{owner}）")
        else:
            print(f"  运营方国家：{owner}")
    if m.get("launch_date"):
        print(f"  发射：{m['launch_date']}")
    if m.get("end_of_life"):
        print(f"  退役：{m['end_of_life']}")
    status_text = _zh(m.get("status"), m.get("status_zh") or _zh_status(m.get("status")), lang)
    if status_text and status_text != "-":
        print(f"  状态：{status_text}")
    orbit_text = _zh(m.get("orbit"), m.get("orbit_zh"), lang)
    if orbit_text and orbit_text != "-":
        print(f"  轨道：{orbit_text}")
    if m.get("instruments"):
        print(f"  仪器（{len(m['instruments'])} 个）：{', '.join(m['instruments'][:10])}{' ...' if len(m['instruments']) > 10 else ''}")

    # CelesTrak 专属字段
    if celestrak:
        print(f"\n  [CelesTrak 轨道参数]")
        if celestrak.get("PERIOD"):
            print(f"    轨道周期：{celestrak['PERIOD']} 分钟")
        if celestrak.get("INCLINATION") is not None:
            print(f"    轨道倾角：{celestrak['INCLINATION']}°")
        if celestrak.get("APOGEE") is not None and celestrak.get("PERIGEE") is not None:
            print(f"    远地点 / 近地点：{celestrak['APOGEE']} km / {celestrak['PERIGEE']} km")
        if celestrak.get("LAUNCH_SITE"):
            print(f"    发射场：{celestrak['LAUNCH_SITE']}")
        if celestrak.get("is_active_payload") is not None:
            tag = "在轨有效载荷" if celestrak["is_active_payload"] else "已陨落 / 非有效载荷"
            print(f"    类型：{celestrak.get('object_type_zh') or celestrak.get('OBJECT_TYPE', '-')}（{tag}）")

    # SatNOGS 专属字段
    if satnogs:
        print(f"\n  [SatNOGS 观测信息]")
        if satnogs.get("status"):
            print(f"    状态：{satnogs.get('status_zh') or satnogs['status']}")
        if satnogs.get("operator"):
            print(f"    运营方：{satnogs['operator']}")
        if satnogs.get("countries"):
            print(f"    国家：{satnogs['countries']}")
        if satnogs.get("website"):
            print(f"    官网：{satnogs['website']}")
        if satnogs.get("citation"):
            cite = satnogs["citation"]
            if len(cite) > 120:
                cite = cite[:120] + "..."
            print(f"    引用：{cite}")

    # UCS 专属字段
    ucs = payload.get("ucs") or {}
    if ucs:
        print(f"\n  [UCS 数据库]")
        if ucs.get("Operator/Owner"):
            print(f"    运营方：{ucs['Operator/Owner']}")
        if ucs.get("Purpose"):
            print(f"    用途：{ucs.get('purpose_zh') or ucs['Purpose']}")
        if ucs.get("Class of Orbit"):
            print(f"    轨道类别：{ucs.get('orbit_class_zh') or ucs['Class of Orbit']}")
        if ucs.get("Launch Mass (kg)"):
            print(f"    发射质量：{ucs['Launch Mass (kg)']} kg")
        if ucs.get("Expected Lifetime (yrs)"):
            print(f"    设计寿命：{ucs['Expected Lifetime (yrs)']} 年")
        if ucs.get("Launch Vehicle"):
            print(f"    运载火箭：{ucs['Launch Vehicle']}")
        if ucs.get("Contractor"):
            print(f"    制造商：{ucs['Contractor']}")

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

    # 链接
    if payload.get("eoportal") and payload["eoportal"].get("url"):
        print(f"\n  eoPortal：{payload['eoportal']['url']}")
    if payload.get("oscar") and payload["oscar"].get("detail_url"):
        print(f"  OSCAR：{payload['oscar']['detail_url']}")
    if celestrak.get("NORAD_CAT_ID"):
        print(f"  CelesTrak：https://celestrak.org/satcat/records.php?CATNR={celestrak['NORAD_CAT_ID']}")
    if satnogs.get("sat_id"):
        print(f"  SatNOGS：https://db.satnogs.org/satellite/{satnogs['sat_id']}")
    if payload.get("merge_hint"):
        print(f"  提示：{payload['merge_hint']}")
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
    print("-" * 50)
    for k, v in s.items():
        print(f"  {k:30s} : {v}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    sources: List[str] = []
    if args.source in ("oscar", "both", "all"):
        sources.append("oscar")
    if args.source in ("eoportal", "both", "all"):
        sources.append("eoportal")
    if args.source in ("celestrak", "all"):
        sources.append("celestrak")
    if args.source in ("satnogs", "all"):
        sources.append("satnogs")
    rc = 0
    for src in sources:
        print(f"\n=== 正在更新 {src} ===")
        t0 = time.time()
        try:
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
                from core.models import jsonl_dumps, jsonl_loads  # type: ignore
                out_path = os.path.join(local_index._data_dir(), "eoportal_satellites.jsonl")
                # Preserve existing detail fields — re-running the list scrape
                # must not throw away v0.2.0+ per-satellite detail payloads.
                existing: Dict[str, Dict[str, Any]] = {}
                if os.path.exists(out_path):
                    with open(out_path, "r", encoding="utf-8") as _f:
                        for r in jsonl_loads(_f.read()):
                            slug = r.get("slug")
                            if slug:
                                existing[slug] = r
                merged: List[Dict[str, Any]] = []
                kept = 0
                for r in records:
                    base = {**r, "source": "eoportal"}
                    old = existing.get(r.get("slug", ""))
                    if old:
                        # Carry over detail / instruments / summary / faq / etc.
                        for keep_k in ("detail", "instruments", "summary",
                                       "applications", "faq", "agency",
                                       "country", "launch_date", "end_of_life",
                                       "status", "measurement_domain",
                                       "last_updated"):
                            if old.get(keep_k) is not None and base.get(keep_k) is None:
                                base[keep_k] = old[keep_k]
                        if old.get("detail"):
                            kept += 1
                    merged.append(base)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(jsonl_dumps(merged))
                print(f"  {len(merged)} 条记录 -> {out_path}  ({time.time()-t0:.1f}秒)")
                print(f"    保留 {kept} 条已有 detail")
            elif src == "celestrak":
                # Delegate to the dedicated scraper
                import subprocess
                p = os.path.join(HERE, "scrape_celestrak.py")
                subprocess.run([sys.executable, p], check=False)
            elif src == "satnogs":
                import subprocess
                p = os.path.join(HERE, "scrape_satnogs.py")
                subprocess.run([sys.executable, p], check=False)
        except Exception as e:
            print(f"  ! {src} 更新失败: {e}")
            rc = 1
    # Clear lru_cache so the new data is visible
    local_index._load_jsonl.cache_clear()
    local_index._load_merged_index.cache_clear()
    print("\n=== 重建 merged 索引 ===")
    from core.models import jsonl_loads as _jsonl_loads  # type: ignore
    import json as _json

    def _load_jsonl(p: str) -> List[Dict[str, Any]]:
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            return _jsonl_loads(f.read())

    def _key(s: str) -> str:
        return s.strip().lower()

    data_dir = local_index._data_dir()
    oscar = _load_jsonl(os.path.join(data_dir, "oscar_satellites.jsonl"))
    eoportal = _load_jsonl(os.path.join(data_dir, "eoportal_satellites.jsonl"))
    celestrak_active = _load_jsonl(os.path.join(data_dir, "celestrak_active_payloads.jsonl"))
    satnogs_alive = _load_jsonl(os.path.join(data_dir, "satnogs_alive.jsonl"))
    merged: Dict[str, Dict[str, Any]] = {}
    for rec in oscar:
        n = rec.get("acronym") or ""
        if not n: continue
        k = _key(n)
        merged.setdefault(k, {})
        merged[k]["oscar"] = {
            "name": n, "sat_id": rec.get("sat_id"),
            "agency": ", ".join(rec.get("agencies") or []),
            "launch": rec.get("launch"), "eol": rec.get("eol"),
            "programme": rec.get("programme"), "orbit": rec.get("orbit"),
            "altitude": rec.get("altitude"), "inclination": rec.get("inclination"),
            "ect": rec.get("ect"), "status": rec.get("status"),
            "instruments": rec.get("instruments") or [],
            "url": rec.get("detail_url"),
        }
        merged[k].setdefault("display", n)
    for rec in eoportal:
        n = rec.get("name") or ""
        if not n: continue
        k = _key(n)
        merged.setdefault(k, {})
        merged[k]["eoportal"] = {"name": n, "slug": rec.get("slug"), "url": rec.get("url")}
        merged[k].setdefault("display", n)
    for rec in celestrak_active:
        norad = rec.get("NORAD_CAT_ID")
        if not norad: continue
        # Use a separate "celestrak" key per norad id; we don't merge into the
        # existing name-keyed merged_index because CelesTrak covers 16k+
        # active payloads and would explode the merged index file.
        merged[f"norad:{norad}"] = {
            "display": rec.get("OBJECT_NAME"),
            "celestrak": {
                "norad_id": norad,
                "name": rec.get("OBJECT_NAME"),
                "owner": rec.get("OWNER"),
                "launch_date": rec.get("LAUNCH_DATE"),
                "object_type": rec.get("OBJECT_TYPE"),
            },
        }
    for rec in satnogs_alive:
        norad = rec.get("norad_cat_id")
        if not norad: continue
        existing = merged.get(f"norad:{norad}")
        if existing:
            existing["satnogs"] = {
                "norad_id": norad, "name": rec.get("name"),
                "operator": rec.get("operator"), "status": rec.get("status"),
                "countries": rec.get("countries"),
            }
        else:
            merged[f"norad:{norad}"] = {
                "display": rec.get("name"),
                "satnogs": {
                    "norad_id": norad, "name": rec.get("name"),
                    "operator": rec.get("operator"), "status": rec.get("status"),
                    "countries": rec.get("countries"),
                },
            }
    out_path = os.path.join(data_dir, "merged_index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {len(merged)} 个键 -> {out_path}")
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
        description="查询和获取遥感卫星参数（eoPortal ESA + WMO OSCAR + CelesTrak + SatNOGS），默认中文输出。",
    )
    p.add_argument("--json", action="store_true",
                   help="以 JSON 行格式输出（每行一个对象）")
    sub = p.add_subparsers(dest="cmd", required=True)

    # list
    sp = sub.add_parser("list", help="列出本地索引中的所有卫星。")
    sp.add_argument("--source", default="both",
                    choices=["oscar", "eoportal", "celestrak", "satnogs", "all", "both"])
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=cmd_list)

    # search
    sp = sub.add_parser("search", help="在本地索引中按名称模糊搜索。")
    sp.add_argument("keyword", help="卫星名称 / NORAD id（支持中英文 / 1-6 位数字）")
    sp.add_argument("--source", default="all",
                    choices=["oscar", "eoportal", "celestrak", "satnogs", "all", "both"])
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    # info
    sp = sub.add_parser("info", help="查看某颗卫星的多源合并详细参数。")
    sp.add_argument("name", help="卫星名称（不区分大小写）或 NORAD id")
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
    sp.add_argument("--source", default="all",
                    choices=["oscar", "eoportal", "celestrak", "satnogs", "all", "both"])
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
