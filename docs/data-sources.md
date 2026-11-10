# Data sources

Every input to the pipeline, verified against its official source before any pipeline code was written. Each fact links to where it came from. Dates are when the check was done.

## 1.1 Sentinel-2 imagery (Digital Earth Australia)

Checked 2026-11-09.

### STAC endpoint

`https://explorer.dea.ga.gov.au/stac`

Source: the DEA Knowledge Hub [STAC guide](https://knowledge.dea.ga.gov.au/guides/setup/gis/stac/) connects with `pystac_client.Client.open("https://explorer.dea.ga.gov.au/stac")`. The page shows no last-updated date.

### Collections

Sentinel-2 Analysis Ready Data (ARD), Collection 3. Product names are used as STAC collection IDs.

| Collection ID | Satellite | Items from | Items to (at check) |
|---|---|---|---|
| `ga_s2am_ard_3` | Sentinel-2A | 2015-07-12 | 2026-11-08 |
| `ga_s2bm_ard_3` | Sentinel-2B | 2017-06-30 | 2026-11-08 |
| `ga_s2cm_ard_3` | Sentinel-2C | 2025-01-21 | 2026-11-08 |

Source: `https://explorer.dea.ga.gov.au/stac/collections` (101 collections, one page). All three are current, so searches should include all three.

The [2A product page](https://knowledge.dea.ga.gov.au/data/product/dea-surface-reflectance-nbart-sentinel-2a-msi/) says coverage ends 21 Jan 2025, but the catalogue has 2A items up to the check date. The catalogue is treated as authoritative for availability.

Not used: `esa_s2*m_level1_0` (raw Level-1, not ARD). Possibly useful later: `ga_s2_ba_provisional_3` (provisional burnt area, 2021-07 to 2023-08).

### Band assets

| Purpose | Asset key | Alias | Sentinel-2 band | Equivalent wavelength | Pixel size |
|---|---|---|---|---|---|
| Narrow NIR | `nbart_nir_2` | `nbart_band8a` | B8A | 864.7 nm | 20 m |
| SWIR2 for NBR | `nbart_swir_3` | `nbart_band12` | B12 | 2202.4 nm | 20 m |

`nbart_swir_2` is **B11** (1613.7 nm), not B12. DEA numbers SWIR bands from B10, so the band NBR calls "SWIR2" is DEA's `nbart_swir_3`.

All `nbart_*` bands: `int16`, nodata `-999`, valid range 1–10,000 (reflectance × 10,000). The scale cancels out in NBR.

CRS: "Multiple UTM zone CRSs". Each tile is in its own UTM zone (WGS84 datum).

Source: [DEA Surface Reflectance NBART (Sentinel-2A MSI)](https://knowledge.dea.ga.gov.au/data/product/dea-surface-reflectance-nbart-sentinel-2a-msi/), Specifications tab.

### Cloud mask (fmask)

Asset `oa_fmask`: `uint8`, 20 m, nodata 0.

| Value | Meaning | Pipeline rule |
|---|---|---|
| 0 | null | drop |
| 1 | clear | **keep** |
| 2 | cloud | drop |
| 3 | cloud shadow | drop |
| 4 | snow | drop |
| 5 | water | drop |

Source: [DEA Surface Reflectance OA (Sentinel-2A MSI)](https://knowledge.dea.ga.gov.au/data/product/dea-surface-reflectance-oa-sentinel-2a-msi/), Specifications tab.

Not used: `oa_s2cloudless_mask`. The OA page's Known Issues says s2cloudless is affected from 25 Jan 2022 to 7 Jun 2024 and recommends fmask instead.

To consider: `oa_nbart_contiguity` (10 m, 1 = valid in every band, 0 = not) as an extra mask.

### Item properties

From a sample item and the test search below:

| Property | Use |
|---|---|
| `eo:cloud_cover` | Whole-tile cloud %, for ranking scenes |
| `fmask:clear`, `fmask:cloud`, `fmask:cloud_shadow`, `fmask:water`, `fmask:snow` | Whole-tile % per fmask class |
| `odc:region_code` | Sentinel-2 tile ID (e.g. `56HKH`) |
| `odc:dataset_version` | Per-item processing version (e.g. `3.2.1`), for provenance |
| `proj:code` | Tile CRS (e.g. `EPSG:32756`). Some newer items have no `proj:epsg`, so read `proj:code` |

Item IDs are UUIDs, so record tile and date alongside them.

### Test search

All three collections, bbox `150.2,-33.8,150.5,-33.6` (Blue Mountains), October 2026: **16 items over 8 dates** (a new image every 2–5 days).

Every date returned **two tiles in two CRSs**, `56HKH` (EPSG:32756) and `55HGC` (EPSG:32755), because the box crosses the UTM zone 55/56 boundary at 150°E. Cloud % differs between the two tiles on the same date (e.g. 27 Oct: 15.8% vs 3.4%).

Consequence for 2.1: choose the least cloudy **date**, then load all of that date's tiles together onto one CRS. Choosing a single item could cover only part of a fire.

To repeat the search:

```sh
curl -sS "https://explorer.dea.ga.gov.au/stac/search?collections=ga_s2am_ard_3,ga_s2bm_ard_3,ga_s2cm_ard_3&bbox=150.2,-33.8,150.5,-33.6&datetime=2026-10-01/2026-10-31&limit=50" | python3 -c "
import json, sys
for f in json.load(sys.stdin)['features']:
    p = f['properties']
    print(p['datetime'][:10], p.get('odc:region_code'), f\"{p.get('eo:cloud_cover', 0):5.1f}%\", f['collection'], p.get('proj:code'))"
```

Docs:
- [STAC API item search](https://github.com/radiantearth/stac-api-spec/tree/main/item-search)
- [DEA STAC guide](https://knowledge.dea.ga.gov.au/guides/setup/gis/stac/)

### Licence and citation

CC BY 4.0.

- NBART: Geoscience Australia, 2022. Geoscience Australia Sentinel-2A MSI NBART Collection 3 - DEA Surface Reflectance NBART (Sentinel-2A MSI). Geoscience Australia, Canberra. https://dx.doi.org/10.26186/146571
- OA: Geoscience Australia, 2022. Geoscience Australia Sentinel-2A Observation Attributes Collection 3 - DEA Surface Reflectance OA (Sentinel-2A MSI). Geoscience Australia, Canberra. https://dx.doi.org/10.26186/146568

The 2B and 2C products have their own product pages and DOIs; add those citations if their data is used.

## 1.2 FESM reference data

Checked 2026-11-09, for the 2023/24 fire year. Other seasons need the same `gdalinfo` check before use.

### Seasons

FESM is published per fire year (1 July to 30 June) on SEED. Seasons seen: 2016/17, 2019/20, 2020/21, 2021/22, 2023/24, 2024/25 (2022/23 not seen in search results; not ruled out). From 2025-26, near real-time wildfire mapping is published during the season.

Version: FESMv3. Method, in the dataset's words: "a semi-automated approach to mapping fire extent and severity through a machine learning framework based on sentinel 2 satellite imagery", described in [Gibson et al. 2020, Remote Sensing of Environment](https://doi.org/10.1016/j.rse.2020.111702) (Sentinel-2 and random forest). So FESM and this project use the same satellite, with different methods.

Source: [FESM 2023/24 on SEED](https://datasets.seed.nsw.gov.au/dataset/fire-extent-and-severity-mapping-fesm-2023-24) and its [full metadata](https://datasets.seed.nsw.gov.au/dataset/fire-extent-and-severity-mapping-fesm-2023-24/metaexport/html).

### Download

Wildfires, TIFF format ("FESM WFs 2023-24 - Tiff format"), statewide:

| Item | Value |
|---|---|
| URL | `https://datasets.seed.nsw.gov.au/dataset/f8e725eb-132d-43bf-b6bc-31048540fb53/resource/f4956478-df15-4757-bc21-4b50cd596598/download/fire_fesm_20232024.zip` |
| SEED dataset ID | `f8e725eb-132d-43bf-b6bc-31048540fb53` |
| Zip size | 22.2 MB (page); 23 MB downloaded |
| SHA-256 (zip) | `718940ab7df33045e98bc9b33786b1ec78413fa13a2b96defd711777292df10e` |
| Unzipped | 6 files, 352,706,704 bytes: `FESM2324.tif` (270 MB), `.tif.ovr` (83 MB), `.tif.aux.xml`, `.tif.vat.dbf`, `.tif.vat.cpg`, `.tfw` |
| Login | None needed for the download |

Hazard reduction burns are a separate package ("FESM HRs 2023-24 Tiff format", 22.2 MB) and are not used.

The zip's entries are plain file names (no absolute paths or `..`), checked with `unzip -l` before extracting.

### Raster

From `gdalinfo data/fesm/2023-24/FESM2324.tif` (GDAL 3.13.3):

| Property | Value |
|---|---|
| CRS | **EPSG:3308**, GDA94 / NSW Lambert (Lambert Conic Conformal 2SP, metres) |
| Size | 173,458 × 102,271 pixels |
| Origin (top-left) | 8,714,580 E, 5,045,059 N |
| Pixel size | **9.982420184 m** (not exactly 10 m, although the metadata says 10 m) |
| Data type | Byte |
| NoData | **255** |
| Values present | 0 to 5 |
| Storage | LZW compression, 128×128 tiles, 9 overview levels in the external `.ovr` |

The metadata page gives the CRS code as 4283. That is GDA94's geographic base CRS inside EPSG:3308, not the raster's CRS; the file itself says EPSG:3308.

### Severity classes

From the raster attribute table embedded with the file (`.tif.vat.dbf`, rows dated 16/7/2024):

| Value | Label | Definition |
|---|---|---|
| 0 | Unburnt | Unburnt surface with green canopy |
| 1 | Burnt grassland/open grassy woodland | Burnt grassland/open grassy woodland (the "extent only" class) |
| 2 | Low severity | Burnt surface with unburnt canopy |
| 3 | Moderate severity | Partial canopy scorch |
| 4 | High severity | Full canopy scorch (+/- partial canopy consumption) |
| 5 | Extreme severity | Full canopy consumption |
| 255 | NoData | |

Value 0 covers the whole state outside burnt areas (mean pixel value 0.008), so a 0 only means "unburnt patch" inside a fire outline (1.3).

Consequences for the pipeline:
- Your severity map is resampled onto FESM's grid (EPSG:3308, 9.98242 m) with nearest neighbour (2.5), not onto a round 10 m grid.
- Class 1 has no severity order relative to 2 to 5, so it is "not comparable" in the disagreement map (2.6).

### Licence and citation

CC BY 4.0. Required attribution: "© State Government of NSW and NSW Department of Climate Change, Energy, the Environment and Water 2024".

Citation (from SEED): © State Government of NSW and NSW Department of Climate Change, Energy, the Environment and Water 2024, Fire Extent and Severity Mapping (FESM) 2023/24, accessed from The Sharing and Enabling Environmental Data Portal [https://datasets.seed.nsw.gov.au/dataset/f8e725eb-132d-43bf-b6bc-31048540fb53], date accessed 2026-11-09.

### To repeat the checks

```sh
mkdir -p data/fesm/2023-24 && curl -fL -o data/fesm/2023-24/fire_fesm_20232024.zip "https://datasets.seed.nsw.gov.au/dataset/f8e725eb-132d-43bf-b6bc-31048540fb53/resource/f4956478-df15-4757-bc21-4b50cd596598/download/fire_fesm_20232024.zip"
shasum -a 256 data/fesm/2023-24/fire_fesm_20232024.zip
unzip -l data/fesm/2023-24/fire_fesm_20232024.zip
unzip -n data/fesm/2023-24/fire_fesm_20232024.zip -d data/fesm/2023-24/
gdalinfo data/fesm/2023-24/FESM2324.tif
```

Docs:
- [gdalinfo](https://gdal.org/en/stable/programs/gdalinfo.html)
- [curl manual](https://curl.se/docs/manpage.html)

## 1.3 Fire outline source

Checked 2026-11-09.

### Decision

**Use NPWS fire history outlines**, because they are independent of both FESM and the dNBR map, and they carry fire names and dates.

FESM's own burnt area was the alternative. It was rejected because an outline drawn from FESM can only test agreement where FESM says it burned (FESM omissions could never be found), and because FESM is one statewide raster per season with no names, dates or per-fire separation.

Two safeguards for the weaknesses of NPWS outlines:
- **Coverage:** only choose fires present in both datasets, i.e. an NPWS wildfire polygon that overlaps FESM burnt pixels (1.4).
- **Precision:** compare inside a slightly shrunk outline (about 50 m inwards), so the outline's coarser edges are not counted as disagreement (2.5).

### Dataset

NPWS Fire History - Wildfires and Prescribed Burns, on SEED. Fire boundaries captured by NPWS regions from incident and burn mapping, GPS, flown boundaries, hand-drawn maps digitised at 1:25,000, and remote sensing. Polygons "often extend outside NPWS Estate"; data from the Rural Fire Service and Forestry Corporation NSW is imported "at times", so fires on private land may be missing. Stated spatial resolution: 50 m.

Source: [dataset page](https://datasets.seed.nsw.gov.au/dataset/fire-history-wildfires-and-prescribed-burns-1e8b6) and [full metadata](https://datasets.seed.nsw.gov.au/dataset/1d05e145-80cb-4275-af9b-327a1536798d/metaexport/html).

### Download

| Item | Value |
|---|---|
| URL | `https://datasets.seed.nsw.gov.au/dataset/1d05e145-80cb-4275-af9b-327a1536798d/resource/3853d6c0-6517-4cba-8482-68f93a6d43b1/download/fire_npwsfirehistory.zip` |
| SEED dataset ID | `1d05e145-80cb-4275-af9b-327a1536798d` |
| Snapshot | Downloaded 2026-11-09; files exported 2026-11-05 (`DBF_DATE_LAST_UPDATE`) |
| Zip size | 61 MB downloaded (page says 57.6 MB, likely from an older edition) |
| SHA-256 (zip) | `20c698c2e8f0015414f2504eead281d0bac4998698cd1a13d2ceac0e592af656` |
| Unzipped | 8 files, 118,202,554 bytes: `NPWSFireHistory.shp` (84 MB), `.dbf` (34 MB), `.shx`, `.prj`, `.cpg`, `.sbn`, `.sbx`, `.shp.xml` |

The dataset is republished regularly (the metadata says monthly), so this checksum identifies the 2026-11-09 snapshot only. Later downloads will differ; keep the snapshot date with the checksum.

Also available as live WMS/WFS services: `https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/Fire/NPWS_Fire_History/MapServer`.

The zip's entries are plain file names (no absolute paths or `..`), checked with `unzip -l` before extracting.

### Format and CRS

From `ogrinfo -so -al` (GDAL 3.13.3):

| Property | Value |
|---|---|
| Format | ESRI Shapefile, polygons |
| Features | 38,238 (wildfires and prescribed burns, 1920 onwards) |
| CRS | **EPSG:4283**, GDA94 geographic (degrees); stored longitude first (`Data axis to CRS axis mapping: 2,1`) |
| Extent | 140.979588°E to 153.632608°E, 38.292520°S to 28.173295°S |

Outlines are reprojected to FESM's EPSG:3308 before clipping (2.5).

### Fields

| Field | Type | Use |
|---|---|---|
| `FireType` | Integer | 1 = Wildfire, 2 = Prescribed Burn; filter to 1 |
| `d_FireType` | String | `FireType` as text |
| `FireName` | String | Fire name, for `name` in config |
| `FireNo` | String | Fire or incident number; candidate stable ID |
| `Label` | String | Display label |
| `StartDate` | Date | Fire start; anchors the pre-fire search window (2.1) |
| `EndDate` | Date | Fire end; anchors the post-fire search window (2.1) |
| `AreaHa` | Real | Area in hectares; for choosing fire sizes (1.4) |
| `PerimeterM` | Real | Perimeter in metres |

The metadata also lists coded values for cause, intensity and capture method, but those fields are not in the public shapefile.

### Recent fires

Wildfires (`FireType = 1`) by start year:

| Year | Wildfires | First start | Last start |
|---|---|---|---|
| 2021 | 91 | 2021-01-12 | 2021-12-24 |
| 2022 | 48 | 2022-01-11 | 2022-12-31 |
| 2023 | 514 | 2023-01-07 | 2023-12-29 |
| 2024 | 199 | 2024-01-01 | 2024-12-31 |
| 2025 | 365 | 2025-01-01 | 2025-12-31 |
| 2026 | 216 | 2026-01-01 | 2026-10-27 |

Recent seasons are included, up to 2026-10-27.

### Licence and citation

CC BY 4.0. Required attribution: "© State Government of NSW and NSW Department of Climate Change, Energy, the Environment and Water 2010".

Citation (from SEED): NPWS Fire History - Wildfires and Prescribed Burns, accessed from The Sharing and Enabling Environmental Data Portal [https://datasets.seed.nsw.gov.au/dataset/1d05e145-80cb-4275-af9b-327a1536798d], date accessed 2026-11-09.

### To repeat the checks

```sh
mkdir -p data/npws/2026-11-09 && curl -fL -o data/npws/2026-11-09/fire_npwsfirehistory.zip "https://datasets.seed.nsw.gov.au/dataset/1d05e145-80cb-4275-af9b-327a1536798d/resource/3853d6c0-6517-4cba-8482-68f93a6d43b1/download/fire_npwsfirehistory.zip"
shasum -a 256 data/npws/2026-11-09/fire_npwsfirehistory.zip
unzip -l data/npws/2026-11-09/fire_npwsfirehistory.zip
unzip -n data/npws/2026-11-09/fire_npwsfirehistory.zip -d data/npws/2026-11-09/
ogrinfo -so -al data/npws/2026-11-09/NPWSFireHistory.shp
ogrinfo -ro -q data/npws/2026-11-09/NPWSFireHistory.shp -dialect SQLite -sql "SELECT substr(StartDate, 1, 4) AS year, COUNT(*) AS wildfires, MIN(StartDate) AS first_start, MAX(StartDate) AS last_start FROM NPWSFireHistory WHERE FireType = 1 AND substr(StartDate, 1, 4) >= '2021' GROUP BY year ORDER BY year"
```

GDAL's default SQL dialect rejects comparing a Date field with a text date; the SQLite dialect treats dates as `YYYY-MM-DD` text.

Docs:
- [ogrinfo](https://gdal.org/en/stable/programs/ogrinfo.html)
- [GDAL: SQLite SQL dialect](https://gdal.org/en/stable/user/sql_sqlite_dialect.html)

## 1.4 Chosen fires

Chosen 2026-11-10, after the three passes below. All from the 2023/24 fire year, so all are compared against FESM 2023/24.

| # | Fire | FireNo | Start | End | ha | UTM zones | Why |
|---|---|---|---|---|---|---|---|
| 1 | Willi Willi Rd, Moparrabah | 23101419923 | 2023-10-14 | 2023-11-08 | 29,106 | 56 | Largest; balanced severity and some burnt grassland (class 1); clear scenes 8 days before and 3 days after |
| 2 | Guy Fawkes NP | 23120927869 | 2023-12-09 | 2023-12-24 | 4,086 | 56 | Clear scenes 3 days before and 2 days after; good severity mix; small |
| 3 | Hudson Fire | 23111224029 | 2023-11-12 | 2023-11-25 | 22,819 | 55 | Low-severity end (58% low); western woodland; zone 55 |
| 4 | Dthinna Dthinnawan | 23120927782 | 2023-12-09 | 2023-12-22 | 13,602 | 56 | Severe end (81% high or extreme); clear scenes, but 4–5 weeks either side |
| 5 | Coolagolite | 23100318556 | 2023-10-03 | 2023-11-16 | 6,565 | 55 + 56 | South coast; good severity mix; spans two UTM zones (the tile-edge case) |

Together they cover low to severe fires, UTM zones 55, 56 and both, and five regions (north coast, tablelands, northwest slopes, west, south coast).

Not chosen: **Christies** (weakest in pass 2 and pass 3), **Sandon River** (post-fire scenes about 22% cloud). **Glens Creek Rd** is the alternate, for example in place of Coolagolite to avoid two UTM zones, or Dthinna Dthinnawan for shorter gaps.

### How candidates are found

Three passes, each narrowing the list:
1. **NPWS query:** wildfires in a FESM season, 1,000–50,000 ha, largest first.
2. **FESM check:** for each candidate, FESM inside the outline has burnt pixels and a mix of severity classes.
3. **Imagery check:** clear pre- and post-fire Sentinel-2 scenes exist, and whether the fire crosses the UTM zone 55/56 boundary at 150°E.

### Pass 1: NPWS candidates, 2023/24 season

Wildfires starting in the 2023/24 fire year (matching FESM 2023/24), 1,000–50,000 ha, 25 largest, with centroids to show location:

```sh
ogr2ogr -f CSV /vsistdout/ data/npws/2026-11-09/NPWSFireHistory.shp -dialect SQLite -sql "SELECT FireName, FireNo, StartDate, EndDate, round(AreaHa) AS ha, round(ST_X(ST_Centroid(geometry)), 3) AS lon, round(ST_Y(ST_Centroid(geometry)), 3) AS lat FROM NPWSFireHistory WHERE FireType = 1 AND StartDate BETWEEN '2023-07-01' AND '2024-06-30' AND AreaHa BETWEEN 1000 AND 50000 ORDER BY AreaHa DESC LIMIT 25"
```

- `ogr2ogr -f CSV /vsistdout/` prints the result as CSV to the terminal; nothing is written to disk.
- `FireType = 1` keeps wildfires only; the date range is the 2023/24 fire year (1 July to 30 June).
- Centroids are in EPSG:4283 degrees: fine for location, not for measuring.

Results (run 2026-11-09 on the 2026-11-09 NPWS snapshot): 25 wildfires, 1,975–29,106 ha, mostly northern NSW in spring 2023.

| FireName | FireNo | Start | End | ha | lon | lat |
|---|---|---|---|---|---|---|
| WILLI WILLI RD, MOPARRABAH | 23101419923 | 2023-10-14 | 2023-11-08 | 29106 | 152.545 | -30.980 |
| Hudson Fire | 23111224029 | 2023-11-12 | 2023-11-25 | 22819 | 147.470 | -29.684 |
| Dthinna Dthinnawan | 23120927782 | 2023-12-09 | 2023-12-22 | 13602 | 150.808 | -28.782 |
| GLENS CREEK RD, NYMBOIDA | 23102221129 | 2023-10-22 | 2023-11-13 | 12779 | 152.729 | -29.866 |
| Christies | 23103122467 | 2023-10-31 | 2023-11-15 | 10939 | 151.904 | -28.918 |
| DEVELOPMENTAL RD, KULWIN | 23112525300 | 2023-11-25 | 2023-12-02 | 9963 | 145.465 | -32.401 |
| FROST RD, WOODSIDE | 23102822002 | 2023-10-28 | 2023-11-15 | 8218 | 151.840 | -29.079 |
| Sawyers Creek, Donnybrook State Forest | 23102621791 | 2023-10-26 | 2023-11-16 | 7863 | 151.852 | -28.999 |
| Benders Creek | 23102621754 | 2023-10-26 | 2023-11-16 | 7687 | 151.995 | -29.173 |
| COOLAGOLITE RD, COOLAGOLITE | 23100318556 | 2023-10-03 | 2023-11-16 | 6565 | 149.994 | -36.479 |
| Amaroo Station 6956 Goodooga Road | 23111324070 | 2023-11-13 | 2023-11-20 | 5003 | 147.392 | -29.554 |
| Ogilvie Dr, Tabulam | 23102922143 | 2023-10-29 | 2023-11-15 | 4627 | 152.525 | -28.957 |
| MAGISTRATE TRL, DEEPWATER | 23102621806 | 2023-10-26 | 2023-11-16 | 4381 | 152.014 | -29.388 |
| SANDON RIVER | 24012133320 | 2024-01-21 | 2024-02-13 | 4361 | 153.274 | -29.749 |
| BUKKULLA-BRENDA RD, WEILMORINGLE | 23110723385 | 2023-11-07 | 2023-11-21 | 4113 | 147.109 | -29.111 |
| GUY FAWKES NP | 23120927869 | 2023-12-09 | 2023-12-24 | 4086 | 152.274 | -30.200 |
| Trap Mountain Dumaresq Valley | 23120927885 | 2023-12-09 | 2023-12-28 | 4011 | 151.429 | -29.217 |
| WALLANGRA RD, WALLANGRA | 23101119572 | 2023-10-11 | 2023-10-23 | 3688 | 151.044 | -29.289 |
| JACKYS CREEK RD, RAMORNIE | 23092116492 | 2023-09-21 | 2023-10-03 | 3442 | 152.683 | -29.719 |
| Guy Fawks River National Park | 23100118153 | 2023-10-01 | 2023-10-24 | 3032 | 152.364 | -29.859 |
| MCGUIRES CROSSING RD, BELMORE RIVER | 23101720542 | 2023-10-17 | 2023-11-07 | 2996 | 153.017 | -31.071 |
| BONSHAW RD, BONSHAW | 23102621723 | 2023-10-26 | 2023-11-15 | 2432 | 151.176 | -29.128 |
| HUTLEYS KNOB SHERWOOD 2450 | 23082811535 | 2023-08-28 | 2023-09-22 | 2064 | 153.047 | -30.000 |
| ROCKY RIVER RD, ROCKY RIVER | 23101620230 | 2023-10-16 | 2023-11-16 | 1996 | 152.339 | -29.109 |
| Punchs Creek | 23093017975 | 2023-09-30 | 2023-10-18 | 1975 | 152.486 | -30.061 |

Observations:
- **Tenterfield cluster:** Christies, Frost Rd Woodside, Sawyers Creek and Benders Creek lie within about 25 km of each other and started 26–31 Oct, probably one fire complex. Only one is shortlisted, so the test cases stay independent.
- **Western fires** (Hudson, Kulwin, Amaroo Station, Weilmoringle) are likely grassland, mapped by FESM mostly as class 1 (no severity order). One is kept as a contrast case.
- **Coolagolite's centroid is at 149.994°E**, 0.006° from the UTM zone 55/56 boundary, so it almost certainly spans two zones.
- `FireNo` begins with the start date as YYMMDD (e.g. `23101419923` for 2023-10-14), which looks like an RFS incident number. This is inferred from the pattern, not stated in the metadata. It is a candidate stable ID.
- CSV output shows dates as `2023/10/14`; inside the SQLite dialect they compare as `2023-10-14`.

### Shortlist for pass 2

Chosen 2026-11-09 (8 fires):

| # | Fire | FireNo | ha | Start | End | Why |
|---|---|---|---|---|---|---|
| 1 | Willi Willi Rd, Moparrabah | 23101419923 | 29,106 | 2023-10-14 | 2023-11-08 | Largest; Mid North Coast hinterland forest |
| 2 | Glens Creek Rd, Nymboida | 23102221129 | 12,779 | 2023-10-22 | 2023-11-13 | Clarence Valley forest, separate from the Tenterfield cluster |
| 3 | Christies | 23103122467 | 10,939 | 2023-10-31 | 2023-11-15 | One fire from the Tenterfield cluster (the largest) |
| 4 | Dthinna Dthinnawan | 23120927782 | 13,602 | 2023-12-09 | 2023-12-22 | Northwest slopes woodland; December |
| 5 | Guy Fawkes NP | 23120927869 | 4,086 | 2023-12-09 | 2023-12-24 | National park gorge country; smaller fire |
| 6 | Sandon River | 24012133320 | 4,361 | 2024-01-21 | 2024-02-13 | Coastal, summer; different vegetation |
| 7 | Coolagolite | 23100318556 | 6,565 | 2023-10-03 | 2023-11-16 | South coast for regional spread; UTM-edge test case |
| 8 | Hudson Fire | 23111224029 | 22,819 | 2023-11-12 | 2023-11-25 | Western grassland contrast: dNBR where FESM says "extent only" |

Post-fire scenes must come after `EndDate`; several fires ran for three to six weeks (Coolagolite: 3 Oct to 16 Nov).

### Pass 2: FESM inside each outline

Method: for each shortlisted `FireNo`, all NPWS polygons with that number were reprojected from EPSG:4283 to EPSG:3308 and used to mask FESM 2023/24, keeping pixels whose centre lies inside the outline (no inward buffer yet). Pixels were counted per class, ignoring nodata (255). Run 2026-11-09 with rasterio and fiona, using a local lookup script (not part of the package). For one fire, the same clip with GDAL:

```sh
gdalwarp -cutline data/npws/2026-11-09/NPWSFireHistory.shp -csql "SELECT * FROM NPWSFireHistory WHERE FireNo = '23101419923'" -crop_to_cutline -dstnodata 255 data/fesm/2023-24/FESM2324.tif /tmp/23101419923_fesm.tif
```

`burnt%` is classes 1–5; `sev%` is classes 2–5, the classes with a severity order.

| Fire | Parts | Pixels | Unburnt 0 | Grass 1 | Low 2 | Mod 3 | High 4 | Extreme 5 | burnt% | sev% |
|---|---|---|---|---|---|---|---|---|---|---|
| Willi Willi Rd | 1 | 2,919,859 | 12.4 | 12.6 | 11.8 | 18.7 | 22.2 | 22.4 | 87.6 | 75.0 |
| Glens Creek Rd | 6 | 1,314,851 | 11.0 | 0.0 | 16.7 | 27.4 | 31.1 | 13.7 | 89.0 | 89.0 |
| Christies | 1 | 1,101,845 | 29.0 | 22.8 | 15.5 | 15.7 | 14.0 | 2.9 | 71.0 | 48.2 |
| Dthinna Dthinnawan | 1 | 1,370,634 | 3.9 | 0.0 | 2.5 | 12.5 | 49.7 | 31.3 | 96.1 | 96.1 |
| Guy Fawkes NP | 1 | 410,375 | 3.1 | 0.0 | 7.9 | 31.1 | 34.3 | 23.6 | 96.9 | 96.9 |
| Sandon River | 3 | 445,905 | 6.0 | 0.0 | 29.5 | 21.6 | 23.2 | 19.7 | 94.0 | 94.0 |
| Coolagolite | 6 | 706,476 | 3.4 | 2.7 | 8.6 | 26.7 | 45.4 | 13.2 | 96.6 | 93.8 |
| Hudson Fire | 2 | 2,297,932 | 9.9 | 0.0 | 58.0 | 13.3 | 14.7 | 4.1 | 90.1 | 90.1 |

Findings:
- **All 8 pass:** FESM marks 71–97% of each NPWS outline as burnt, so the two datasets agree on where these fires were.
- **Area check:** Willi Willi has 2,919,859 pixels × (9.98242 m)² ≈ 29,100 ha, against NPWS `AreaHa` 29,106, so the reprojection, clip and pixel size are consistent.
- **Severity range:** Hudson is skewed low (58% low), Dthinna Dthinnawan skewed severe (81% high or extreme), the others balanced.
- **Hudson is not grassland:** it was expected to be mostly class 1, but FESM maps it as 0% grass. The class 1 cases are Willi Willi (12.6%) and Christies (22.8%).
- **Christies is the weakest** (29% unburnt, 48% with a severity class).

All 8 go to pass 3.

### Pass 3: Sentinel-2 imagery

Method: for each fire, a STAC search of all three collections (1.1) over the bounding box of its NPWS polygons, in a 60-day window before `StartDate` and a 60-day window after `EndDate` (the config defaults). Items were grouped by acquisition date, since one date can return several tiles, and each date was ranked by its cloudiest tile's `eo:cloud_cover`, a deliberately pessimistic choice. Run 2026-11-10 with pystac-client, using a local lookup script (not part of the package). For one window, the same search with curl:

```sh
curl -sS "https://explorer.dea.ga.gov.au/stac/search?collections=ga_s2am_ard_3,ga_s2bm_ard_3,ga_s2cm_ard_3&bbox=152.394,-31.073,152.667,-30.87&datetime=2023-08-15/2023-10-13&limit=100"
```

Best dates by cloud (whole-tile `eo:cloud_cover`); the gap is the number of days between the fire and that date:

| Fire | Tiles | Dates pre / post | Best pre | Best post | Verdict |
|---|---|---|---|---|---|
| Willi Willi Rd | 56JML | 24 / 22 | 2023-10-06, 0%, 8 days | 2023-11-11, 0%, 3 days | Excellent |
| Glens Creek Rd | 56JMM, 56JMN | 24 / 22 | 2023-09-16, 0%, 36 days | 2023-11-26, 5%, 13 days | Good |
| Christies | 56JLN, 56JLP, 56JMN, 56JMP | 12 / 10 | 2023-09-21, 0%, 40 days | 2023-12-25, 10%, 40 days (next 21%) | Weak |
| Dthinna Dthinnawan | 56JKP | 22 / 24 | 2023-10-31, 0%, 39 days | 2024-01-22, 0%, 31 days | Clear, long gaps |
| Guy Fawkes NP | 56JMM | 21 / 24 | 2023-12-06, 0%, 3 days | 2023-12-26, 0%, 2 days | Excellent |
| Sandon River | 56JNM, 56JNN | 12 / 12 | 2024-01-20, 0%, 1 day | 2024-02-14, 22%, 1 day | Post-fire cloud |
| Coolagolite | 55HGV, 56HKE | 24 / 22 | 2023-09-16, 0%, 17 days | 2023-11-21, 16%, 5 days | OK; two UTM zones |
| Hudson Fire | 55JEH | 24 / 24 | 2023-10-22, 0%, 21 days | 2023-12-16, 0%, 21 days | Good |

Findings:
- Every fire has a clear pre-fire date; most have a 0% date within days of the fire.
- **Coolagolite spans UTM zones 55 and 56** (tiles 55HGV and 56HKE), confirming the centroid check in pass 1.
- **Gaps matter as well as cloud:** Dthinna Dthinnawan's clear scenes are 4–5 weeks either side of the fire, in the growing season, so regrowth or seasonal change could be counted as severity. Whether 2.1 should rank by cloud alone or by cloud and closeness was open (decided in 2.1, see "Checked in 2.1" below).
- Cloud is whole-tile, not within the fire; the within-fire cloud gate (3.1) gives the real figure. The ranking is by cloud only, so a slightly cloudier date closer to the fire may exist beyond the three shown.
- DEA's STAC only advertises GET for searches; pystac-client warned and fell back to GET. 2.1 should pass `method="GET"`.

These dates are candidates; 2.1 makes the final scene choice.

Docs:
- [ogr2ogr](https://gdal.org/en/stable/programs/ogr2ogr.html)
- [GDAL virtual file systems (`/vsistdout/`)](https://gdal.org/en/stable/user/virtual_file_systems.html#vsistdout-standard-output-streaming)
- [GDAL: SQLite SQL dialect](https://gdal.org/en/stable/user/sql_sqlite_dialect.html)

### Checked in 2.1: chosen scenes

2.1 (#8) picks scenes in two steps. First it keeps only dates whose tiles' footprints (STAC `geometry`) cover at least `stac.min_scene_coverage` (99%) of the fire outline. Of those, it takes the date closest to the fire whose cloudiest tile is at or below `stac.max_scene_cloud` (20%), falling back to the least cloudy date with a warning. Dates are grouped in NSW time (UTC+10), because Sentinel-2 passes over NSW close to midnight UTC. Run 2026-11-10 with `uv run fesmqa run --fire <id>`:

| Fire | Pre-fire | Post-fire | Dates covering the outline (pre / post) |
|---|---|---|---|
| Willi Willi Rd | 2023-10-13, 0.0%, 1-day gap | 2023-11-12, 0.0%, 4-day gap | 12 of 24 / 12 of 22 |
| Guy Fawkes NP | 2023-12-07, 0.1%, 2-day gap | 2023-12-27, 0.0%, 3-day gap | 21 of 21 / 24 of 24 |
| Hudson Fire | 2023-11-11, 0.0%, 1-day gap | 2023-11-26, 18.0%, 1-day gap | 24 of 24 / 24 of 24 |
| Dthinna Dthinnawan | 2023-11-10, 6.8%, 29-day gap | 2023-12-25, 10.9%, 3-day gap | 10 of 22 / 12 of 24 |
| Coolagolite | 2023-09-16, 0.0%, 17-day gap, 2 tiles | 2023-12-30, 14.3%, 44-day gap, 2 tiles | 12 of 24 / 10 of 22 |

Findings:
- **Swath-edge slivers:** a STAC bbox search returns every tile whose footprint touches the box, including tiles at the edge of the satellite's swath that hold only a thin strip of image. `eo:cloud_cover` is measured over that strip only, so a near-empty tile can report almost no cloud. A first version of 2.1 (cloud and closeness only) picked such tiles for Dthinna Dthinnawan (both scenes) and Coolagolite (post-fire): their footprints covered 0% of the fire, and loading them in 2.2 gave fmask 0 (null) for every pixel. The coverage step was added to fix this.
- Fires near a swath edge (Willi Willi Rd, Dthinna Dthinnawan, Coolagolite) lose about half their dates to the coverage step; fires in mid-swath (Guy Fawkes NP, Hudson Fire) lose none.
- Pass 3 ranked by `eo:cloud_cover` alone and so shares the same blind spot; its "best" dates for these three fires should not be relied on.
- Coolagolite's post-fire scene is 44 days after the fire and, once loaded on the fire's grid in 2.2, 51% of its pixels are masked (cloud over the fire, though the whole tile reports 14.3%). It is the weakest case of the five.
- Pixel check in 2.2 for the three changed scenes: no null (fmask 0) pixels; masked 0.3% (Willi Willi Rd post), 0.1% (Dthinna Dthinnawan pre), 51.0% (Coolagolite post).
