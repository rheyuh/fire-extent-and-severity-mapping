"""Tests for loading and masking bands, using small hand-made grids (no network)."""

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import odc.stac
import pytest
import xarray as xr
from odc.geo.geom import box

from fesmqa.bands import fire_grid, load_scene, mask_scene, masked_fraction
from fesmqa.config import Config, load_config
from fesmqa.scenes import SceneDate

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"
NIR, SWIR2, FMASK = "nbart_nir_2", "nbart_swir_3", "oa_fmask"
BBOX = (149.9, -36.6, 150.1, -36.4)  # straddles 150°E, the UTM 55/56 boundary, like Coolagolite


@pytest.fixture
def config() -> Config:
    return load_config(REPO_CONFIG)


def raw_scene(nir: list[int], swir2: list[int], fmask: list[int]) -> xr.Dataset:
    """A one-row scene as odc.stac.load returns it: int16 reflectance, uint8 fmask."""

    def band(values: list[int], dtype: str) -> tuple[tuple[str, str], Any]:
        return ("y", "x"), np.array([values], dtype=dtype)

    return xr.Dataset(
        {NIR: band(nir, "int16"), SWIR2: band(swir2, "int16"), FMASK: band(fmask, "uint8")}
    )


# mask_scene and masked_fraction


def test_only_clear_pixels_are_kept(config: Config) -> None:
    # fmask 0 null, 1 clear, 2 cloud, 3 shadow, 4 snow, 5 water
    ds = raw_scene([100] * 6, [50] * 6, [0, 1, 2, 3, 4, 5])
    masked = mask_scene(ds, config)
    assert np.isnan(masked[NIR].values[0]).tolist() == [True, False, True, True, True, True]
    assert np.isnan(masked[SWIR2].values[0]).tolist() == [True, False, True, True, True, True]


def test_nodata_becomes_nan_even_when_clear(config: Config) -> None:
    ds = raw_scene([-999, 100], [50, -999], [1, 1])
    masked = mask_scene(ds, config)
    assert np.isnan(masked[NIR].values[0]).tolist() == [True, False]
    assert np.isnan(masked[SWIR2].values[0]).tolist() == [False, True]


def test_bands_become_float32_and_fmask_is_unchanged(config: Config) -> None:
    ds = raw_scene([100, 200], [50, 60], [1, 2])
    masked = mask_scene(ds, config)
    assert masked[NIR].dtype == np.float32
    assert masked[NIR].values[0, 0] == 100.0
    assert masked[FMASK].values[0].tolist() == [1, 2]


def test_masked_fraction_counts_pixels_missing_in_either_band(config: Config) -> None:
    ds = raw_scene([100, -999, 100, 100], [50, 50, -999, 50], [1, 1, 1, 2])
    assert masked_fraction(mask_scene(ds, config), config) == 0.75


# fire_grid


def test_fire_grid_uses_config_crs_and_resolution(config: Config) -> None:
    grid = fire_grid(BBOX, config)
    assert grid.crs is not None
    assert grid.crs.epsg == 3308
    assert (grid.resolution.x, grid.resolution.y) == (20, -20)


def test_fire_grid_edges_fall_on_multiples_of_the_resolution(config: Config) -> None:
    grid = fire_grid(BBOX, config)
    assert grid.affine.c % 20 == 0
    assert grid.affine.f % 20 == 0


def test_fire_grid_covers_the_box(config: Config) -> None:
    grid = fire_grid(BBOX, config)
    assert grid.extent.contains(box(*BBOX, crs="EPSG:4326").to_crs("EPSG:3308"))


# load_scene, with odc.stac.load replaced by a fake that records its arguments


def test_load_scene_uses_nearest_for_fmask(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_load(items: Any, **kwargs: Any) -> xr.Dataset:
        calls.append(kwargs)
        return raw_scene([100], [50], [1]).expand_dims(time=1)

    monkeypatch.setattr(odc.stac, "load", fake_load)
    grid = fire_grid(BBOX, config)
    ds = load_scene(
        SceneDate(day=date(2023, 9, 16), cloud=0.0, coverage=100.0, items=()), grid, config
    )

    [kwargs] = calls
    assert kwargs["resampling"] == {"*": "bilinear", FMASK: "nearest"}
    assert kwargs["bands"] == [NIR, SWIR2, FMASK]
    assert kwargs["geobox"] is grid
    assert "time" not in ds.dims
