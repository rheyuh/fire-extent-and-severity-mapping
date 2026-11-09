"""Command-line interface for fesmqa."""

import logging
from pathlib import Path

import click
import yaml

from fesmqa.config import Config, load_config
from fesmqa.logs import setup_logging

logger = logging.getLogger(__name__)


def _load(path: Path) -> Config:
    """Load config for a command, turning failures into readable CLI errors (exit 1)."""
    try:
        return load_config(path)
    except FileNotFoundError as e:
        raise click.ClickException(f"config file not found: {path}") from e
    except (ValueError, yaml.YAMLError) as e:  # pydantic's ValidationError is a ValueError
        raise click.ClickException(f"invalid config {path}:\n{e}") from e


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Show debug messages.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default="config.yaml",
    show_default=True,
    envvar="FESMQA_CONFIG",
    help="Config file to use. Can also be set with FESMQA_CONFIG.",
)
@click.pass_context
def main(ctx: click.Context, verbose: bool, config_path: Path) -> None:
    """Check Sentinel-2 dNBR burn severity against NSW FESM."""
    setup_logging(verbose)
    logger.debug("Debug logging enabled")
    # Only the path is passed on: each command loads the config itself, so --help never needs it.
    ctx.obj = config_path


@main.command()
@click.option(
    "--fire", "fire_id", required=True, help="ID of the fire to process, as listed in config."
)
@click.pass_obj
def run(config_path: Path, fire_id: str) -> None:
    """Process one fire."""
    config = _load(config_path)
    try:
        fire = config.fire(fire_id)
    except KeyError as e:
        raise click.BadParameter(str(e.args[0]), param_hint="'--fire'") from e
    pre, post = config.search_windows(fire)
    logger.info("Would run fire: %s (%s), search windows %d/%d days", fire.id, fire.name, pre, post)
