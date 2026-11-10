"""Load a scene's bands onto the fire's grid and mask unusable pixels (2.2)."""

import odc.stac
import xarray as xr
from odc.geo.geobox import GeoBox
from odc.geo.geom import box

from fesmqa.config import Config
from fesmqa.scenes import Bbox, SceneDate


def fire_grid(bbox: Bbox, config: Config) -> GeoBox:
    """One grid in config.grid.crs covering the fire's lon/lat box, shared by both scenes.

    Pixel edges fall on multiples of the resolution, so the grid depends only on the CRS,
    the resolution and the box: reruns give the same pixels.
    """
    if config.grid.crs is None:
        raise ValueError("grid.crs must be set to build the fire's grid")
    area = box(*bbox, crs="EPSG:4326").to_crs(config.grid.crs)
    return GeoBox.from_geopolygon(area, resolution=config.grid.resolution, crs=config.grid.crs)


def load_scene(scene: SceneDate, grid: GeoBox, config: Config) -> xr.Dataset:
    """Read NIR, SWIR2 and fmask for one scene date onto the grid, with tiles mosaicked.

    Nodata comes from each band's STAC metadata (-999 reflectance, 0 fmask), so pixels outside
    one tile are filled from the other where a fire spans two UTM zones.
    """
    # DEA's band files are on a public S3 bucket: read them unsigned, without AWS credentials.
    odc.stac.configure_rio(cloud_defaults=True, aws={"aws_unsigned": True})
    bands = config.bands
    ds = odc.stac.load(
        scene.items,
        bands=[bands.nir, bands.swir2, bands.fmask],
        geobox=grid,
        groupby="solar_day",  # all tiles of the date become one image
        # fmask is a class map: any blending would invent classes, so it is always nearest.
        resampling={"*": config.grid.resampling, bands.fmask: "nearest"},
    )
    if ds.sizes["time"] != 1:
        raise ValueError(f"expected one date for {scene.day}, got {ds.sizes['time']}")
    return ds.isel(time=0)


def mask_scene(ds: xr.Dataset, config: Config) -> xr.Dataset:
    """NIR and SWIR2 as float32 with NaN wherever the band is nodata or fmask is not kept.

    fmask is passed through unchanged, for the QA gates in 3.1.
    """
    bands = config.bands
    keep = ds[bands.fmask].isin(bands.fmask_keep)
    out = xr.Dataset(coords=ds.coords)
    for name in (bands.nir, bands.swir2):
        valid = keep & (ds[name] != bands.nodata)
        out[name] = ds[name].where(valid).astype("float32")
        out[name].attrs.pop("nodata", None)  # NaN marks missing now, not -999
    out[bands.fmask] = ds[bands.fmask]
    return out


def masked_fraction(ds: xr.Dataset, config: Config) -> float:
    """Share of pixels (0 to 1) missing in NIR or SWIR2 after masking."""
    missing = ds[config.bands.nir].isnull() | ds[config.bands.swir2].isnull()
    return float(missing.mean())
