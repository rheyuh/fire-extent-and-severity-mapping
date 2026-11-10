"""Command-line interface for fesmqa."""

import logging
from pathlib import Path

import click
import yaml

from fesmqa.bands import fire_grid, load_scene, mask_scene, masked_fraction
from fesmqa.config import Config, load_config
from fesmqa.logs import setup_logging
from fesmqa.outlines import load_outline, outline_area, outline_bbox
from fesmqa.scenes import find_scenes

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
    try:
        outline = load_outline(config, fire)
        pre, post = find_scenes(config, fire, outline_area(outline))
        grid = fire_grid(outline_bbox(outline), config)  # one grid, shared by both scenes
        for label, scene in (("Pre-fire", pre), ("Post-fire", post)):
            masked = mask_scene(load_scene(scene, grid, config), config)
            logger.info(
                "%s %s: %.1f%% of pixels masked",
                label,
                scene.day,
                100 * masked_fraction(masked, config),
            )
    except (FileNotFoundError, ValueError) as e:  # missing outline file, no outline, no scenes
        raise click.ClickException(str(e)) from e
    logger.info("Scenes for %s (%s): pre %s, post %s", fire.id, fire.name, pre.day, post.day)
