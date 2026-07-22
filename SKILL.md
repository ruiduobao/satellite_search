---
name: satellite_search
display_name: 卫星参数查询
version: 0.3.0
author: Mavis
license: MIT-0
description: |
  离线优先的遥感卫星参数查询 skill。把欧空局 eoPortal（ESA，~1100 颗）
  和世界气象组织 OSCAR（~1000 颗）这两个最权威的遥感卫星数据库整合到
  本地索引，本地秒级查询。本地没有时支持在线抓取（Playwright + stealth
  绕过 Cloudflare）和 web 搜索兜底（crawl4ai-skill DuckDuckGo）。所有
  卫星介绍（summary / FAQ / 应用领域 / 名称）均已通过 LLM 翻译为中文，
  中文用户直接看中文，英文原文作为 secondary 输出保留可溯源。
runtime: python>=3.9
tags: [gis, remote-sensing, satellite, eoportal, oscar, wmo, earth-observation, params, 中文]
---

# 卫星参数查询 (satellite_search)

把 **eoPortal** + **WMO OSCAR** 两个最权威的遥感卫星参数源整合进一个本地优先的 skill，
面向中文用户，所有介绍性内容（summary、FAQ、应用领域、名称）均已翻译成中文，原始英文
保留供溯源。

做遥感时谁没经历过：搜某颗卫星的分辨率/波段/轨道，百度给的是新闻和博客，参数散落不全
且彼此打架。最准的要么去卫星官网翻文档，要么去欧空局 eoPortal 或 WMO OSCAR 这种
专门数据库查——但每个卫星都单独搜一遍太费劲。

**satellite_search** 把这两个站抓下来打包成本地索引，本地秒查；本地没有时再现场抓。
eoPortal 详情页有反爬保护，用 Playwright + stealth（隐藏 webdriver、模拟 Chrome
runtime / navigator.plugins / languages / WebGL）绕过 Cloudflare，全量抓取 1100+ 颗
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
| eoPortal | https://www.eoportal.org/satellite-missions | ~1100 颗（列表 + 1100 颗详情，中文翻译） | 文字介绍、Quick facts、FAQ Q&A、国产卫星覆盖好 |
| WMO OSCAR | https://space.oscar.wmo.int/satellites | ~1000 颗 | 轨道/传感器/波段表结构化 |

> ⚠️ 数据版权归 eoPortal (ESA) 与 WMO OSCAR 所有，本 skill 仅做**只读抓取与本地缓存**，
> 用于学术研究和教育用途。

## Quickstart

```bash
# 1) 模糊搜索（先查本地索引）
python scripts/satellite_search.py search landsat
python scripts/satellite_search.py search "高分三号"
python scripts/satellite_search.py search sentinel-2

# 2) 详细参数（合并 eoPortal + OSCAR 两源 + 中文 summary + FAQ）
python scripts/satellite_search.py info "Sentinel-2A"
python scripts/satellite_search.py info "FY-4A"
python scripts/satellite_search.py info "GF-1"

# 3) 列出本地索引中的所有卫星
python scripts/satellite_search.py list --source oscar --limit 30
python scripts/satellite_search.py list --source eoportal --limit 30
python scripts/satellite_search.py list --limit 30  # 全部合并去重

# 4) 本地没命中？强制在线抓取
python scripts/satellite_search.py fetch "高分三号" --source eoportal
python scripts/satellite_search.py fetch "Sentinel-2A" --source both

# 5) 看索引里有多少颗
python scripts/satellite_search.py stats
```

## 子命令

| 子命令 | 用途 | 主要参数 |
|---|---|---|
| `search` | 模糊搜索本地索引 | `<keyword>` `[--source] [--limit]` |
| `info` | 详细参数（多源合并 + 中文 Summary + FAQ） | `<name>` `[--source]` `[--lang zh\|en\|both]` |
| `list` | 列出本地索引中所有卫星 | `[--source] [--limit]` |
| `fetch` | 在线抓取（覆盖/补充本地） | `<name>` `[--source eoportal\|oscar\|both]` `[--no-online-fallback]` |
| `stats` | 看本地索引统计 | — |
| `update` | 重新抓取全量并更新本地索引 | `[--source]` |
| `translate` | 用 LLM 翻译 eoPortal 介绍（中文） | `[--limit] [--concurrency]` |

## 数据格式 (Output Contract)

`info` / `search` 返回的统一 JSON 字段（双源合并 + 双语）：

```json
{
  "name": "Sentinel-2A",
  "name_zh": "哨兵-2A",
  "aliases": ["S2A", "Sentinel 2A"],
  "sources": ["eoportal", "oscar"],
  "eoportal": {
    "url": "https://www.eoportal.org/satellite-missions/copernicus-sentinel-2",
    "agency": "ESA",
    "agency_zh": "欧空局",
    "launch_date": "2015-06-23",
    "status": "Operational (extended)",
    "status_zh": "在轨运行（延寿）",
    "summary_zh": "Sentinel-2 卫星是哥白尼计划的一部分...",
    "summary_en": "The Copernicus Sentinel-2 ...",
    "applications_zh": ["陆表监测", "应急响应", "..."],
    "applications_en": ["Land monitoring", "Emergency response"],
    "instruments": ["MSI"],
    "faq_zh": [{"q": "...", "a": "..."}],
    "faq_en": [{"q": "...", "a": "..."}],
    "last_updated": "2024-XX-XXTXX:XX:XXZ"
  },
  "oscar": { "...": "..." },
  "merged": {
    "agency": "ESA",
    "launch_date": "2015-06-23",
    "instruments_count": 1,
    "sources_count": 2,
    "summary_zh": "...",
    "faq_zh_count": 3
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

# 重建 merged_index.json
python scripts/build_detailed_index.py

# 用 LLM 翻译 eoPortal 全部 1100 颗卫星的 summary/FAQ 到中文
python scripts/translate_descriptions.py --concurrency 4
# 然后重建索引把翻译合并进去
python scripts/build_detailed_index.py

# 对详情抓不到的 slug 跑 web search
python scripts/online_fallback.py
```

## Permissions

- **网络出口**：
  - `https://www.eoportal.org`（Playwright + stealth，需要 Chromium）
  - `https://space.oscar.wmo.int`（requests + XLSX 导出）
  - `https://html.duckduckgo.com`（兜底 web search）
  - `https://token-plan-cn.xiaomimimo.com`（LLM 翻译）
  - 默认**直连**。通过 `SATELLITE_SEARCH_USE_PROXY=1` 走系统代理
    （默认 `http://127.0.0.1:7897`）。
- **环境变量读取**：
  - `SATELLITE_SEARCH_USE_PROXY` / `SATELLITE_SEARCH_NO_PLAYWRIGHT`
  - `SATELLITE_SEARCH_DATA_DIR`（覆盖默认 `data/` 路径）
  - `OPENAI_API_KEY` / `OPENAI_BASE_URL`（LLM 翻译用）
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
  `crawl4ai-skill search`（DuckDuckGo）找相关原始出处。
- **中文翻译**：用 `mimo-v2.5-pro`（OpenAI 协议）批量翻译 eoPortal 的
  英文介绍，存到 `eoportal_satellites_zh.jsonl`，再合并到
  `merged_index.json`。用户拿到的默认是中文，英文原文保留供核对。

## 输出示例

```bash
$ python scripts/satellite_search.py info "Sentinel-2A"
# Copernicus: Sentinel-2  / 哥白尼：哨兵-2
  别名：Sentinel-2A, Sentinel-2
  数据源：eoPortal, oscar
  运营方：ESA, EC
  发射：2015-06-23
  退役：≥2026
  状态：在轨运行
  轨道：太阳同步轨道，高度 786 km
  仪器（1 个）：MSI
  覆盖：2/2 个数据源

  简介（https://www.eoportal.org/satellite-missions/copernicus-sentinel-2）：
    哨兵-2 是哥白尼计划的一部分，多颗卫星协同工作以优化覆盖和重访时间。
  应用领域：陆表监测、应急响应、...
  FAQ（3 条）：
    Q: 哨兵-2 数据是免费的吗？
    A: 欧空局和欧盟的数据政策提供完全开放的数据访问，可在哥白尼数据中心免费下载。
    Q: 哨兵-2 的设计寿命是多久？
    A: 设计寿命 7.25 年，包括 3 个月的入轨测试期...
    Q: 哨兵-2 与其他哨兵任务有何不同？
    A: 哨兵-2 是唯一搭载高分辨率光学成像仪的卫星...

  eoPortal: https://www.eoportal.org/satellite-missions/copernicus-sentinel-2
  OSCAR:    https://space.oscar.wmo.int/satellites/view/398
```

## License

MIT-0 — 详见 [LICENSE](./LICENSE)。
eoPortal 数据 © ESA；OSCAR 数据 © WMO。本 skill 仅做只读抓取与本地缓存。
