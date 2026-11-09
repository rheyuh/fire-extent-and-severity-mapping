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

Not yet checked.

## 1.4 Chosen fires

Not yet chosen.
