# satellite_search · 卫星参数查询

> 把 **eoPortal**（ESA）+ **WMO OSCAR** + **CelesTrak**（NORAD）+ **SatNOGS** 四个最权威的
> 遥感卫星参数源整合进一个本地优先的 skill，所有介绍性内容都已翻译成中文，面向中文用户。
> MIT-0 开源。
> **v0.4.1 加固**：所有外部请求（web 搜索 / LLM 翻译 / 浏览器指纹）都有显式隐私提示和
> `SATELLITE_SEARCH_NO_*=1` opt-out 环境变量；LLM 翻译的 prompt 已加固防 prompt injection。

## 为什么做这个

做遥感工作第一步是查卫星参数（传感器、分辨率、波段、轨道、幅宽、运营方）。百度搜出来的
要么是新闻，要么是博客，参数散落且彼此打架。

最准的查询方式是：
- 卫星**官网**（每个卫星单独查，麻烦）
- **eoPortal**（ESA 支持，~1,100 颗，文字介绍最详细）
- **WMO OSCAR**（世界气象组织，~1,000 颗，波段/轨道表结构化好）
- **CelesTrak**（美国国防部 NORAD 太空目标目录，70,000+ 条记录 1957 至今）
- **SatNOGS**（业余 / 立方星社区数据库，~1,700 在轨）

这个 skill 把 4 个站抓下来打包成本地索引 + 翻译，并提供 CLI 让"查卫星"这件事变成本地
一次查询。中文用户直接看中文，英文原文保留供核对。

## Quickstart

```bash
# 搜索（中文 / 英文 / NORAD 数字）
python scripts/satellite_search.py search landsat
python scripts/satellite_search.py search "高分"
python scripts/satellite_search.py search "Sentinel-2"
python scripts/satellite_search.py search STARLINK --source celestrak
python scripts/satellite_search.py search 25544  # ISS by NORAD id

# 详细参数（4 源合并）
python scripts/satellite_search.py info "Sentinel-2A"
python scripts/satellite_search.py info "FY-4A"
python scripts/satellite_search.py info "高分三号"
python scripts/satellite_search.py info 25544 --lang en

# 本地列表
python scripts/satellite_search.py list --source oscar --limit 20
python scripts/satellite_search.py list --source eoportal --limit 20
python scripts/satellite_search.py list --source celestrak --limit 20
python scripts/satellite_search.py list --source all --limit 20

# 在线抓取（本地没有的）
python scripts/satellite_search.py fetch "高分三号" --source eoportal

# 看索引大小
python scripts/satellite_search.py stats
```

## 数据规模（v0.4.0）

| 数据源 | 收录规模 | 数据特点 |
|---|---|---|
| **eoPortal** | 1,128 颗（列表 + 1,070 颗详情 + 中文翻译） | 文字介绍、Quick facts、FAQ Q&A、国产卫星覆盖好 |
| **WMO OSCAR** | 1,038 颗（列表） | 轨道/传感器/波段表结构化 |
| **CelesTrak SATCAT** | 70,006 条全量 / **19,627 条在轨有效载荷** | NORAD 目录号、轨道周期、倾角、远地点、近地点、发射场、运营方国家 |
| **SatNOGS DB** | 1,688 alive + 1,016 re-entered | 业余 / 立方星社区数据、运营方、官网、引用 |
| **合并去重** | **~21,000 颗** | 跨 4 源（UCS 计划 v0.5.0） |
| **中文翻译** | 540 颗 eoPortal summary/FAQ | 通过 mimo-v2.5-pro LLM 批量翻译 |

⚠️ 数据版权归各原始数据源所有（eoPortal © ESA、OSCAR © WMO、CelesTrak © U.S. Government、
SatNOGS © CC BY-SA 4.0），本 skill 仅做**只读抓取与本地缓存**，用于学术研究和教育用途。

## 子命令

| 子命令 | 用途 |
|---|---|
| `search <keyword\|norad>` | 本地索引模糊搜索（4 源 / NORAD 直查） |
| `info <name\|norad>` | 多源合并的详细参数（默认中文） |
| `list` | 列出本地索引卫星 |
| `fetch <name>` | 在线抓取（覆盖/补充本地） |
| `stats` | 看本地索引统计（4 源） |
| `update` | 重新抓取全量并更新本地索引（4 源） |
| `translate` | 用 LLM 翻译 eoPortal 介绍到中文 |

## 数据格式

`info` / `search` 返回的 JSON 字段（中英双语，4 源合并）：

```json
{
  "name": "Sentinel-2A",
  "name_zh": "哨兵-2A",
  "norad_id": 40697,
  "sources": ["eoportal", "oscar", "celestrak"],
  "eoportal": {
    "agency_zh": "欧空局",
    "summary_zh": "哨兵-2 是哥白尼计划的一部分...",
    "summary_en": "Sentinel-2 is part of the Copernicus programme...",
    "applications_zh": ["陆表监测", "应急响应"],
    "faq_zh": [{"q": "...", "a": "..."}],
    "url": "https://www.eoportal.org/..."
  },
  "oscar": { "...": "..." },
  "celestrak": {
    "NORAD_CAT_ID": 40697,
    "OBJECT_NAME": "SENTINEL-2A",
    "OBJECT_TYPE": "PAY",
    "object_type_zh": "有效载荷（卫星本体）",
    "OWNER": "ESA",
    "owner_zh": "欧洲空间局",
    "PERIOD": 100.65,
    "INCLINATION": 98.57
  },
  "merged": { "agency": "ESA, EC", "norad_id": 40697, "sources_count": 3 }
}
```

详见 [SKILL.md](./SKILL.md) 的 "Output Contract" 段。

## 网络 / 代理

默认直连（4 个站都是墙外但国内直连测试可达）。
通过 `SATELLITE_SEARCH_USE_PROXY=1` 强制走系统代理（默认直连）。

## 翻译说明

eoPortal 卫星的中文翻译通过 `mimo-v2.5-pro`（OpenAI 协议）批量完成。翻译结果存到
`data/eoportal_satellites_zh.jsonl`，合并到 `merged_index.json` 后由 CLI 默认输出。
英文原文保留为 `summary_en` / `faq_en` / `applications_en` 等字段，供溯源对照。

CelesTrak / SatNOGS 的枚举值（国家代码、状态码、轨道类型）通过 `core/i18n.py` 中的
静态字典翻译为中文（如 `OWNER='ISS'` → `owner_zh='国际空间站'`、
`OBJECT_TYPE='PAY'` → `object_type_zh='有效载荷（卫星本体）'`）。

## License

MIT-0（详见 [LICENSE](./LICENSE)）。
数据来源：eoPortal © ESA、OSCAR © WMO、CelesTrak © U.S. Government、SatNOGS © CC BY-SA 4.0。
