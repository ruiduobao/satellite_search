---
name: satellite_search
display_name: 卫星参数查询
version: 0.2.0
author: Mavis
license: MIT-0
description: |
  Search and fetch remote-sensing satellite parameters from two authoritative
  public sources:

  1. **eoPortal** (https://www.eoportal.org/satellite-missions) — ~1100 missions,
     detailed text descriptions, launch history, application domains, FAQ Q&A
     (parsed from JSON-LD), full agency / launch / status / instruments /
     applications. Best for "what is this satellite" / "what does it do".
  2. **WMO OSCAR** (https://space.oscar.wmo.int/) — ~1000 satellites, structured
     orbit / instrument / spectral band tables. Best for "what are the bands",
     "what is the orbit", "which agency operates it".

  The skill ships a **pre-scraped offline index** of both sources so the common
  case (`search` / `info` / `list`) is a local JSON lookup — no network needed.
  The eoPortal **detail pages** (text, FAQ, applications) are also pre-scraped
  via Playwright stealth (Cloudflare bypass) so `info` shows full descriptions.
  When something is missing, `fetch` does a live scrape; if that fails, a web
  search via crawl4ai-skill (DuckDuckGo) gives the user a pointer to the
  authoritative source.
runtime: python>=3.9
tags: [gis, remote-sensing, satellite, eoportal, oscar, wmo, earth-observation, params]
---

# 卫星参数查询 (satellite_search)

把 **eoPortal** + **WMO OSCAR** 两个最权威的遥感卫星参数源整合进一个本地优先的 skill。

做遥感时谁没经历过：搜某颗卫星的分辨率/波段/轨道，百度给的是新闻和博客，参数散落不全
且彼此打架。最准的要么去卫星官网翻文档，要么去欧空局 eoPortal 或 WMO OSCAR 这种
专门数据库查——但每个卫星都单独搜一遍太费劲。

**satellite_search** 把这两个站抓下来打包成本地索引，本地秒查；本地没有时再现场抓。
eoPortal 详情页有反爬保护，我们用 Playwright + stealth (隐藏 webdriver、模拟 Chrome
runtime / navigator.plugins / languages / WebGL) 绕过 Cloudflare，全量抓取 1100+ 颗
卫星的 Quick facts / Summary / FAQ Q&A。

## 适用场景

- 想知道某颗国产/国外卫星的**传感器类型、分辨率、波段、轨道、幅宽、发射时间、运营方**
- 写论文/报告/标书时需要一个**可引用的参数来源**（每个字段都带 eoPortal / OSCAR 原始 URL）
- 看 **FAQ Q&A**（eoPortal 的"分辨率多少？"、"什么时候发射？"等都结构化好）
- 不确定某颗卫星叫什么 / 有没有 / 还活着没 —— 模糊搜索
- 本地没收录的新发射卫星 —— 现场抓
- **找不到时的兜底**：fetch 失败 → 自动 web search 找原始出处

## 数据源

| 源 | URL | 收录规模 | 强项 |
|---|---|---|---|
| eoPortal | https://www.eoportal.org/satellite-missions | ~1100 颗（列表 + ~1100 颗详情） | 文字介绍、Quick facts、FAQ Q&A、国产卫星覆盖好 |
| WMO OSCAR | https://space.oscar.wmo.int/satellites | ~1000 颗 | 轨道/传感器/波段表结构化 |

> ⚠️ 数据版权归 eoPortal (ESA) 与 WMO OSCAR 所有，本 skill 仅做**只读抓取与本地缓存**，
> 用于学术研究和教育用途。

## Quickstart

```bash
# 1) 模糊搜索（先查本地索引）
python scripts/satellite_search.py search landsat
python scripts/satellite_search.py search "高分三号"
python scripts/satellite_search.py search sentinel-2

# 2) 详细参数（合并 eoPortal + OSCAR 两源 + summary + FAQ）
python scripts/satellite_search.py info "Sentinel-2A"
python scripts/satellite_search.py info "FY-4A"
python scripts/satellite_search.py info "GF-1"

# 3) 列出本地索引中的所有卫星
python scripts/satellite_search.py list --source oscar --limit 30
python scripts/satellite_search.py list --source eoportal --limit 30
python scripts/satellite_search.py list --limit 30  # 全部合并去重

# 4) 本地没命中？强制在线抓取
python scripts/satellite_search.py fetch "Sentinel-2A" --source both
python scripts/satellite_search.py fetch "高分三号" --source eoportal

# 5) 看索引里有多少颗
python scripts/satellite_search.py stats
```

## 子命令

| 子命令 | 用途 | 主要参数 |
|---|---|---|
| `search` | 模糊搜索本地索引 | `<keyword>` `[--source] [--limit]` |
| `info` | 详细参数（多源合并 + Summary + FAQ） | `<name>` `[--source]` |
| `list` | 列出本地索引中所有卫星 | `[--source] [--limit]` |
| `fetch` | 在线抓取（覆盖/补充本地） | `<name>` `[--source eoportal\|oscar\|both]` `[--no-online-fallback]` |
| `stats` | 看本地索引统计 | — |
| `update` | 重新抓取全量并更新本地索引 | `[--source]` |

## 数据格式 (Output Contract)

`info` / `search` 返回的统一 JSON 字段（双源合并）：

```json
{
  "name": "Sentinel-2A",
  "aliases": ["S2A", "Sentinel 2A"],
  "sources": ["eoportal", "oscar"],
  "eoportal": {
    "url": "https://www.eoportal.org/satellite-missions/copernicus-sentinel-2",
    "agency": "ESA",
    "country": "Multinational",
    "launch_date": "2015-06-23",
    "status": "Operational (extended)",
    "summary": "...",
    "applications": ["Land monitoring", "Emergency response"],
    "instruments": ["MSI"],
    "faq": [{"q": "What is the resolution?", "a": "..."}, ...],
    "last_updated": "2024-XX-XXTXX:XX:XXZ"
  },
  "oscar": {
    "url": "https://space.oscar.wmo.int/satellites/view/398",
    "acronym": "Sentinel-2A",
    "programme": "Copernicus",
    "agency": "ESA, EC",
    "orbit_type": "SunSync",
    "altitude_km": 786,
    "inclination_deg": 98.6,
    "period_min": 100.6,
    "instruments": ["MSI"]
  },
  "merged": {
    "agency": "ESA",
    "launch_date": "2015-06-23",
    "status": "Operational (extended)",
    "orbit": "SunSync, 786 km, 98.6°",
    "instruments_count": 1,
    "sources_count": 2,
    "summary": "...",
    "faq_count": 3
  }
}
```

## 数据抓取与刷新

```bash
# 重新抓 OSCAR 列表（4 秒搞定 1000 颗）
python scripts/satellite_search.py update --source oscar

# 重新抓 eoPortal 列表（2 秒搞定 1100 颗）
python scripts/satellite_search.py update --source eoportal

# 重新抓 eoPortal 详情（~30 分钟，4 并发 + Playwright stealth）
python scripts/scrape_eoportal_details.py --shuffle --concurrency 4

# 重新合并索引（detail → merged_index.json）
python scripts/build_detailed_index.py

# 对详情抓不到的 slug 跑 web search
python scripts/online_fallback.py
```

## Permissions

- **网络出口**：
  - `https://www.eoportal.org`（Playwright + stealth，需要 Chromium）
  - `https://space.oscar.wmo.int`（requests + XLSX 导出）
  - `https://html.duckduckgo.com`（兜底 web search）
  - `https://www.googleapis.com`（crawl4ai-skill 内部需要）
  - 默认**直连**。通过 `SATELLITE_SEARCH_USE_PROXY=1` 走系统代理
    （默认 `http://127.0.0.1:7897`）。
- **环境变量读取**：
  - `SATELLITE_SEARCH_USE_PROXY` / `SATELLITE_SEARCH_NO_PLAYWRIGHT`
  - `SATELLITE_SEARCH_DATA_DIR`（覆盖默认 `data/` 路径）
- **文件读取**：`data/*.jsonl` 与 `data/*.json`（本地索引）
- **文件写入**：`data/` 目录（更新本地索引）

## Notes

- **eoPortal 详情页抓取**用 Playwright + stealth：通过 `addInitScript`
  注入反检测脚本（隐藏 `navigator.webdriver`、补 `chrome.runtime`、
  mock `navigator.plugins` / `languages` / `WebGL` vendor），实测 ~95%
  成功率。
- **eoPortal 列表是 Next.js 渲染**：`__NEXT_DATA__` JSON 里有按 A-Z
  分组的 1100 颗卫星（slug + name + taxonomyCategoryBriefs），不需要
  Playwright 即可一次拉完。
- **OSCAR 列表是服务端渲染**：直接走等价的"Export"按钮 POST 接口
  拿 XLSX（1038 颗一次性返回）。
- **OSCAR 详情页**只比列表多几个仪器状态字段，没 band 详情，所以
  详情按需抓（不打包进首版）。
- **首次运行** `crawl4ai-skill` 会下载 Chromium（~100MB），耗时较长。
- **web_search 兜底**：当 eoPortal 详情抓不到时，自动用
  `crawl4ai-skill search`（DuckDuckGo）找相关原始出处，结果存
  `data/web_search_results.jsonl`。

## 输出示例

```bash
$ python scripts/satellite_search.py info "Landsat-9"
# Landsat-9
  Aliases: Landsat Data Continuity Mission
  Sources: eoportal, oscar
  Agency:  USGS, NASA
  Launch:  27 Sep 2021
  EOL:     ≥2031
  Status:  Operational
  Orbit:   SunSync, alt 705 km
  Instruments (2): OLI, TIRS
  Coverage: 2 of 2 sources

  Summary (https://www.eoportal.org/satellite-missions/landsat-9):
    Landsat-9 mission objectives include the collection and archival of
    moderate-resolution multispectral data, to be made freely available to
    worldwide users.
  FAQ (3):
    Q: What is the resolution of Landsat-9?
    A: The resolution of the images taken by Landsat-9 vary depending on
       the spectral band used. Thermal bands have a spatial resolution of
       100 m, multispectral bands have a resolution of 30 m, ...
    Q: Who launched Landsat-9?
    A: ...
    Q: What will Landsat-9 do?
    A: ...

  eoPortal: https://www.eoportal.org/satellite-missions/landsat-9
  OSCAR:    https://space.oscar.wmo.int/satellites/view/724
```

## License

MIT-0 — 详见 [LICENSE](./LICENSE)。
eoPortal 数据 © ESA；OSCAR 数据 © WMO。本 skill 仅做只读抓取与本地缓存。
