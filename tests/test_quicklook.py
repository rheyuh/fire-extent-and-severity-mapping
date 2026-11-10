"""Tests for the quick-look PNG, using tiny hand-made scenes (no network)."""

from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import xarray as xr
from shapely.geometry import box

from fesmqa.bands import fire_grid, mask_scene
from fesmqa.config import Config, load_config
from fesmqa.quicklook import nbr, write_quicklook
from fesmqa.scenes import SceneDate

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"
BBOX = (149.9, -36.6, 150.1, -36.4)


@pytest.fixture
def config() -> Config:
    return load_config(REPO_CONFIG)


def raw_scene(fmask: list[list[int]]) -> xr.Dataset:
    shape = np.array(fmask).shape
    return xr.Dataset(
        {
            "nbart_nir_2": (("y", "x"), np.full(shape, 3000, dtype="int16")),
            "nbart_swir_3": (("y", "x"), np.full(shape, 1000, dtype="int16")),
            "oa_fmask": (("y", "x"), np.array(fmask, dtype="uint8")),
        }
    )


def test_nbr_is_normalised_difference(config: Config) -> None:
    # (3000 - 1000) / (3000 + 1000) = 0.5
    values = nbr(mask_scene(raw_scene([[1, 2]]), config), config).values
    assert values[0, 0] == pytest.approx(0.5)
    assert np.isnan(values[0, 1])  # cloud is masked, so NBR is missing too


def test_write_quicklook_writes_a_png(config: Config, tmp_path: Path) -> None:
    raw = raw_scene([[1, 1, 2], [3, 5, 0]])
    panels = [
        (
            label,
            SceneDate(day=date(2023, 9, 16), cloud=1.0, coverage=100.0, items=()),
            raw,
            mask_scene(raw, config),
        )
        for label in ("Pre-fire", "Post-fire")
    ]
    outline = gpd.GeoDataFrame(geometry=[box(149.95, -36.55, 150.05, -36.45)], crs="EPSG:4326")
    path = tmp_path / "fire" / "quicklook.png"

    written = write_quicklook(panels, outline, fire_grid(BBOX, config), config, "Test", path)

    assert written == path
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
