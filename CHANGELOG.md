# 更新日志

所有显著的改动都记录在此。版本号遵循 [语义化版本](https://semver.org/)。

## [0.3.0] — 2026-07-22

### 新增
- **中文翻译**：调用 mimo-v2.5-pro（OpenAI 协议）批量翻译 eoPortal
  全部 1100+ 颗卫星的 `name` / `summary` / `applications` / `faq` / `status` /
  `agency` 等字段，结果存到 `data/eoportal_satellites_zh.jsonl`。
- **双语输出**：`info` 命令默认输出中文（`name_zh` / `summary_zh` /
  `applications_zh` / `faq_zh`），英文原文保留为 `*_en` 字段供溯源核对。
- **新增 `--lang` 选项**：`info --lang en` 只看英文，`--lang both` 双语并列。
- **`scripts/translate_descriptions.py`**：批量翻译脚本，支持
  `--concurrency` / `--limit` / `--only-slug`，增量持久化。
- **`scripts/translate_status.py`**：把 OSCAR 的 status / programme /
  orbit / agency 等枚举值映射成中文（覆盖 Sentinel 计划的所有衍生任务）。
- **`core/online_search.py`** 同步支持中文查询。

### 变更
- **所有用户文档翻译为中文**：SKILL.md / README.md / CHANGELOG.md /
  openai.yaml / data/README.md / examples/README.md。
- **CLI 全部字符串中文化**：argparse help / 提示 / 错误信息 / 列表
  表头。
- `core/local_index.info()`：合并 payload 增加 `*_zh` 字段。

## [0.2.0] — 2026-07-22

### 新增
- **eoPortal 详情页全量抓取**：内置 Playwright + stealth（隐藏 webdriver、
  模拟 Chrome runtime、navigator.plugins、languages、WebGL），4 并发
  增量持久化，覆盖 1100+ 颗卫星的 detail / Quick facts / FAQ。
- **`scripts/scrape_eoportal_details.py`**：批量抓 eoPortal 详情，
  支持 `--concurrency` / `--retries` / `--shuffle` / `--only-slug`。
- **`scripts/online_fallback.py`**：对抓不到的 slug 跑 web search（site:
  eoportal.org），结果存到 `data/web_search_results.jsonl`，给用户
  "原始出处"指引。
- **`scripts/build_detailed_index.py`**：合并 detail 数据到 merged_index。
- **`core/online_search.py` 重写**：3 个引擎兜底（crawl4ai-skill DuckDuckGo
  → web_search skill → duckduckgo.com-direct）。
- **CLI `info` 输出增强**：展示 eoPortal summary、FAQ Q&A、last_updated。
- **CLI `fetch` 自动兜底**：eoPortal 抓失败时自动跑 web search。

### 变更
- **`core/local_index.info()`**：自动用 eoportal record 的 `detail` 字段
  作为优先数据源。
- 数据规模：~1100 颗 eoPortal 详情 + 1038 OSCAR 列表 = 离线可查 2130 颗。

## [0.1.0] — 2026-07-22

### 新增
- 首次发布。
- **离线优先**：内置 `data/eoportal_satellites.jsonl` + `data/oscar_satellites.jsonl` +
  合并去重的 `data/merged_index.json`，本地秒级查询。
- **5 个 CLI 子命令**：`search` / `info` / `list` / `fetch` / `stats`。
- **在线兜底**：
  - eoPortal —— Playwright 渲染 Next.js 列表页，抓卫星名 + 详情 URL。
  - OSCAR —— 走网站等价的 CSV 导出 POST 接口，一次拉全量 ~900 颗。
- **多源合并**：`info` 命令同时返回 eoPortal / oscar 两个原始 payload + 一个
  `merged` 汇总。
- **中文友好**：`search` 对"高分"、"风云"、"资源"等中文关键词做包含匹配。
- **代理可切**：`SATELLITE_SEARCH_USE_PROXY=1` 走系统代理。
- 20+ 项 e2e 测试。
