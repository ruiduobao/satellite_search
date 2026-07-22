# Changelog

All notable changes to `satellite_search` are documented here.
The skill follows [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-07-22

### Added
- **eoPortal 详情页全量抓取**：内置 Playwright + stealth（隐藏 webdriver、
  模拟 Chrome runtime、navigator.plugins、languages、WebGL），4 并发
  增量持久化，覆盖 1000+ 颗卫星的 detail / Quick facts / FAQ。
- **`scripts/scrape_eoportal_details.py`**：批量抓 eoPortal 详情，
  支持 `--concurrency` / `--retries` / `--shuffle` / `--only-slug`。
- **`scripts/online_fallback.py`**：对抓不到的 slug 跑 web search（site:
  eoportal.org），结果存到 `data/web_search_results.jsonl`，给用户
  "原始出处"指引。
- **`scripts/build_detailed_index.py`**：合并 detail 数据到 merged_index，
  让 `info` 直接展示 summary / FAQ / applications。
- **`core/online_search.py` 重写**：3 个引擎兜底（crawl4ai-skill DuckDuckGo
  → web_search skill → duckduckgo.com-direct）。
- **CLI `info` 输出增强**：展示 eoPortal summary、FAQ Q&A、last_updated。
- **CLI `fetch` 自动兜底**：eoPortal 抓失败时自动跑 web search，
  `--no-online-fallback` 可关闭。

### Changed
- **`core/local_index.info()`**：自动用 eoportal record 的 `detail` 字段
  作为优先数据源，无需重新抓。
- 数据规模：~1000 颗 eoPortal 详情（agency/launch/instruments/FAQ）
  + 1038 OSCAR 列表 = 离线可查 2130 颗；fetch 失败时自动 search。

## [0.1.0] — 2026-07-22

### Added
- 首次发布。
- **离线优先**：内置 `data/eoportal_satellites.jsonl` + `data/oscar_satellites.jsonl` +
  合并去重的 `data/merged_index.json`，本地秒级查询。
- **5 个 CLI 子命令**：`search` / `info` / `list` / `fetch` / `stats` (+ `update` 内部用)。
- **在线兜底**：
  - eoPortal —— Playwright 渲染 Next.js 列表页，抓卫星名 + 详情 URL，可选抓详情。
  - OSCAR —— 走网站等价的 CSV 导出 POST 接口，一次拉全量 ~900 颗。
- **多源合并**：`info` 命令同时返回 eoPortal / oscar 两个原始 payload + 一个
  `merged` 汇总（agency、orbit、status、sources_count）。
- **中文友好**：`search` 对"高分"、"风云"、"资源"等中文关键词做包含匹配。
- **代理可切**：`SATELLITE_SEARCH_USE_PROXY=1` 走系统代理（默认 `http://127.0.0.1:7897`），
  默认直连。
- 20+ 项 e2e 测试覆盖本地索引加载、模糊搜索、双源合并、CLI 出参。
