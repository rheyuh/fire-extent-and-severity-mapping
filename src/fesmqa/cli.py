"""Command-line interface for fesmqa."""

import click


@click.group()
def main() -> None:
    """Check Sentinel-2 dNBR burn severity against NSW FESM."""


@main.command()
@click.option("--fire", required=True, help="ID of the fire to process, as listed in config.")
def run(fire: str) -> None:
    """Process one fire."""
    click.echo(f"Would run fire: {fire}")
