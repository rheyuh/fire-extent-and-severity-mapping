"""Tests for config loading and validation.

Each failure test starts from the real config.yaml and breaks exactly one thing.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from fesmqa.config import Config, load_config

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"


@pytest.fixture
def data() -> dict[str, Any]:
    """The committed config.yaml as a plain dict, ready to be broken."""
    loaded: dict[str, Any] = yaml.safe_load(REPO_CONFIG.read_text())
    return loaded


def make_fire(fire_id: str = "test-fire", **overrides: Any) -> dict[str, Any]:
    fire: dict[str, Any] = {
        "id": fire_id,
        "name": "Test Fire",
        "npws_fire_no": "25120100001",
        "start_date": "2025-12-01",
        "end_date": "2025-12-20",
    }
    fire.update(overrides)
    return fire


def test_repo_config_loads() -> None:
    config = load_config(REPO_CONFIG)
    assert config.bands.swir2 == "nbart_swir_3"
    assert config.bands.nir == "nbart_nir_2"


def test_unknown_key_rejected(data: dict[str, Any]) -> None:
    data["dates"]["pre_fire_dayz"] = 30
    with pytest.raises(ValidationError, match="pre_fire_dayz"):
        Config.model_validate(data)


def test_thresholds_must_increase(data: dict[str, Any]) -> None:
    data["severity"]["thresholds"] = [0.10, 0.44, 0.27]
    with pytest.raises(ValidationError, match="strictly increase"):
        Config.model_validate(data)


def test_fmask_value_out_of_range(data: dict[str, Any]) -> None:
    data["bands"]["fmask_keep"] = [7]
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_max_scene_cloud_out_of_range(data: dict[str, Any]) -> None:
    data["stac"]["max_scene_cloud"] = 150
    with pytest.raises(ValidationError, match="max_scene_cloud"):
        Config.model_validate(data)


def test_unknown_resampling_rejected(data: dict[str, Any]) -> None:
    data["grid"]["resampling"] = "bilinaer"
    with pytest.raises(ValidationError, match="resampling"):
        Config.model_validate(data)


def test_fire_end_before_start(data: dict[str, Any]) -> None:
    data["fires"] = [make_fire(start_date="2025-12-20", end_date="2025-12-01")]
    with pytest.raises(ValidationError, match="end_date is before start_date"):
        Config.model_validate(data)


def test_duplicate_fire_ids(data: dict[str, Any]) -> None:
    data["fires"] = [make_fire("same-id"), make_fire("same-id")]
    with pytest.raises(ValidationError, match="duplicate fire ids"):
        Config.model_validate(data)


def test_bad_fire_id(data: dict[str, Any]) -> None:
    data["fires"] = [make_fire("Fire 1")]
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_npws_fire_no_must_be_digits(data: dict[str, Any]) -> None:
    data["fires"] = [make_fire(npws_fire_no="WILLI-WILLI")]
    with pytest.raises(ValidationError, match="npws_fire_no"):
        Config.model_validate(data)


def test_search_windows_override(data: dict[str, Any]) -> None:
    data["dates"] = {"pre_fire_days": 60, "post_fire_days": 60}
    data["fires"] = [make_fire("default-windows"), make_fire("long-post", post_fire_days=90)]
    config = Config.model_validate(data)
    assert config.search_windows(config.fire("default-windows")) == (60, 60)
    assert config.search_windows(config.fire("long-post")) == (60, 90)


def test_unknown_fire_lists_known(data: dict[str, Any]) -> None:
    data["fires"] = [make_fire("known-fire")]
    config = Config.model_validate(data)
    with pytest.raises(KeyError, match="known-fire"):
        config.fire("nope")
