# Data directory

这个目录存的是 skill 自带的离线索引。**首次发布时随仓库打包**，不需要重新抓。

## 文件清单

| 文件 | 格式 | 内容 | 抓取时间 |
|---|---|---|---|
| `eoportal_satellites.jsonl` | JSON Lines | eoPortal 1100+ 卫星列表 + 详情（agency/launch/instruments/summary/FAQ） | 首次发布 |
| `oscar_satellites.jsonl` | JSON Lines | OSCAR 1000+ 卫星列表（含 orbit/launch/agency/payload） | 首次发布 |
| `merged_index.json` | JSON | 双源去重合并的轻量索引（含 eoPortal detail 字段） | 首次发布 |
| `scrape_report.json` | JSON | 抓取日志（每源多少条、失败列表） | 每次抓取更新 |
| `web_search_results.jsonl` | JSON Lines | 对 eoPortal 抓不到的 slug 跑 web search 的结果 | 兜底抓取时生成 |
| `eoportal_details_failed.jsonl` | JSON Lines | 多次重试后仍失败的 slug + 错误 | 抓取时生成 |

## 重新抓取

```bash
# 重抓 OSCAR 列表（推荐，速度快）
python scripts/satellite_search.py update --source oscar

# 重抓 eoPortal 列表
python scripts/satellite_search.py update --source eoportal

# 重抓 eoPortal 详情（~30 分钟，4 并发 + Playwright stealth）
python scripts/scrape_eoportal_details.py --shuffle --concurrency 4 --retries 3

# 重建 merged_index.json
python scripts/build_detailed_index.py

# 对详情抓不到的 slug 跑 web search 兜底
python scripts/online_fallback.py
```

## 数据规模

- `eoportal_satellites.jsonl`：~1100 条 × ~3 KB（含 detail）= ~3.3 MB
- `oscar_satellites.jsonl`：~1000 条 × ~0.5 KB = ~500 KB
- `merged_index.json`：~2000 条去重后 × ~2 KB = ~4 MB
- `web_search_results.jsonl`：~50-200 条 × ~0.5 KB = <100 KB
- 合计 < 10 MB

## License

数据版权归 eoPortal (ESA) 和 OSCAR (WMO) 所有。本目录的 JSON 文件仅供学术研究 / 教育用途。
