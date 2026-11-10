"""Tests for the fesmqa command-line interface."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import yaml
from click.testing import CliRunner

from fesmqa import cli
from fesmqa.cli import main
from fesmqa.config import Config, FireConfig
from fesmqa.scenes import SceneDate

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"

# A loaded scene with one clear pixel (fmask 1) and one cloudy pixel (fmask 2): 50% masked.
HALF_CLOUDY = xr.Dataset(
    {
        "nbart_nir_2": (("y", "x"), np.array([[900, 900]], dtype="int16")),
        "nbart_swir_3": (("y", "x"), np.array([[500, 500]], dtype="int16")),
        "oa_fmask": (("y", "x"), np.array([[1, 2]], dtype="uint8")),
    }
)


@pytest.fixture(autouse=True)
def fake_scenes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace outline and scene finding: CLI tests read no shapefile and use no network."""

    def find_scenes(config: Config, fire: FireConfig, area: Any) -> tuple[SceneDate, SceneDate]:
        pre = SceneDate(day=fire.start_date, cloud=0.0, coverage=100.0, items=())
        post = SceneDate(day=fire.end_date, cloud=0.0, coverage=100.0, items=())
        return pre, post

    monkeypatch.setattr(cli, "load_outline", lambda config, fire: None)
    monkeypatch.setattr(cli, "outline_area", lambda outline: None)
    monkeypatch.setattr(cli, "outline_bbox", lambda outline: (149.9, -36.6, 150.1, -36.4))
    monkeypatch.setattr(cli, "load_scene", lambda scene, grid, config: HALF_CLOUDY)
    monkeypatch.setattr(cli, "find_scenes", find_scenes)


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """A copy of the committed config with one test fire added."""
    data: dict[str, Any] = yaml.safe_load(REPO_CONFIG.read_text())
    data["fires"] = [
        {
            "id": "test-fire",
            "name": "Test Fire",
            "npws_fire_no": "25120100001",
            "start_date": "2025-12-01",
            "end_date": "2025-12-20",
        }
    ]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_help_lists_run() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output


def test_run_help_works_without_config(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, ["--config", str(tmp_path / "missing.yaml"), "run", "--help"])
    assert result.exit_code == 0
    assert "--fire" in result.output


def test_run_requires_fire(config_file: Path) -> None:
    result = CliRunner().invoke(main, ["--config", str(config_file), "run"])
    assert result.exit_code == 2
    assert "Missing option '--fire'" in result.output


def test_run_known_fire(config_file: Path) -> None:
    result = CliRunner().invoke(main, ["--config", str(config_file), "run", "--fire", "test-fire"])
    assert result.exit_code == 0


def test_run_unknown_fire_is_usage_error(config_file: Path) -> None:
    result = CliRunner().invoke(main, ["--config", str(config_file), "run", "--fire", "nope"])
    assert result.exit_code == 2
    assert "fires in config: test-fire" in result.output


def test_run_logs_masked_share_per_scene(
    config_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="fesmqa"):
        result = CliRunner().invoke(
            main, ["--config", str(config_file), "run", "--fire", "test-fire"]
        )
    assert result.exit_code == 0
    assert "Pre-fire 2025-12-01: 50.0% of pixels masked" in caplog.text
    assert "Post-fire 2025-12-20: 50.0% of pixels masked" in caplog.text


def test_scene_failure_is_reported(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_scenes(config: Config, fire: FireConfig, area: Any) -> tuple[SceneDate, SceneDate]:
        raise ValueError("no pre-fire scenes from 2025-10-02 to 2025-11-30")

    monkeypatch.setattr(cli, "find_scenes", no_scenes)
    result = CliRunner().invoke(main, ["--config", str(config_file), "run", "--fire", "test-fire"])
    assert result.exit_code == 1
    assert "no pre-fire scenes" in result.output


def test_invalid_config_is_reported(config_file: Path) -> None:
    data = yaml.safe_load(config_file.read_text())
    data["severity"]["thresholds"] = [0.44, 0.10]
    config_file.write_text(yaml.safe_dump(data))
    result = CliRunner().invoke(main, ["--config", str(config_file), "run", "--fire", "test-fire"])
    assert result.exit_code == 1
    assert "invalid config" in result.output


def test_missing_config_is_reported(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    result = CliRunner().invoke(main, ["--config", str(missing), "run", "--fire", "test-fire"])
    assert result.exit_code == 1
    assert "config file not found" in result.output


def test_verbose_sets_debug_level(config_file: Path) -> None:
    result = CliRunner().invoke(
        main, ["-v", "--config", str(config_file), "run", "--fire", "test-fire"]
    )
    assert result.exit_code == 0
    assert logging.getLogger("fesmqa").level == logging.DEBUG


def test_default_level_is_info(config_file: Path) -> None:
    result = CliRunner().invoke(main, ["--config", str(config_file), "run", "--fire", "test-fire"])
    assert result.exit_code == 0
    assert logging.getLogger("fesmqa").level == logging.INFO
