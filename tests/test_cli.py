"""Tests for the fesmqa command-line interface."""

import logging
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from fesmqa import cli
from fesmqa.cli import main
from fesmqa.config import Config, FireConfig
from fesmqa.scenes import SceneDate

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"


@pytest.fixture(autouse=True)
def fake_scenes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace scene finding, so CLI tests read no shapefile and make no network calls."""

    def find_scenes(config: Config, fire: FireConfig) -> tuple[SceneDate, SceneDate]:
        pre = SceneDate(day=fire.start_date, cloud=0.0, item_ids=("pre",))
        post = SceneDate(day=fire.end_date, cloud=0.0, item_ids=("post",))
        return pre, post

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


def test_scene_failure_is_reported(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_scenes(config: Config, fire: FireConfig) -> tuple[SceneDate, SceneDate]:
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
