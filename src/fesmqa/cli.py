"""Command-line interface for fesmqa."""

import logging

import click

from fesmqa.logs import setup_logging

logger = logging.getLogger(__name__)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Show debug messages.")
def main(verbose: bool) -> None:
    """Check Sentinel-2 dNBR burn severity against NSW FESM."""
    setup_logging(verbose)
    logger.debug("Debug logging enabled")


@main.command()
@click.option("--fire", required=True, help="ID of the fire to process, as listed in config.")
def run(fire: str) -> None:
    """Process one fire."""
    logger.info("Would run fire: %s", fire)
