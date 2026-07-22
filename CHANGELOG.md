# 更新日志

所有显著的改动都记录在此。版本号遵循 [语义化版本](https://semver.org/)。

## [0.4.0] — 2026-07-22

### 新增

- **CelesTrak SATCAT 整合**：新增美国国防部太空目标目录（NORAD）。
  - 全量 70,006 条记录（1957 至今），含有效载荷 / 火箭箭体 / 碎片
  - 有效载荷子集 19,627 条（`OBJECT_TYPE='PAY' AND DECAY_DATE=''`）
  - 字段：NORAD_CAT_ID / OBJECT_NAME / OBJECT_TYPE（PAY/R/B/DEB/UNK）/
    OWNER / LAUNCH_DATE / LAUNCH_SITE / PERIOD / INCLINATION /
    APOGEE / PERIGEE / ORBIT_CENTER / ORBIT_TYPE / DECAY_DATE
  - **NORAD 数字查询**：1-6 位数字自动识别为 NORAD 目录号，跨 4 源直查
  - 抓取：`https://celestrak.org/pub/satcat.csv`（6.6 MB CSV，~3 秒下载）
- **SatNOGS DB 整合**：新增业余 / 大学 / 立方星社区维护的数据库。
  - 1,688 条 alive + 1,016 条 re-entered = 2,704 条
  - 字段：norad_cat_id / name / status / operator / countries / website / citation
  - 抓取：`https://db.satnogs.org/api/satellites/?format=json&status=alive`（~9 秒）
- **多源 NORAD 跨参**：`info` 命令查某颗卫星时，会通过 NORAD id 把
  eoPortal / OSCAR 的文字介绍和 CelesTrak / SatNOGS 的轨道参数 / 运营方
  国家 / 状态码关联起来——`info 25544` 一次拿到 ISS 的 eoPortal 介绍 + OSCAR
  仪器清单 + CelesTrak 轨道周期 92.96 min + SatNOGS 状态。
- **5 源 i18n 枚举翻译**：
  - CelesTrak：3 字母国家代码（US/CIS/PRC/J/ISS/ESA/...）
  - CelesTrak：OBJECT_TYPE（PAY/R/B/DEB/UNK）
  - CelesTrak：ORBIT_CENTER（EA/MO/MA/SA/...）
  - CelesTrak：ORBIT_TYPE（ORB/LAN/IMP/...）
  - SatNOGS：status（alive/dead/re-entered/future/unknown）
  - UCS：orbit_class（LEO/MEO/GEO/HEO/SSO）+ purpose（21 个常用值）
- **CLI `--source` 扩展到 4 源**：
  `search --source celestrak|satnogs|ucs|all` / `list --source all` /
  `update --source celestrak|satnogs|all`
- **CLI `info` 输出扩展**：
  - CelesTrak 块：轨道周期 / 倾角 / 远地点 / 近地点 / 发射场 / 在轨状态
  - SatNOGS 块：状态 / 运营方 / 国家代码 / 官网 / 引用
  - UCS 块：发射质量 / 设计寿命 / 运载火箭 / 制造商
- **CLI `update --source all` 自动重建多源 merged 索引**：
  旧 `build_detailed_index.py` 只处理 OSCAR + eoPortal，新版 update 会同时
  把 CelesTrak / SatNOGS 按 `norad:N` 键合并进 merged_index.json。
- **`scripts/scrape_celestrak.py`** + **`scripts/scrape_satnogs.py`**：
  两个新的独立抓取脚本（可单独运行）；scrape_satnogs 支持 `--status` 过滤。
- **19 项新单元 + e2e 测试**（`tests/test_local_index.py` + `test_cli.py`）：
  - CelesTrak 搜索（STARLINK / ISS ZARYA）
  - NORAD id 直查（25544 → ISS）
  - `_is_norad_id` 边界测试（1-6 位数字 + 拒绝 7 位）
  - CelesTrak 数据类反序列化 `to_celestrak_record`
  - SatNOGS 数据类反序列化 `to_satnogs_record`
  - i18n 翻译函数（country_zh / celestrak_object_type_zh /
    celestrak_orbit_center_zh / satnogs_status_zh / ucs_orbit_class_zh /
    ucs_purpose_zh）
  - `list_satellites(source="all")` 跨 4 源

### 变更

- **数据规模**：从 2,130 颗扩到 **~21,000 颗**（2,130 OSCAR+eoPortal +
  ~19,600 CelesTrak 在轨有效载荷 + 1,700 SatNOGS alive，去重后）。
- **`core/models.py`**：新增 `CelestrakRecord` / `SatnogsRecord` /
  `UcsRecord` 三个 dataclass；`ALL_SOURCES` 现在 5 个。
- **`core/local_index.py`** 重写：
  - 新增 `all_celestrak()` / `all_celestrak_active()` / `all_satnogs()` /
    `all_satnogs_alive()` / `all_ucs()` 访问器
  - `search()` 现在跨 4 源（+ UCS 占位）+ NORAD id 直查
  - `info()` 自动用 NORAD id 跨源关联（eoPortal/OSCAR 文字介绍 ↔
    CelesTrak 轨道参数 ↔ SatNOGS 状态）
  - 新增 `to_celestrak_record()` / `to_satnogs_record()` / `to_ucs_record()`
  - `list_satellites(source="all")` 跨 4 源合并
- **`core/i18n.py`** 新增 6 个翻译函数 + 6 个常量表。
- **`scripts/satellite_search.py`**：CLI 全面支持 4 源；`stats` 命令
  报告所有 5 源统计（`celestrak_total` / `celestrak_active_payloads` /
  `satnogs_total` / `satnogs_alive` / `ucs`）；`update --source all` 会
  自动跑 scrape_celestrak.py + scrape_satnogs.py + 重建 merged 索引。
- **`data/README.md`** 重写：v0.4.0 文件清单（38 MB 总规模），新增
  CelesTrak / SatNOGS 抓取流程。

### 已知限制

- **UCS Satellite Database 未整合**（`ucs` 源暂为空）：UCS 已下线
  公开 S3 bucket（`https://s3.amazonaws.com/ucs-documents/.../Sat-database-*.txt`）
  现 403。v0.5.0 计划通过 web search 找新下载源，或在 eoPortal / CelesTrak
  找不到时按需补一条。**所有 UCS 相关代码已就绪**，只是没有数据。
- **CelesTrak 搜索默认走 active_payloads**（19.6k）以保持响应速度；
  70k 全量只用于 NORAD id 直查和 `--source celestrak` 显式指定。
- **`scrape_satnogs.py` 不写 `satnogs_all.jsonl`**，避免混淆；
  alive 写到 `satnogs_alive.jsonl`，re-entered 写到 `satnogs_reentered.jsonl`。
- **首次 `update` 拉取 CelesTrak** ~6.6 MB CSV（~3 秒下载 + 解析），
  SatNOGS ~9 秒，eoPortal 列表 ~2 秒，OSCAR 列表 ~4 秒。

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
