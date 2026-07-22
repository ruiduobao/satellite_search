# Data directory

这个目录存的是 skill 自带的离线索引。**首次发布时随仓库打包**，不需要重新抓。

## 文件清单

| 文件 | 格式 | 内容 | 抓取时间 |
|---|---|---|---|
| `eoportal_satellites.jsonl` | JSON Lines | eoPortal 卫星列表（~1000+） | 首次发布 |
| `oscar_satellites.jsonl` | JSON Lines | OSCAR 卫星列表（~900） | 首次发布 |
| `merged_index.json` | JSON | 双源去重合并的轻量索引（只保留 name/aliases/source/quick 字段） | 首次发布 |
| `scrape_report.json` | JSON | 抓取日志（每源多少条、失败列表） | 首次发布 |

## 重新抓取

```bash
# 重抓 OSCAR（推荐，速度快）
python scripts/satellite_search.py update --source oscar

# 重抓 eoPortal（需要 Playwright，慢）
python scripts/satellite_search.py update --source eoportal

# 两个都重抓
python scripts/satellite_search.py update
```

## 数据规模

- `eoportal_satellites.jsonl`：~1000 条 × ~3 KB = ~3 MB
- `oscar_satellites.jsonl`：~900 条 × ~2 KB = ~2 MB（CSV 导出）
- `merged_index.json`：~1500 条去重后 × ~1 KB = ~1.5 MB
- 合计 < 10 MB

## License

数据版权归 eoPortal (ESA) 和 OSCAR (WMO) 所有。本目录的 JSON 文件仅供学术研究 / 教育用途。
