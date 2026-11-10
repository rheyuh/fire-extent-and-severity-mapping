"""Command-line interface for fesmqa."""

import logging
from pathlib import Path

import click
import geopandas as gpd
import yaml
from odc.geo.geobox import GeoBox

from fesmqa.bands import fire_grid, load_scene, mask_scene, masked_fraction
from fesmqa.config import Config, FireConfig, load_config
from fesmqa.logs import setup_logging
from fesmqa.outlines import load_outline, outline_area, outline_bbox
from fesmqa.quicklook import Panel, write_quicklook
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


fire_option = click.option(
    "--fire", "fire_id", required=True, help="ID of the fire to process, as listed in config."
)


def _fire(config: Config, fire_id: str) -> FireConfig:
    """The fire with this id; an unknown id is a usage error (exit 2) listing the known ones."""
    try:
        return config.fire(fire_id)
    except KeyError as e:
        raise click.BadParameter(str(e.args[0]), param_hint="'--fire'") from e


def _load_scenes(config: Config, fire: FireConfig) -> tuple[gpd.GeoDataFrame, GeoBox, list[Panel]]:
    """Outline, shared grid, and both scenes loaded and masked, logging each scene's masked share.

    Expected failures (missing outline file, no outline, no scenes) become CLI errors (exit 1).
    """
    try:
        outline = load_outline(config, fire)
        pre, post = find_scenes(config, fire, outline_area(outline))
        grid = fire_grid(outline_bbox(outline), config)  # one grid, shared by both scenes
        panels: list[Panel] = []
        for label, scene in (("Pre-fire", pre), ("Post-fire", post)):
            raw = load_scene(scene, grid, config)
            masked = mask_scene(raw, config)
            logger.info(
                "%s %s: %.1f%% of pixels masked",
                label,
                scene.day,
                100 * masked_fraction(masked, config),
            )
            panels.append((label, scene, raw, masked))
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e)) from e
    return outline, grid, panels


@main.command()
@fire_option
@click.pass_obj
def run(config_path: Path, fire_id: str) -> None:
    """Process one fire."""
    config = _load(config_path)
    fire = _fire(config, fire_id)
    _, _, [(_, pre, _, _), (_, post, _, _)] = _load_scenes(config, fire)
    logger.info("Scenes for %s (%s): pre %s, post %s", fire.id, fire.name, pre.day, post.day)


@main.command()
@fire_option
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="PNG to write. Default: <outputs.root>/<fire>/quicklook.png.",
)
@click.pass_obj
def quicklook(config_path: Path, fire_id: str, out: Path | None) -> None:
    """Write a PNG of one fire's scenes: NBR with masked pixels, and fmask classes."""
    config = _load(config_path)
    fire = _fire(config, fire_id)
    outline, grid, panels = _load_scenes(config, fire)
    path = out or Path(config.outputs.root) / fire.id / "quicklook.png"
    write_quicklook(panels, outline, grid, config, f"{fire.name} ({fire.id})", path)
    logger.info("Wrote %s", path)
