# Examples

## Sample outputs

### `info` on Landsat-9 (multi-source merge)

```
$ python scripts/satellite_search.py info Landsat-9
# Landsat-9
  Aliases: Landsat Data Continuity Mission
  Sources: eoportal, oscar
  Agency:  USGS NASA
  Launch:  27 Sep 2021
  EOL:     ≥2031
  Status:  Operational
  Orbit:   SunSync, alt 705 km
  Instruments (2): OLI TIRS
  Coverage: 2 of 2 sources

  eoPortal: https://www.eoportal.org/satellite-missions/landsat-9
  OSCAR:    https://space.oscar.wmo.int/satellites/view/724
```

### `search` with Chinese keyword

```
$ python scripts/satellite_search.py search "高分" --limit 5
Top 5 matches for '高分' (source=both):

   1. [OSCAR]    GF-1                 | Gao Fen                        | CNSA | launch=26 Apr 2013
   2. [OSCAR]    GF-1-02              | Gao Fen                        | CNSA | launch=31 Mar 2018
   3. [OSCAR]    GF-10                | Gao Fen                        | CNSA | launch=04 Oct 2019
   4. [EOPORTAL] GF-1 (Gaofen-1)                          | slug=gaofen-1
   5. [EOPORTAL] GF-2 (Gaofen-2)                          | slug=gaofen-2

5 satellites
```

### `list` (combined, limited)

```
$ python scripts/satellite_search.py list --limit 8
SOURCE  NAME                     AGENCY  LAUNCH       ORBIT    STATUS
-------------------------------------------------------------------------
oscar   3D-Winds                 NASA    TBD          SunSync  Mission concept
oscar   ACE                      NASA    25 Aug 1997  L1       Operational
oscar   ACE (Aer.Clo.Eco.)       NASA    TBD          SunSync  Mission concept
eoportal Aalto-1: The Finnish Student Nanosatellite            | url=...
...
```

See the top-level `SKILL.md` / `README.md` for full docs.
