"""Find the pre- and post-fire Sentinel-2 scenes for a fire (2.1).

Rule: in each window, take the date closest to the fire that is clear enough (its cloudiest
tile is at or below stac.max_scene_cloud). If no date is, take the least cloudy and warn.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta, timezone

import pystac
from pystac_client import Client

from fesmqa.config import Config, FireConfig
from fesmqa.outlines import load_outline, outline_bbox

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
    item_ids: tuple[str, ...]  # one per tile, e.g. two where a fire spans UTM zones 55 and 56

    def describe(self) -> str:
        return f"{self.day} ({self.cloud:.1f}% cloud, tiles: {', '.join(self.item_ids)})"


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


def group_by_date(items: list[pystac.Item], cloud_property: str) -> list[SceneDate]:
    """Group tiles by local acquisition date, oldest first."""
    by_day: dict[date, list[pystac.Item]] = defaultdict(list)
    for item in items:
        if item.datetime is None:
            raise ValueError(f"item {item.id} has no datetime")
        by_day[item.datetime.astimezone(NSW_TIME).date()].append(item)
    return [
        SceneDate(
            day=day,
            cloud=max(_cloud(item, cloud_property) for item in tiles),
            item_ids=tuple(sorted(item.id for item in tiles)),
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
    config: Config, bbox: Bbox, label: str, start: date, end: date, target: date
) -> SceneDate:
    # Search one extra UTC day each side, then keep only local dates inside the window.
    items = search_items(config, bbox, start - timedelta(days=1), end + timedelta(days=1))
    grouped = group_by_date(items, config.stac.cloud_cover_property)
    candidates = [c for c in grouped if start <= c.day <= end]
    if not candidates:
        raise ValueError(f"no {label}-fire scenes from {start} to {end}")
    scene, clear = pick_date(candidates, target, config.stac.max_scene_cloud)
    if not clear:
        logger.warning(
            "no %s-fire date is at or below %s%% cloud; using the least cloudy",
            label,
            config.stac.max_scene_cloud,
        )
    logger.info(
        "%s-fire scene: %s, %d-day gap to the fire, from %d dates",
        label.capitalize(),
        scene.describe(),
        abs((scene.day - target).days),
        len(candidates),
    )
    return scene


def find_scenes(config: Config, fire: FireConfig) -> tuple[SceneDate, SceneDate]:
    """The pre-fire and post-fire scene dates for a fire."""
    pre_days, post_days = config.search_windows(fire)
    bbox = outline_bbox(load_outline(config, fire))
    one_day = timedelta(days=1)
    pre = _pick_in_window(
        config,
        bbox,
        "pre",
        start=fire.start_date - timedelta(days=pre_days),
        end=fire.start_date - one_day,
        target=fire.start_date,
    )
    post = _pick_in_window(
        config,
        bbox,
        "post",
        start=fire.end_date + one_day,
        end=fire.end_date + timedelta(days=post_days),
        target=fire.end_date,
    )
    return pre, post
