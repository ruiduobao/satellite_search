"""Chinese translations for OSCAR / eoPortal enum values.

Both data sources ship with English enum values (orbit types, status,
agency names, etc.). The CLI displays the Chinese translation by default
and shows the original English in parentheses if it differs.

Keep the table narrow and idiomatic; do not translate acronyms like
"NASA" or "ESA" — those are proper nouns.
"""

from __future__ import annotations

from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Orbit / status / programme translations
# ---------------------------------------------------------------------------

ORBIT_ZH: Dict[str, str] = {
    "SunSync": "太阳同步轨道",
    "GEO": "地球静止轨道",
    "DRIFT": "漂移轨道（低轨非太阳同步）",
    "L1": "日地 L1 点",
    "L4-L5": "日地 L4/L5 点",
    "Molniya": "闪电轨道（高椭圆，12 小时）",
    "TAP": "高椭圆轨道（16 小时）",
    "Tundra": "冻原轨道（24 小时）",
    "GeoSync": "地球同步倾斜轨道",
    "Ecliptic": "黄道轨道",
    "Solar": "太阳轨道",
    "Moon": "月球轨道",
    "MAG": "磁层穿越轨道",
}


STATUS_ZH: Dict[str, str] = {
    "Operational": "在轨运行",
    "Operational (nominal)": "在轨运行（标称）",
    "Operational (extended)": "在轨运行（延寿）",
    "Mission complete": "任务完成",
    "Mission concept": "任务概念阶段",
    "Planned": "规划中",
    "Inactive": "已停止运行",
    "Lost at launch": "发射失败",
    "Decayed": "陨落",
    "Re-entered": "再入大气层",
    "Failed": "任务失败",
    "Unknown": "未知",
    "Unclear": "状态不明",
    "Launch failure": "发射失败",
}


# Satellite names / programme names — small, curated dictionary
NAME_ZH: Dict[str, str] = {
    "Landsat": "陆地卫星",
    "Sentinel-1": "哨兵-1",
    "Sentinel-2": "哨兵-2",
    "Sentinel-3": "哨兵-3",
    "Sentinel-4": "哨兵-4",
    "Sentinel-5": "哨兵-5",
    "Sentinel-5P": "哨兵-5P",
    "Sentinel-6": "哨兵-6",
    "Gaofen": "高分",
    "Gao Fen": "高分",
    "Feng-Yun": "风云",
    "FengYun": "风云",
    "Zi Yuan": "资源",
    "Huanjing": "环境",
    "Haiyang": "海洋",
    "Tiangong": "天宫",
    "Shijian": "实践",
    "Kuaizhou": "快舟",
    "Yaogan": "遥感",
    "Jilin": "吉林",
    "BeiDou": "北斗",
    "China-Brazil Earth Resources Satellite": "中巴地球资源卫星",
    "CBERS": "中巴地球资源卫星",
    "Communications": "通信",
    "Earth Observation": "对地观测",
    "Navigation": "导航",
    "Science": "科学",
    "Technology": "技术试验",
    "Meteorological": "气象",
}


# Agency / country — keep acronym proper, translate organization type
AGENCY_SUFFIX_ZH = {
    "Space Agency": "航天局",
    "Aeronautics and Space Administration": "航空航天局",
    "Geological Survey": "地质调查局",
    "Meteorological Administration": "气象局",
    "Oceanic and Atmospheric Administration": "海洋与大气管理局",
}


# Programme / application translations
PROGRAMME_ZH: Dict[str, str] = {
    "Copernicus": "哥白尼计划",
    "Earth Explorer": "地球探测者计划",
    "Living Planet": "活力星球计划",
    "Disaster Monitoring Constellation": "灾害监测星座",
}


# Country / measurement domain
DOMAIN_ZH: Dict[str, str] = {
    "Atmosphere": "大气",
    "Land": "陆地",
    "Ocean": "海洋",
    "Snow & Ice": "冰雪",
    "Gravity and Magnetic Fields": "重力与磁场",
}


# Common application categories
APPLICATION_ZH: Dict[str, str] = {
    "Multi-purpose imagery (land)": "陆地多用途成像",
    "Multi-purpose imagery (ocean)": "海洋多用途成像",
    "Cloud type, amount and cloud top temperature": "云类型、云量与云顶温度",
    "Ocean colour/biology": "海洋水色/生物",
    "Land surface topography": "陆表地形",
    "Vegetation": "植被",
    "Aerosols": "气溶胶",
    "Soil moisture": "土壤水分",
    "Sea surface temperature": "海表温度",
    "Sea ice cover, edge and thickness": "海冰覆盖、边缘与厚度",
    "Snow cover, edge and depth": "积雪覆盖、边缘与深度",
    "Atmospheric humidity": "大气湿度",
    "Atmospheric temperature": "大气温度",
    "Atmospheric wind": "大气风场",
    "Trace gases": "痕量气体",
    "Ozone": "臭氧",
    "Precipitation": "降水",
    "Lightning": "闪电",
    "Land cover": "土地覆盖",
    "Ocean salinity": "海洋盐度",
    "Ocean topography/currents": "海洋地形/洋流",
}


# Common instrument types
INSTRUMENT_TYPE_ZH: Dict[str, str] = {
    "Imaging multi-spectral radiometers (vis/IR)": "可见光/红外多光谱成像辐射计",
    "Imaging multi-spectral radiometers (passive microwave)": "被动微波多光谱成像辐射计",
    "Imaging microwave radars": "成像微波雷达（SAR）",
    "High resolution optical imagers": "高分辨率光学成像仪",
    "Hyperspectral imagers": "高光谱成像仪",
    "Lidars": "激光雷达（LiDAR）",
    "Atmospheric chemistry": "大气化学",
    "Atmospheric temperature and humidity sounders": "大气温湿度探测仪",
    "Radar altimeters": "雷达高度计",
    "Scatterometers": "散射计",
    "Precision orbit": "精密定轨",
    "Magnetic field": "磁场测量",
    "Gravity instruments": "重力测量",
    "Communications": "通信",
    "Data collection": "数据采集",
    "Earth radiation budget radiometers": "地球辐射收支辐射计",
    "Multiple direction/polarisation radiometers": "多方向/偏振辐射计",
    "Ocean colour instruments": "海洋水色仪",
    "Lightning sensors": "闪电探测仪",
    "Space environment": "空间环境",
    "In situ": "原位探测",
    "Other": "其他",
    "TBD": "待定",
}


# ---------------------------------------------------------------------------
# Translation helpers
# ---------------------------------------------------------------------------

def orbit_zh(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    return ORBIT_ZH.get(s, s)


def status_zh(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    return STATUS_ZH.get(s, s)


def domain_zh(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return DOMAIN_ZH.get(s.strip(), s)


def application_zh(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return APPLICATION_ZH.get(s.strip(), s)


def instrument_type_zh(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return INSTRUMENT_TYPE_ZH.get(s.strip(), s)


def programme_zh(s: Optional[str]) -> Optional[str]:
    """Translate common programme names like Copernicus."""
    if s is None:
        return None
    return PROGRAMME_ZH.get(s.strip(), s)


def name_zh_hint(s: Optional[str]) -> Optional[str]:
    """Best-effort Chinese hint for a programme/series name. Returns None
    if no translation is available so the caller can keep the English
    fallback."""
    if not s:
        return None
    s = s.strip()
    # Try exact match first
    if s in NAME_ZH:
        return NAME_ZH[s]
    # Try substring: "Sentinel-1A" → 哨兵-1A
    for k, v in NAME_ZH.items():
        if k in s or s.startswith(k):
            return s.replace(k, v)
    return None
