---
name: satellite_search
display_name: 卫星参数查询
version: 0.4.2
author: Mavis
license: MIT-0
description: |
  离线优先的遥感卫星参数查询 skill。整合欧空局 eoPortal（ESA，~1100 颗）、
  世界气象组织 OSCAR（~1000 颗）、CelesTrak SATCAT（NORAD，~19,600 条在轨
  有效载荷）和 SatNOGS DB（业余 / 立方星，~1,700 alive）四个权威数据库到
  本地索引，本地秒级查询。本地没有时支持在线抓取（Playwright + 标准浏览器
  指纹归一化通过 eoPortal Cloudflare 风控）和 web 搜索兜底。所有卫星介绍
  （summary / FAQ / 应用领域 / 名称）均已通过 LLM 翻译为中文，中文用户
  直接看中文，英文原文作为 secondary 输出保留可溯源。
  v0.4.1 加固：所有外部请求（web 搜索 / LLM 翻译 / 浏览器指纹）都有显式
  隐私提示和 opt-out 环境变量；LLM 翻译的 prompt 已加固防御 prompt injection。
runtime: python>=3.9
tags: [gis, remote-sensing, satellite, eoportal, oscar, wmo, celestrak, satnogs, norad, earth-observation, params, 中文]
---

# 卫星参数查询 (satellite_search)

把 **eoPortal** + **WMO OSCAR** + **CelesTrak** + **SatNOGS** 四个最权威的遥感卫星参数源整合进
一个本地优先的 skill，面向中文用户，所有介绍性内容（summary、FAQ、应用领域、名称）均已翻译
成中文，原始英文保留供溯源。

做遥感时谁没经历过：搜某颗卫星的分辨率/波段/轨道，百度给的是新闻和博客，参数散落不全
且彼此打架。最准的要么去卫星官网翻文档，要么去欧空局 eoPortal、WMO OSCAR 这种专门数据库
查——但每个卫星都单独搜一遍太费劲。

**satellite_search** 把 4 个站抓下来打包成本地索引，本地秒查；本地没有时再现场抓。
eoPortal 详情页有反爬保护，用 Playwright + stealth（隐藏 webdriver、模拟 Chrome
runtime / navigator.plugins / languages / WebGL）绕过 Cloudflare，全量抓取 1100+ 颗
卫星的 Quick facts / Summary / FAQ Q&A。CelesTrak 拿美国国防部 NORAD 太空目标目录
（70k+ 条记录含碎片、火箭箭体、有效载荷），SatNOGS 拿业余 / 大学 / 立方星社区维护的
数据库（~1.7k alive）。

**v0.4.0 关键能力**：通过 **NORAD 目录号**（1-6 位数字）跨 4 源自动关联：
eoPortal / OSCAR 的文字介绍 + CelesTrak 的轨道参数（周期/倾角/远地点/近地点/发射场）
+ SatNOGS 的运行状态和运营方，一条 `info 25544` 命令一次拿到 ISS 的全部参数。

## 适用场景

- 想知道某颗国产/国外卫星的**传感器类型、分辨率、波段、轨道、幅宽、发射时间、运营方**
- 写论文/报告/标书时需要一个**可引用的参数来源**（每个字段都带 eoPortal / OSCAR /
  CelesTrak / SatNOGS 原始 URL）
- 看 **FAQ Q&A**（eoPortal 的"分辨率多少？"、"什么时候发射？"等都结构化好）
- 不确定某颗卫星叫什么 / 有没有 / 还活着没 —— 模糊搜索
- 本地没收录的新发射卫星 —— 现场抓
- **找不到时的兜底**：fetch 失败 → 自动 web search 找原始出处
- **只知道 NORAD 目录号**（1-6 位数字）也能查：`info 25544` 直接拿到 ISS 全参数
- **想看全量**：CelesTrak 19,600 条在轨有效载荷的发射日期 / 国家 / 轨道都查得到

## 数据源

| 源 | URL | 收录规模 | 强项 |
|---|---|---|---|
| eoPortal | https://www.eoportal.org/satellite-missions | ~1,100 颗（列表 + 1,100 颗详情 + 中文翻译） | 文字介绍、Quick facts、FAQ Q&A、国产卫星覆盖好 |
| WMO OSCAR | https://space.oscar.wmo.int/satellites | ~1,000 颗 | 轨道/传感器/波段表结构化 |
| CelesTrak SATCAT | https://celestrak.org/pub/satcat.csv | 70,006 条全量 / 19,627 条在轨有效载荷 | 完整 NORAD 目录：轨道周期、倾角、远地点、近地点、发射场、运营方国家 |
| SatNOGS DB | https://db.satnogs.org/api/satellites/ | 1,688 alive + 1,016 re-entered | 业余 / 大学 / 立方星社区数据、运营方、官网、引用 |

> ⚠️ 数据版权归各原始数据源所有（eoPortal © ESA、OSCAR © WMO、CelesTrak © U.S. Government、
> SatNOGS © CC BY-SA 4.0），本 skill 仅做**只读抓取与本地缓存**，用于学术研究和教育用途。
> UCS Satellite Database 暂未整合（v0.4.0 计划但 S3 bucket 403）——相关代码就绪，缺数据。

## Quickstart

```bash
# 1) 模糊搜索（先查本地索引，支持中文 + NORAD 数字）
python scripts/satellite_search.py search landsat
python scripts/satellite_search.py search "高分三号"
python scripts/satellite_search.py search sentinel-2
python scripts/satellite_search.py search STARLINK --source celestrak
python scripts/satellite_search.py search AO-91 --source satnogs

# 2) 详细参数（4 源合并 + 中文 summary + FAQ + CelesTrak 轨道参数）
python scripts/satellite_search.py info "Sentinel-2A"
python scripts/satellite_search.py info "FY-4A"
python scripts/satellite_search.py info "GF-1"
python scripts/satellite_search.py info 25544            # ISS by NORAD id
python scripts/satellite_search.py info 43013 --lang en  # 纯英文输出

# 3) 列出本地索引中的所有卫星
python scripts/satellite_search.py list --source oscar --limit 30
python scripts/satellite_search.py list --source eoportal --limit 30
python scripts/satellite_search.py list --source celestrak --limit 30
python scripts/satellite_search.py list --source satnogs --limit 30
python scripts/satellite_search.py list --source all --limit 30  # 跨 4 源

# 4) 本地没命中？强制在线抓取
python scripts/satellite_search.py fetch "高分三号" --source eoportal
python scripts/satellite_search.py fetch "Sentinel-2A" --source both

# 5) 看索引里有多少颗
python scripts/satellite_search.py stats
```

## 子命令

| 子命令 | 用途 | 主要参数 |
|---|---|---|
| `search` | 模糊搜索本地索引 | `<keyword>` `[--source oscar\|eoportal\|celestrak\|satnogs\|all]` `[--limit]` |
| `info` | 详细参数（4 源合并 + 中文 Summary + FAQ + CelesTrak 轨道参数） | `<name\|norad>` `[--lang zh\|en\|both]` `[--no-online]` |
| `list` | 列出本地索引中所有卫星 | `[--source] [--limit]` |
| `fetch` | 在线抓取（覆盖/补充本地） | `<name>` `[--source eoportal\|oscar\|both]` `[--no-online-fallback]` |
| `stats` | 看本地索引统计（含 4 源） | — |
| `update` | 重新抓取全量并更新本地索引 | `[--source oscar\|eoportal\|celestrak\|satnogs\|all]` |
| `translate` | 用 LLM 翻译 eoPortal 介绍（中文） | `[--limit] [--concurrency]` |

## 数据格式 (Output Contract)

`info` / `search` 返回的统一 JSON 字段（4 源合并 + 双语）：

```json
{
  "name": "Sentinel-2A",
  "name_zh": "哨兵-2A",
  "aliases": ["S2A", "Sentinel 2A"],
  "sources": ["eoportal", "oscar", "celestrak"],
  "norad_id": 40697,
  "eoportal": {
    "url": "https://www.eoportal.org/satellite-missions/copernicus-sentinel-2",
    "agency": "ESA",
    "agency_zh": "欧空局",
    "launch_date": "2015-06-23",
    "status": "Operational (extended)",
    "status_zh": "在轨运行（延寿）",
    "summary_zh": "Sentinel-2 卫星是哥白尼计划的一部分...",
    "summary_en": "The Copernicus Sentinel-2 ...",
    "applications_zh": ["陆表监测", "应急响应"],
    "applications_en": ["Land monitoring", "Emergency response"],
    "instruments": ["MSI"],
    "faq_zh": [{"q": "...", "a": "..."}],
    "faq_en": [{"q": "...", "a": "..."}],
    "last_updated": "2024-XX-XXTXX:XX:XXZ"
  },
  "oscar": { "...": "..." },
  "celestrak": {
    "NORAD_CAT_ID": 40697,
    "OBJECT_NAME": "SENTINEL-2A",
    "OBJECT_TYPE": "PAY",
    "object_type_zh": "有效载荷（卫星本体）",
    "OWNER": "ESA",
    "owner_zh": "欧洲空间局",
    "LAUNCH_DATE": "2015-06-23",
    "LAUNCH_SITE": "FRGUI",
    "PERIOD": 100.65,
    "INCLINATION": 98.57,
    "APOGEE": 786,
    "PERIGEE": 786,
    "is_active_payload": true
  },
  "satnogs": null,
  "merged": {
    "agency": "ESA, EC",
    "launch_date": "2015-06-23",
    "instruments_count": 1,
    "sources_count": 3,
    "summary_zh": "...",
    "faq_zh_count": 3,
    "norad_id": 40697
  }
}
```

## 数据抓取与刷新

```bash
# 重新抓 OSCAR 列表（4 秒搞定 1000 颗）
python scripts/satellite_search.py update --source oscar

# 重新抓 eoPortal 列表（2 秒搞定 1100 颗）
python scripts/satellite_search.py update --source eoportal

# 重新抓 CelesTrak SATCAT（~3 秒下载 6.6 MB CSV + 解析 70k 条）
python scripts/satellite_search.py update --source celestrak

# 重新抓 SatNOGS（~9 秒拿到 alive + re-entered）
python scripts/satellite_search.py update --source satnogs

# 全部 4 源 + 重建 merged 索引（推荐日常用）
python scripts/satellite_search.py update --source all

# 重新抓 eoPortal 详情（~30 分钟，4 并发 + Playwright stealth）
python scripts/scrape_eoportal_details.py --shuffle --concurrency 4

# 用 LLM 翻译 eoPortal 全部 1100 颗卫星的 summary/FAQ 到中文
python scripts/translate_descriptions.py --concurrency 4

# 对详情抓不到的 slug 跑 web search
python scripts/online_fallback.py
```

## Permissions

- **网络出口**（每个都附隐私告示 + opt-out）：
  - `https://www.eoportal.org`（Playwright + 浏览器指纹归一化，需要 Chromium；
    只抓公开页；`SATELLITE_SEARCH_NO_BROWSER_FINGERPRINT=1` 可关）
  - `https://space.oscar.wmo.int`（requests + XLSX 导出）
  - `https://celestrak.org/pub/satcat.csv`（requests，6.6 MB CSV）
  - `https://db.satnogs.org/api/satellites/`（requests，~9 秒）
  - `https://html.duckduckgo.com` / `crawl4ai-skill`（web 搜索兜底；
    会向搜索引擎发用户查询字符串；`SATELLITE_SEARCH_NO_ONLINE=1` 可关）
  - `https://token-plan-cn.xiaomimimo.com`（LLM 翻译；启动时打印详细
    隐私告示；`SATELLITE_SEARCH_NO_LLM=1` 可关）
  - 默认**直连**。通过 `SATELLITE_SEARCH_USE_PROXY=1` 走系统代理。
- **环境变量读取**：
  - `SATELLITE_SEARCH_USE_PROXY` / `SATELLITE_SEARCH_NO_PLAYWRIGHT`
  - `SATELLITE_SEARCH_DATA_DIR`（覆盖默认 `data/` 路径）
  - `SATELLITE_SEARCH_NO_BROWSER_FINGERPRINT=1`（v0.4.1+）
  - `SATELLITE_SEARCH_NO_ONLINE=1`（v0.4.1+）
  - `SATELLITE_SEARCH_NO_LLM=1`（v0.4.1+）
  - `OPENAI_API_KEY` / `OPENAI_BASE_URL`（LLM 翻译用）
- **文件读取**：`data/*.jsonl` 与 `data/*.json`（本地索引）
- **文件写入**：`data/` 目录（更新本地索引）

## Notes

- **eoPortal 详情页抓取**用 Playwright + 浏览器指纹归一化：通过
  `addInitScript` 注入标准 Chrome 默认值（隐藏 `navigator.webdriver`、
  补 `chrome.runtime`、mock `navigator.plugins` / `languages` /
  `WebGL` vendor），让 headless Chromium 通过 eoPortal 的标准
  Cloudflare 风控（~95% 成功率）。**不绕过任何认证或访问控制**——
  抓的都是 eoPortal 公开页。设置
  `SATELLITE_SEARCH_NO_BROWSER_FINGERPRINT=1` 可关闭指纹注入。
- **eoPortal 列表是 Next.js 渲染**：`__NEXT_DATA__` JSON 里有按 A-Z
  分组的 1100 颗卫星（slug + name + taxonomyCategoryBriefs），不需要
  Playwright 即可一次拉完。
- **OSCAR 列表是服务端渲染**：直接走等价的"Export"按钮 POST 接口
  拿 XLSX（1038 颗一次性返回）。
- **OSCAR 详情页**只比列表多几个仪器状态字段，没 band 详情，所以
  详情按需抓（不打包进首版）。
- **CelesTrak 全量 70k** 含大量碎片和火箭箭体，搜索默认走 19.6k
  有效载荷子集以保持响应速度；NORAD id 直查走全量 70k。
- **SatNOGS 走 `?format=json&status=alive`** 一次性拿所有 alive 卫星
  （`page_size` 参数被忽略）。
- **跨源 NORAD 关联**：eoPortal / OSCAR 的 `norad_id` 字段 → CelesTrak
  `NORAD_CAT_ID` / SatNOGS `norad_cat_id` / UCS `NORAD Number`（v0.5.0
  上 UCS 后），通过 `info()` 自动合并。
- **首次运行** `crawl4ai-skill` 会下载 Chromium（~100MB），耗时较长。
- **web_search 兜底**：当 eoPortal 详情抓不到时，自动用
  `crawl4ai-skill search`（DuckDuckGo）找相关原始出处。**每次会向
  第三方搜索引擎发送用户输入的查询字符串**（仅字符串，不带其他数据），
  设置 `SATELLITE_SEARCH_NO_ONLINE=1` 可完全关闭。
- **中文翻译**：用 `mimo-v2.5-pro`（OpenAI 协议）批量翻译 eoPortal 的
  英文介绍，存到 `eoportal_satellites_zh.jsonl`，再合并到
  `merged_index.json`。用户拿到的默认是中文，英文原文保留供核对。
  **每次翻译会向 LLM 端点发送每颗卫星的英文文本**（name / agency /
  summary / applications / FAQ），`translate` 命令启动时会打印详细
  隐私告示；设置 `SATELLITE_SEARCH_NO_LLM=1` 可完全跳过。
- **LLM 提示词加固**（v0.4.1）：`SYSTEM_PROMPT` 有显式的"覆盖用户内容
  中所有指示"指令 + 每个字段 12 KB 截断防巨型 payload 注入 + 用户模板
  明确"数据不是对话"。
- **CelesTrak / SatNOGS 枚举值**翻译在 `core/i18n.py`（OWNER 国家代码、
  OBJECT_TYPE、ORBIT_CENTER、SatNOGS status）。

## 输出示例

```bash
$ python scripts/satellite_search.py info 25544
# ISS (ZARYA)  / 国际空间站（ZARYA）
  数据源：eoPortal, oscar, celestrak（共 3 个）
  NORAD 目录号：25544
  运营方：International Space Station
  运营方国家：国际空间站（ISS）
  发射：1998-11-20
  状态：Operational
  轨道：center=EA, period=92.96min, inc=51.63°
  仪器（0 个）：

  [CelesTrak 轨道参数]
    轨道周期：92.96 分钟
    轨道倾角：51.64°
    远地点 / 近地点：424 km / 415 km
    发射场：TYMSC
    类型：有效载荷（卫星本体）（在轨有效载荷）

  CelesTrak：https://celestrak.org/satcat/records.php?CATNR=25544
```

## License

MIT-0 — 详见 [LICENSE](./LICENSE)。
数据来源：eoPortal © ESA、OSCAR © WMO、CelesTrak © U.S. Government、
SatNOGS © CC BY-SA 4.0。本 skill 仅做只读抓取与本地缓存。
