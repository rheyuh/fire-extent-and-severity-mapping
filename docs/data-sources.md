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

Not yet checked.

## 1.3 Fire outline source

Not yet checked.

## 1.4 Chosen fires

Not yet chosen.
