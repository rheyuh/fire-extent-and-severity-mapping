"""Load a fire's outline from the NPWS Fire History (1.3)."""

from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from fesmqa.config import Config, FireConfig


def load_outline(config: Config, fire: FireConfig) -> gpd.GeoDataFrame:
    """Return the outline polygons whose FireNo matches the fire. Raises ValueError if none do."""
    if not Path(config.outlines.path).exists():
        raise FileNotFoundError(f"outline file not found: {config.outlines.path}")
    field = config.outlines.fire_no_field
    # Filter while reading so only this fire's rows are loaded, not all 38k polygons.
    # Safe to build as text: npws_fire_no is validated as digits only.
    outline = gpd.read_file(config.outlines.path, where=f"{field} = '{fire.npws_fire_no}'")
    if outline.empty:
        raise ValueError(
            f"fire {fire.id}: no outline with {field} = {fire.npws_fire_no} "
            f"in {config.outlines.path}"
        )
    return outline


def outline_area(outline: gpd.GeoDataFrame) -> BaseGeometry:
    """All of the outline's polygons as one shape in lon/lat (EPSG:4326)."""
    return outline.to_crs("EPSG:4326").union_all()


def outline_bbox(outline: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    """The outline's bounding box as (west, south, east, north) in lon/lat, for a STAC search."""
    west, south, east, north = outline.to_crs("EPSG:4326").total_bounds
    return float(west), float(south), float(east), float(north)
