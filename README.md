# satellite_search · 卫星参数查询

> 把 **eoPortal** (ESA) 和 **WMO OSCAR** 两个最权威的遥感卫星参数源整合进一个本地优先的 skill，
> 离线查得着就不用联网，本地没有就现场抓。

## 为什么做这个

做遥感工作第一步是查卫星参数（传感器、分辨率、波段、轨道、幅宽、运营方）。
百度搜出来的要么是新闻，要么是博客，参数散落且彼此打架。

最准的查询方式是：
- 卫星**官网**（每个卫星单独查，麻烦）
- **eoPortal** —— ESA 支持，~1000+ 颗，文字介绍最详细
- **WMO OSCAR** —— 世界气象组织，~900 颗，波段/轨道表结构化好

这个 skill 把两个站抓下来打包成本地索引，并提供 CLI 让"查卫星"这件事变成本地一次查询。

## Quickstart

```bash
# 搜索
python scripts/satellite_search.py search landsat
python scripts/satellite_search.py search "高分"
python scripts/satellite_search.py search "Sentinel-2"

# 详细参数
python scripts/satellite_search.py info "Sentinel-2A"
python scripts/satellite_search.py info "FY-4A"

# 本地列表
python scripts/satellite_search.py list --source oscar --limit 20
python scripts/satellite_search.py list --source eoportal --limit 20

# 在线抓取（本地没有的）
python scripts/satellite_search.py fetch "高分三号" --source eoportal
```

## 数据源

| 源 | URL | 收录规模 | 强项 |
|---|---|---|---|
| eoPortal | https://www.eoportal.org/satellite-missions | ~1000+ 颗 | 文字介绍、发射历史、应用领域、国产卫星覆盖好 |
| WMO OSCAR | https://space.oscar.wmo.int/satellites | ~900 颗 | 轨道/传感器/波段表结构化 |

⚠️ 数据版权归 ESA 和 WMO 所有，本 skill 仅做**只读抓取与本地缓存**，
用于学术研究和教育用途。

## 子命令

| 子命令 | 用途 |
|---|---|
| `search <keyword>` | 本地索引模糊搜索 |
| `info <name>` | 多源合并的详细参数 |
| `list` | 列出本地索引卫星 |
| `fetch <name>` | 在线抓取（覆盖/补充本地） |
| `stats` | 看本地索引统计 |
| `update` | 重新抓取全量并更新本地索引 |

## 数据格式

`info` / `search` 返回的 JSON：

```json
{
  "name": "Sentinel-2A",
  "aliases": ["S2A"],
  "sources": ["eoportal", "oscar"],
  "eoportal": { "url": "...", "agency": "ESA", "summary": "..." },
  "oscar":    { "url": "...", "orbit_type": "SunSync", "instruments": [...] },
  "merged":   { "agency": "ESA", "orbit": "SunSync, 786 km" }
}
```

详见 [SKILL.md](./SKILL.md) 的 "Output Contract" 段。

## 网络 / 代理

默认直连（两个站都是墙外但国内直连测试可达）。
通过 `SATELLITE_SEARCH_USE_PROXY=1` 强制走系统代理（默认 `http://127.0.0.1:7897`）。

## License

MIT-0（详见 [LICENSE](./LICENSE)）。
eoPortal 数据 © ESA；OSCAR 数据 © WMO。
