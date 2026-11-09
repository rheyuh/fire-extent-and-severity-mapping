"""Tests for the fesmqa command-line interface."""

import logging

from click.testing import CliRunner

from fesmqa.cli import main


def test_help_lists_run() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output


def test_run_requires_fire() -> None:
    result = CliRunner().invoke(main, ["run"])
    assert result.exit_code == 2
    assert "Missing option '--fire'" in result.output


def test_verbose_sets_debug_level() -> None:
    result = CliRunner().invoke(main, ["-v", "run", "--fire", "x"])
    assert result.exit_code == 0
    assert logging.getLogger("fesmqa").level == logging.DEBUG


def test_default_level_is_info() -> None:
    result = CliRunner().invoke(main, ["run", "--fire", "x"])
    assert result.exit_code == 0
    assert logging.getLogger("fesmqa").level == logging.INFO
