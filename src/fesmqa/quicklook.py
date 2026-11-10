"""A quick-look PNG of a fire's two scenes, to check by eye what was loaded and masked (2.2).

Top row: NBR of each scene after masking; masked pixels show in magenta, so cloud blanked out
is easy to see. Bottom row: each scene's fmask classes. The fire outline is drawn on all four.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import xarray as xr
from matplotlib import colormaps
from matplotlib.colors import Colormap, ListedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from odc.geo.geobox import GeoBox

from fesmqa.config import Config
from fesmqa.scenes import SceneDate

# fmask classes (1.1), in code order 0 to 5.
FMASK_CLASSES = [
    ("null", "#000000"),
    ("clear", "#cfcfcf"),
    ("cloud", "#3b7ddd"),
    ("shadow", "#6a3d9a"),
    ("snow", "#a6e3ff"),
    ("water", "#08306b"),
]
MASKED_COLOUR = "magenta"

# One scene in the figure: (label, scene date, bands as loaded, bands after masking).
Panel = tuple[str, SceneDate, xr.Dataset, xr.Dataset]


def nbr(ds: xr.Dataset, config: Config) -> xr.DataArray:
    """Normalised Burn Ratio, (NIR - SWIR2) / (NIR + SWIR2). For display here; dNBR is 2.3."""
    nir, swir2 = ds[config.bands.nir], ds[config.bands.swir2]
    return (nir - swir2) / (nir + swir2)


def _nbr_cmap() -> Colormap:
    """Red (burnt, low NBR) to green (vegetated, high NBR), with masked pixels in magenta."""
    return colormaps["RdYlGn"].with_extremes(bad=MASKED_COLOUR)


def write_quicklook(
    panels: list[Panel],
    outline: gpd.GeoDataFrame,
    grid: GeoBox,
    config: Config,
    title: str,
    path: Path,
) -> Path:
    """Write the PNG to path (creating its folder) and return the path."""
    # Figure, not pyplot: no GUI backend or global state, so it also works headless (CI, Slurm).
    fig = Figure(figsize=(5 * len(panels), 9.5), layout="constrained")
    axes = fig.subplots(2, len(panels), squeeze=False)
    bounds = grid.boundingbox
    extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
    outline_xy = outline.to_crs(str(grid.crs))
    fmask_cmap = ListedColormap([colour for _, colour in FMASK_CLASSES])

    for col, (label, scene, raw, masked) in enumerate(panels):
        top, bottom = axes[0][col], axes[1][col]
        values = nbr(masked, config).values
        image = top.imshow(
            np.ma.masked_invalid(values),
            cmap=_nbr_cmap(),
            vmin=-0.5,
            vmax=0.8,
            extent=extent,
            interpolation="nearest",
        )
        top.set_title(f"{label} {scene.day}\nNBR, {100 * np.isnan(values).mean():.1f}% masked")
        fig.colorbar(image, ax=top, shrink=0.7, label="NBR")

        bottom.imshow(
            raw[config.bands.fmask].values,
            cmap=fmask_cmap,
            vmin=-0.5,
            vmax=len(FMASK_CLASSES) - 0.5,
            extent=extent,
            interpolation="nearest",
        )
        bottom.set_title(f"{label} {scene.day}\nfmask, {scene.cloud:.1f}% whole-tile cloud")

        for ax in (top, bottom):
            outline_xy.boundary.plot(ax=ax, color="black", linewidth=0.8)
            ax.set_axis_off()

    handles = [Patch(color=c, label=n) for n, c in FMASK_CLASSES]
    handles.append(Patch(color=MASKED_COLOUR, label="masked (NBR panels)"))
    fig.legend(handles=handles, loc="outside lower center", ncols=len(handles))
    fig.suptitle(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    return path
