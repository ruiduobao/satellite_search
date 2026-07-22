# data 目录

这个目录存的是 skill 自带的离线索引。**首次发布时随仓库打包**，不需要重新抓。

## 文件清单（v0.4.0）

| 文件 | 格式 | 内容 | 大小 | 抓取时间 |
|---|---|---|---|---|
| `eoportal_satellites.jsonl` | JSON Lines | eoPortal 1,100+ 卫星列表 + 详情（agency/launch/instruments/summary/FAQ） | ~1.3 MB | 首次发布 |
| `eoportal_satellites_zh.jsonl` | JSON Lines | eoPortal 中文翻译（name_zh / summary_zh / faq_zh 等） | ~0.5 MB | 首次发布（mimo-v2.5-pro 翻译） |
| `oscar_satellites.jsonl` | JSON Lines | WMO OSCAR 1,000+ 卫星列表（含 orbit/launch/agency/payload） | ~0.5 MB | 首次发布 |
| `celestrak_satellites.jsonl` | JSON Lines | CelesTrak SATCAT 全量（70,000+ 空间目标 1957 至今，含有效载荷 / 火箭箭体 / 碎片） | ~25 MB | 首次发布 |
| `celestrak_active_payloads.jsonl` | JSON Lines | CelesTrak SATCAT 有效载荷子集（19,600+ 在轨工作的卫星，无 DECAY_DATE 且 OBJECT_TYPE=PAY） | ~7 MB | 首次发布 |
| `satnogs_alive.jsonl` | JSON Lines | SatNOGS DB 在轨业余 / 小卫星（1,600+ alive） | ~0.8 MB | 首次发布 |
| `satnogs_reentered.jsonl` | JSON Lines | SatNOGS DB 已陨落小卫星（1,000+ re-entered） | ~0.5 MB | 首次发布 |
| `merged_index.json` | JSON | 多源去重合并的轻量索引（OSCAR + eoPortal 按 name 合并；CelesTrak / SatNOGS 按 norad:ID 合并） | ~2.4 MB | 首次发布 |
| `scrape_report.json` | JSON | 抓取日志（每源多少条、失败列表） | <1 KB | 每次抓取更新 |
| `web_search_results.jsonl` | JSON Lines | 对 eoPortal 抓不到的 slug 跑 web search 的结果 | <100 KB | 兜底抓取时生成 |
| `eoportal_details_failed.jsonl` | JSON Lines | 多次重试后仍失败的 slug + 错误 | <50 KB | 抓取时生成 |

## 数据源说明

### 1. eoPortal（ESA）
- 1100+ 遥感 / 通信 / 导航 / 科学卫星的官方介绍页
- 字段：name / agency / launch_date / status / summary / applications / instruments / FAQ
- 抓取：Next.js `__NEXT_DATA__` JSON（1.4 秒 1128 条）+ Playwright stealth 详情页（4 并发，~20 分钟）
- 详情页用 stealth 注入隐藏 webdriver / 模拟 chrome.runtime / WebGL vendor

### 2. WMO OSCAR
- 1000+ 气象 / 地球观测卫星的运行信息
- 字段：acronym / launch / eol / programme / agencies / orbit / altitude / inclination / ect / status / instruments
- 抓取：POST `/satellites` 触发 "Export" 按钮直下 XLSX（4 秒 1038 条）

### 3. CelesTrak SATCAT
- 美国国防部太空目标目录（NORAD）
- 70,000+ 条记录：含 19,600+ 在轨有效载荷 + ~50,000 火箭箭体 / 碎片
- 字段：NORAD_CAT_ID / OBJECT_NAME / OBJECT_TYPE（PAY/R/B/DEB/UNK）/ OWNER / LAUNCH_DATE / LAUNCH_SITE / PERIOD / INCLINATION / APOGEE / PERIGEE / ORBIT_CENTER / ORBIT_TYPE / DECAY_DATE
- 抓取：`https://celestrak.org/pub/satcat.csv`（6.6 MB CSV）
- **active_payloads** 子集 = `OBJECT_TYPE='PAY' AND DECAY_DATE=''`

### 4. SatNOGS DB
- 业余 / 大学 / 立方星社区维护的数据库
- 1,600+ alive + 1,000+ re-entered
- 字段：norad_cat_id / name / status / operator / countries / website / citation
- 抓取：`https://db.satnogs.org/api/satellites/?format=json&status=alive`（一次性返回所有 alive，~9 秒）

## 重新抓取

```bash
# 重抓 OSCAR 列表（推荐，速度快）
python scripts/satellite_search.py update --source oscar

# 重抓 eoPortal 列表
python scripts/satellite_search.py update --source eoportal

# 重抓 CelesTrak SATCAT（CSV ~6.6 MB，~3 秒下载 + 解析）
python scripts/satellite_search.py update --source celestrak

# 重抓 SatNOGS（~9 秒）
python scripts/satellite_search.py update --source satnogs

# 重抓所有源 + 重建 merged 索引
python scripts/satellite_search.py update --source all

# 重抓 eoPortal 详情（~30 分钟，4 并发 + Playwright stealth）
python scripts/scrape_eoportal_details.py --shuffle --concurrency 4 --retries 3

# 重新翻译 eoPortal 介绍到中文（4 并发 LLM 调用，~20 分钟）
python scripts/translate_descriptions.py --concurrency 4

# 重建 merged_index.json（多源合并）
python scripts/build_detailed_index.py
# 注意：v0.4.0 起 update --source all 会自动重建；build_detailed_index.py
# 旧版只处理 OSCAR + eoPortal，要支持新源请改用 update

# 对详情抓不到的 slug 跑 web search 兜底
python scripts/online_fallback.py
```

## 数据规模

- `eoportal_satellites.jsonl`：~1,100 条 × ~1.2 KB = ~1.3 MB
- `eoportal_satellites_zh.jsonl`：~540 条 × ~0.9 KB = ~0.5 MB
- `oscar_satellites.jsonl`：~1,000 条 × ~0.5 KB = ~0.5 MB
- `celestrak_satellites.jsonl`：~70,000 条 × ~0.4 KB = ~25 MB
- `celestrak_active_payloads.jsonl`：~19,600 条 × ~0.4 KB = ~7 MB
- `satnogs_alive.jsonl`：~1,700 条 × ~0.5 KB = ~0.8 MB
- `satnogs_reentered.jsonl`：~1,000 条 × ~0.5 KB = ~0.5 MB
- `merged_index.json`：~21,000 条去重后 × ~0.1 KB = ~2.4 MB
- 合计 < 38 MB

## License

数据版权归各原始数据源所有：

- eoPortal — ESA 公开数据，仅限研究 / 教育用途
- WMO OSCAR — 公共领域（CC BY 4.0 等同条款）
- CelesTrak — 公共领域（U.S. Government work）
- SatNOGS — DB 内容遵循 CC BY-SA 4.0

本目录的 JSON 文件仅供学术研究 / 教育用途。
