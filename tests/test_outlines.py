"""Tests for loading fire outlines, using a small shapefile written per test."""

from pathlib import Path
from typing import Any

import geopandas as gpd
import pytest
import yaml
from shapely.geometry import box

from fesmqa.config import Config, FireConfig
from fesmqa.outlines import load_outline, outline_area, outline_bbox

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """The committed config, pointed at a shapefile with fire 111 (two parts) and fire 222."""
    path = tmp_path / "outlines.shp"
    gpd.GeoDataFrame(
        {"FireNo": ["111", "111", "222"]},
        geometry=[
            box(150.0, -30.0, 150.5, -29.5),
            box(150.6, -30.2, 151.0, -29.8),
            box(1, 1, 2, 2),
        ],
        crs="EPSG:4283",
    ).to_file(path)
    data: dict[str, Any] = yaml.safe_load(REPO_CONFIG.read_text())
    data["outlines"] = {"path": str(path), "fire_no_field": "FireNo"}
    return Config.model_validate(data)


def make_fire(npws_fire_no: str) -> FireConfig:
    return FireConfig.model_validate(
        {
            "id": "test-fire",
            "name": "Test Fire",
            "npws_fire_no": npws_fire_no,
            "start_date": "2025-12-01",
            "end_date": "2025-12-20",
        }
    )


def test_load_outline_keeps_only_matching_rows(config: Config) -> None:
    outline = load_outline(config, make_fire("111"))
    assert len(outline) == 2
    assert set(outline["FireNo"]) == {"111"}


def test_load_outline_no_match_raises(config: Config) -> None:
    with pytest.raises(ValueError, match="no outline with FireNo = 999"):
        load_outline(config, make_fire("999"))


def test_load_outline_missing_file_raises(config: Config, tmp_path: Path) -> None:
    moved = config.model_copy(
        update={"outlines": config.outlines.model_copy(update={"path": str(tmp_path / "no.shp")})}
    )
    with pytest.raises(FileNotFoundError, match="outline file not found"):
        load_outline(moved, make_fire("111"))


def test_outline_area_joins_all_parts_in_lon_lat(config: Config) -> None:
    area = outline_area(load_outline(config, make_fire("111")))
    # Two boxes, 0.5 x 0.5 and 0.4 x 0.4 degrees.
    assert area.area == pytest.approx(0.25 + 0.16, abs=1e-4)
    assert area.bounds == pytest.approx((150.0, -30.2, 151.0, -29.5), abs=1e-4)


def test_outline_bbox_covers_all_parts_in_lon_lat(config: Config) -> None:
    bbox = outline_bbox(load_outline(config, make_fire("111")))
    # GDA94 and WGS84 differ by about a metre here, far below 1e-4 degrees (about 10 m).
    assert bbox == pytest.approx((150.0, -30.2, 151.0, -29.5), abs=1e-4)
