---
name: satellite_search
display_name: 卫星参数查询
version: 0.1.0
author: Mavis
license: MIT-0
description: |
  Search and fetch remote-sensing satellite parameters from two authoritative
  public sources:

  1. **eoPortal** (https://www.eoportal.org/satellite-missions) — ~1000+ missions,
     detailed text descriptions, launch history, application domains. Best for
     "what is this satellite" / "what agency / programme is it part of".
  2. **WMO OSCAR** (https://space.oscar.wmo.int/) — ~900 satellites, structured
     orbit / instrument / spectral band tables. Best for "what are the bands",
     "what is the orbit", "which agency operates it".

  The skill ships a **pre-scraped offline index** of both sources so the common
  case (`search` / `info`) is a local JSON lookup — no network needed. When a
  satellite is not in the index, or you need fresher data, the skill can
  fall back to a live Playwright scrape of the source website.
runtime: python>=3.9
tags: [gis, remote-sensing, satellite, eoportal, oscar, wmo, earth-observation, params]
---

# 卫星参数查询 (satellite_search)

把 **eoPortal** + **WMO OSCAR** 两个最权威的遥感卫星参数源整合进一个本地优先的 skill。

做遥感时谁没经历过：搜某颗卫星的分辨率/波段/轨道，百度给的是新闻和博客，参数散落不全
且彼此打架。最准的要么去卫星官网翻文档，要么去欧空局 eoPortal 或 WMO OSCAR 这种
专门数据库查——但每个卫星都单独搜一遍太费劲。

**satellite_search** 把这两个站抓下来打包成本地索引，本地秒查；本地没有时再现场抓。

## 适用场景

- 想知道某颗国产/国外卫星的**传感器类型、分辨率、波段、轨道、幅宽、发射时间、运营方**
- 写论文/报告/标书时需要一个**可引用的参数来源**
- 不确定某颗卫星叫什么 / 有没有 / 还活着没 —— 模糊搜索
- 本地没收录的新发射卫星 —— 现场去官网抓

## 数据源

| 源 | URL | 收录规模 | 强项 | 弱项 |
|---|---|---|---|---|
| eoPortal | https://www.eoportal.org/satellite-missions | ~1000+ 颗 | 文字介绍、发射历史、应用领域、国产卫星覆盖好 | 参数散落、需要逐页解析 |
| WMO OSCAR | https://space.oscar.wmo.int/satellites | ~900 颗 | 轨道/传感器/波段表结构化、可机器解析 | 文字介绍少、国产卫星偏少 |

> ⚠️ 数据版权归 eoPortal (ESA) 与 WMO OSCAR 所有，本 skill 仅做**只读抓取与本地缓存**，
> 用于学术研究和教育用途。

## Quickstart

```bash
# 1) 模糊搜索（先查本地索引）
python scripts/satellite_search.py search landsat
python scripts/satellite_search.py search "高分三号"
python scripts/satellite_search.py search sentinel-2

# 2) 详细参数（合并 eoPortal + OSCAR 两源）
python scripts/satellite_search.py info "Sentinel-2A"
python scripts/satellite_search.py info "FY-4A"

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
| `info` | 详细参数（多源合并） | `<name>` `[--source]` |
| `list` | 列出本地索引中所有卫星 | `[--source] [--limit]` |
| `fetch` | 在线抓取（覆盖/补充本地） | `<name>` `[--source eoportal\|oscar\|both]` |
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
    "url": "https://www.eoportal.org/satellite-missions/sentinel-2",
    "agency": "ESA",
    "country": "Multinational",
    "launch_date": "2015-06-23",
    "status": "Operational",
    "summary": "...",
    "applications": ["Land monitoring", "Emergency response"]
  },
  "oscar": {
    "url": "https://space.oscar.wmo.int/satellites/...",
    "acronym": "S2A",
    "programme": "Copernicus",
    "agency": "ESA",
    "orbit_type": "SunSync",
    "altitude_km": 786,
    "inclination_deg": 98.6,
    "period_min": 100.6,
    "instruments": [
      {
        "name": "MSI",
        "purpose": "Multispectral imager",
        "bands": [
          {"id": "B1", "name": "Coastal aerosol", "range_um": [0.43, 0.45], "resolution_m": 60},
          ...
        ]
      }
    ]
  },
  "merged": {
    "agency": "ESA",
    "launch_date": "2015-06-23",
    "status": "Operational",
    "orbit": "SunSync, 786 km, 98.6°",
    "instruments_count": 1,
    "sources_count": 2
  }
}
```

本地只命中一个源时，另一个源字段为 `null`，但仍会注明该卫星在另一站**可能有**信息
（`merge_hint` 字段给出 URL 提示）。

## Permissions

- **网络出口**：
  - `https://www.eoportal.org`（Next.js SPA，需要 Playwright）
  - `https://space.oscar.wmo.int`（可服务端解析的 HTML / CSV 导出）
  - 默认**直连**（在墙内两个站都是墙外站，国内网络可直连测试过）。
  - 通过 `SATELLITE_SEARCH_USE_PROXY=1` 强制走系统代理（`HTTP_PROXY`/`HTTPS_PROXY`），
    默认端口 7897。
- **环境变量读取**：
  - `SATELLITE_SEARCH_USE_PROXY`（决定是否走代理）
  - `SATELLITE_SEARCH_DATA_DIR`（覆盖默认 `data/` 路径）
  - `SATELLITE_SEARCH_NO_PLAYWRIGHT=1`（Playwright 未装时跳过在线抓取）
- **文件读取**：`data/*.jsonl` 与 `data/*.json`（本地索引）
- **文件写入**：`data/` 目录（更新本地索引）

## Notes

- **第一次在线抓取会下载 Playwright Chromium**（~100MB）。本 skill 的 `search/info/list`
  不需要 Playwright，只有 `fetch` / `update` 需要。
- OSCAR 列表页有 **Export CSV** 按钮，本 skill 直接走它等价的 POST 接口，
  一次拿全量 ~900 颗卫星的元信息。
- eoPortal 是 Next.js，列表需要 Playwright 渲染；从渲染后的 DOM 提取卫星名 + 详情 URL。
- 本地索引每条记录 ≤ 5 KB，~2000 颗卫星总索引约 5-10 MB，可整个塞进仓库。
- **数据陈旧性**：快照于首次发布；想用新数据可跑 `update` 子命令重抓。

## 输出示例

```bash
$ python scripts/satellite_search.py search "高分"

# 高分系列 (从 eoportal 本地索引命中)
1. 高分一号 (GF-1)        eoportal · 2013-04-26 · 退役
2. 高分二号 (GF-2)        eoportal · 2014-08-19 · 运营中
3. 高分三号 (GF-3)        eoportal · 2016-08-10 · 运营中
...
```

## License

MIT-0 — 详见 [LICENSE](./LICENSE)。
eoPortal 数据 © ESA；OSCAR 数据 © WMO。本 skill 仅做只读抓取与本地缓存。
