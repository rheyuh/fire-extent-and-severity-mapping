"""Find the pre- and post-fire Sentinel-2 scenes for a fire (2.1).

Rule: in each window, keep only dates whose tiles cover the fire outline (at least
stac.min_scene_coverage). Of those, take the date closest to the fire that is clear enough (its
cloudiest tile is at or below stac.max_scene_cloud). If none is, take the least cloudy and warn.

Coverage comes first because a tile at the edge of the satellite's swath can hold only a thin
strip of image. Its cloud cover is measured over that strip, so it can look clear while showing
nothing of the fire.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta, timezone

import pystac
from pystac_client import Client
from shapely import union_all
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from fesmqa.config import Config, FireConfig

logger = logging.getLogger(__name__)

Bbox = tuple[float, float, float, float]

# NSW standard time. Sentinel-2 passes over NSW around 10 am local, which is close to midnight
# UTC, so tiles from one pass can fall on two UTC dates. Local dates keep a pass together and
# match the NPWS fire dates. A fixed offset is enough: 10 or 11 am is never near midnight.
NSW_TIME = timezone(timedelta(hours=10), "AEST")


@dataclass(frozen=True)
class SceneDate:
    """All tiles acquired on one local date, rated by the cloudiest of them."""

    day: date
    cloud: float  # cloud cover (%) of the cloudiest tile
    coverage: float  # share (%) of the fire outline inside the tiles' footprints
    items: tuple[pystac.Item, ...]  # one per tile, e.g. two where a fire spans UTM zones 55 and 56

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.items)

    def describe(self) -> str:
        return (
            f"{self.day} ({self.cloud:.1f}% cloud, {self.coverage:.1f}% coverage, "
            f"tiles: {', '.join(self.item_ids)})"
        )


def search_items(config: Config, bbox: Bbox, start: date, end: date) -> list[pystac.Item]:
    """All Sentinel-2 ARD tiles over bbox acquired from start to end (whole UTC days)."""
    client = Client.open(str(config.stac.endpoint))
    search = client.search(
        collections=config.stac.collections,
        bbox=bbox,
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        method="GET",  # DEA's STAC API only accepts GET searches
    )
    return list(search.items())


def _cloud(item: pystac.Item, cloud_property: str) -> float:
    value = item.properties.get(cloud_property)
    if value is None:
        # Unknown cloud is treated as fully cloudy: never picked as clear, but the run goes on.
        logger.warning("item %s has no %s; treating it as 100%% cloud", item.id, cloud_property)
        return 100.0
    return float(value)


def coverage(items: Sequence[pystac.Item], area: BaseGeometry) -> float:
    """Share (%) of area (lon/lat) inside the union of the items' footprints."""
    footprints = [shape(item.geometry) for item in items if item.geometry is not None]
    if not footprints or area.area == 0:
        return 0.0
    return float(100 * union_all(footprints).intersection(area).area / area.area)


def group_by_date(
    items: list[pystac.Item], cloud_property: str, area: BaseGeometry
) -> list[SceneDate]:
    """Group tiles by local acquisition date, oldest first, with each date's coverage of area."""
    by_day: dict[date, list[pystac.Item]] = defaultdict(list)
    for item in items:
        if item.datetime is None:
            raise ValueError(f"item {item.id} has no datetime")
        by_day[item.datetime.astimezone(NSW_TIME).date()].append(item)
    return [
        SceneDate(
            day=day,
            cloud=max(_cloud(item, cloud_property) for item in tiles),
            coverage=coverage(tiles, area),
            items=tuple(sorted(tiles, key=lambda item: item.id)),
        )
        for day, tiles in sorted(by_day.items())
    ]


def pick_date(
    candidates: list[SceneDate], target: date, max_cloud: float
) -> tuple[SceneDate, bool]:
    """The closest clear-enough date to target, and True; else the least cloudy date, and False.

    Ties on cloud in the fallback go to the date closer to target.
    """
    if not candidates:
        raise ValueError("no scene dates to pick from")

    def distance(scene: SceneDate) -> int:
        return abs((scene.day - target).days)

    clear = [c for c in candidates if c.cloud <= max_cloud]
    if clear:
        return min(clear, key=distance), True
    return min(candidates, key=lambda c: (c.cloud, distance(c))), False


def _pick_in_window(
    config: Config, area: BaseGeometry, label: str, start: date, end: date, target: date
) -> SceneDate:
    # Search one extra UTC day each side, then keep only local dates inside the window.
    west, south, east, north = area.bounds
    bbox = (float(west), float(south), float(east), float(north))
    items = search_items(config, bbox, start - timedelta(days=1), end + timedelta(days=1))
    grouped = group_by_date(items, config.stac.cloud_cover_property, area)
    in_window = [c for c in grouped if start <= c.day <= end]
    if not in_window:
        raise ValueError(f"no {label}-fire scenes from {start} to {end}")
    min_coverage = config.stac.min_scene_coverage
    candidates = [c for c in in_window if c.coverage >= min_coverage]
    if not candidates:
        raise ValueError(
            f"no {label}-fire date from {start} to {end} covers at least {min_coverage}% "
            f"of the fire outline ({len(in_window)} dates checked)"
        )
    logger.debug(
        "%s-fire: %d of %d dates cover the outline", label, len(candidates), len(in_window)
    )
    scene, clear = pick_date(candidates, target, config.stac.max_scene_cloud)
    if not clear:
        logger.warning(
            "no %s-fire date is at or below %s%% cloud; using the least cloudy",
            label,
            config.stac.max_scene_cloud,
        )
    logger.info(
        "%s-fire scene: %s, %d-day gap to the fire, from %d of %d dates",
        label.capitalize(),
        scene.describe(),
        abs((scene.day - target).days),
        len(candidates),
        len(in_window),
    )
    return scene


def find_scenes(
    config: Config, fire: FireConfig, area: BaseGeometry
) -> tuple[SceneDate, SceneDate]:
    """The pre-fire and post-fire scene dates for a fire with this outline (lon/lat)."""
    pre_days, post_days = config.search_windows(fire)
    one_day = timedelta(days=1)
    pre = _pick_in_window(
        config,
        area,
        "pre",
        start=fire.start_date - timedelta(days=pre_days),
        end=fire.start_date - one_day,
        target=fire.start_date,
    )
    post = _pick_in_window(
        config,
        area,
        "post",
        start=fire.end_date + one_day,
        end=fire.end_date + timedelta(days=post_days),
        target=fire.end_date,
    )
    return pre, post
