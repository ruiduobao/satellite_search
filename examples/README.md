# 示例

## 输出示例

### `info` 在 Landsat-9 上的输出（多源合并 + 中文翻译）

```
$ python scripts/satellite_search.py info Landsat-9
# Landsat-9  / 陆地卫星 9 号
  别名：Landsat Data Continuity Mission
  数据源：eoPortal, oscar
  运营方：USGS, NASA
  发射：2021-09-27
  退役：≥2031
  状态：在轨运行
  轨道：太阳同步轨道，高度 705 km
  仪器（2 个）：OLI, TIRS
  覆盖：2/2 个数据源

  简介（https://www.eoportal.org/satellite-missions/landsat-9）：
    Landsat-9 于 2021 年 9 月发射，由美国国家航空航天局（NASA）和美国地质调查局
    （USGS）合作运营，作为陆地卫星计划的一部分，继续采集和存档中分辨率多光谱
    数据，免费提供给全球用户使用。
  FAQ（3 条）：
    Q: Landsat-9 的分辨率是多少？
    A: 不同光谱波段分辨率不同。热红外波段 100 m，多光谱波段 30 m，全色波段 15 m。
    Q: Landsat-9 由谁发射？
    A: 由 NASA 和 USGS 于 2021 年 9 月发射，设计寿命 5 年...
    Q: Landsat-9 将做什么？
    A: Landsat-9 与 Landsat-8 共面运行，提供数据连续性...

  eoPortal: https://www.eoportal.org/satellite-missions/landsat-9
  OSCAR:    https://space.oscar.wmo.int/satellites/view/724
```

### `search` 中文关键词

```
$ python scripts/satellite_search.py search "高分" --limit 5
'高分' 的 5 条最匹配结果（数据源=both）：

   1. [OSCAR]    GF-1                 | 高分系列                        | CNSA | 发射=2013-04-26
   2. [OSCAR]    GF-1-02              | 高分系列                        | CNSA | 发射=2018-03-31
   3. [OSCAR]    GF-10                | 高分系列                        | CNSA | 发射=2019-10-04
   4. [EOPORTAL] GF-1 (Gaofen-1) 高分一号                          | slug=gaofen-1
   5. [EOPORTAL] GF-2 (Gaofen-2) 高分二号                          | slug=gaofen-2

共 5 颗
```

### `list`（合并，限制 8 条）

```
$ python scripts/satellite_search.py list --limit 8
数据源    名称                                       运营方        发射          轨道        状态
---------------------------------------------------------------------------------------------------------
oscar   3D-Winds                                  NASA       TBD         SunSync   任务概念
oscar   ACE                                       NASA       1997-08-25  L1        在轨运行
oscar   ACE (Aer.Clo.Eco.)                        NASA       TBD         SunSync   任务概念
eoportal Aalto-1: The Finnish Student Nanosatellite    Aalto University  2017-06-23  SunSync  已退役
...

共 8 颗
```

详见顶层 `SKILL.md` / `README.md`。
