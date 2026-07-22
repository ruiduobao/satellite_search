# Changelog

All notable changes to `satellite_search` are documented here.
The skill follows [Semantic Versioning](https://semver.org/).

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
