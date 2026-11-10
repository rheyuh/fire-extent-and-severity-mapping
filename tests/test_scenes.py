"""Tests for scene selection. Items are built by hand, so no network is needed."""

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pystac
import pytest
from shapely.geometry import box, mapping

from fesmqa import scenes
from fesmqa.config import Config, FireConfig, load_config
from fesmqa.scenes import SceneDate, group_by_date, pick_date

REPO_CONFIG = Path(__file__).parent.parent / "config.yaml"
CLOUD = "eo:cloud_cover"
AREA = box(150.0, -30.0, 151.0, -29.0)  # the fire outline, in lon/lat
FULL = box(149.0, -31.0, 152.0, -28.0)  # a tile footprint covering all of AREA
SLIVER = box(149.0, -29.2, 152.0, -28.0)  # a swath-edge tile: only AREA's northern strip
WHEN = datetime(2023, 10, 10, 0, 0, tzinfo=UTC)


def make_item(
    item_id: str, when: datetime, cloud: float | None, footprint: Any = FULL
) -> pystac.Item:
    properties = {} if cloud is None else {CLOUD: cloud}
    geometry = None if footprint is None else mapping(footprint)
    return pystac.Item(
        id=item_id, geometry=geometry, bbox=None, datetime=when, properties=properties
    )


def scene(day: str, cloud: float) -> SceneDate:
    # pick_date only looks at day and cloud, so no items are needed.
    return SceneDate(day=date.fromisoformat(day), cloud=cloud, coverage=100.0, items=())


# group_by_date


def test_one_pass_across_utc_midnight_is_one_date() -> None:
    # 23:58 UTC on the 13th and 00:01 UTC on the 14th are both about 10 am on the 14th in NSW.
    items = [
        make_item("zone-56", datetime(2023, 10, 13, 23, 58, tzinfo=UTC), 5.0),
        make_item("zone-55", datetime(2023, 10, 14, 0, 1, tzinfo=UTC), 30.0),
    ]
    [scene_date] = group_by_date(items, CLOUD, AREA)
    assert scene_date.day == date(2023, 10, 14)
    assert scene_date.cloud == 30.0
    assert scene_date.item_ids == ("zone-55", "zone-56")


def test_dates_are_sorted_oldest_first() -> None:
    items = [
        make_item("b", datetime(2023, 10, 20, 0, 0, tzinfo=UTC), 1.0),
        make_item("a", datetime(2023, 10, 10, 0, 0, tzinfo=UTC), 1.0),
    ]
    assert [s.day for s in group_by_date(items, CLOUD, AREA)] == [
        date(2023, 10, 10),
        date(2023, 10, 20),
    ]


def test_missing_cloud_counts_as_fully_cloudy() -> None:
    items = [make_item("a", datetime(2023, 10, 10, 0, 0, tzinfo=UTC), None)]
    assert group_by_date(items, CLOUD, AREA)[0].cloud == 100.0


# coverage


def test_coverage_combines_tiles_from_two_zones() -> None:
    west = make_item("zone-55", WHEN, 0.0, box(149.0, -31.0, 150.5, -28.0))
    east = make_item("zone-56", WHEN, 0.0, box(150.5, -31.0, 152.0, -28.0))
    assert scenes.coverage([west], AREA) == pytest.approx(50.0)
    assert scenes.coverage([west, east], AREA) == pytest.approx(100.0)


def test_sliver_covers_only_its_strip() -> None:
    assert scenes.coverage([make_item("edge", WHEN, 0.0, SLIVER)], AREA) == pytest.approx(20.0)


def test_item_without_footprint_covers_nothing() -> None:
    assert scenes.coverage([make_item("a", WHEN, 0.0, None)], AREA) == 0.0


# pick_date


def test_closest_clear_date_beats_clearer_far_date() -> None:
    candidates = [scene("2023-09-01", 0.0), scene("2023-10-10", 15.0), scene("2023-10-12", 60.0)]
    picked, clear = pick_date(candidates, date(2023, 10, 14), max_cloud=20)
    assert picked.day == date(2023, 10, 10)
    assert clear


def test_limit_is_inclusive() -> None:
    _, clear = pick_date([scene("2023-10-10", 20.0)], date(2023, 10, 14), max_cloud=20)
    assert clear


def test_no_clear_date_falls_back_to_least_cloudy() -> None:
    candidates = [scene("2023-10-01", 40.0), scene("2023-10-12", 70.0)]
    picked, clear = pick_date(candidates, date(2023, 10, 14), max_cloud=20)
    assert picked.day == date(2023, 10, 1)
    assert not clear


def test_fallback_tie_goes_to_closer_date() -> None:
    candidates = [scene("2023-10-01", 40.0), scene("2023-10-12", 40.0)]
    picked, _ = pick_date(candidates, date(2023, 10, 14), max_cloud=20)
    assert picked.day == date(2023, 10, 12)


def test_no_candidates_raises() -> None:
    with pytest.raises(ValueError, match="no scene dates"):
        pick_date([], date(2023, 10, 14), max_cloud=20)


# find_scenes, with the outline and search replaced by fakes


@pytest.fixture
def config() -> Config:
    return load_config(REPO_CONFIG)


@pytest.fixture
def fire() -> FireConfig:
    return FireConfig.model_validate(
        {
            "id": "test-fire",
            "name": "Test Fire",
            "npws_fire_no": "23101400001",
            "start_date": "2023-10-14",
            "end_date": "2023-11-08",
        }
    )


@pytest.fixture
def fake_search(monkeypatch: pytest.MonkeyPatch) -> list[pystac.Item]:
    """Replace the STAC search. Tests fill the returned list with items."""
    items: list[pystac.Item] = []
    monkeypatch.setattr(scenes, "search_items", lambda config, bbox, start, end: items)
    return items


def test_find_scenes_keeps_fire_dates_out_of_windows(
    config: Config, fire: FireConfig, fake_search: list[pystac.Item]
) -> None:
    fake_search += [
        make_item("before", datetime(2023, 10, 10, 0, 0, tzinfo=UTC), 5.0),
        # 23:58 UTC on the 13th is the fire's start date (the 14th) in NSW, so it's not pre-fire.
        make_item("start-day", datetime(2023, 10, 13, 23, 58, tzinfo=UTC), 0.0),
        make_item("end-day", datetime(2023, 11, 8, 0, 0, tzinfo=UTC), 0.0),
        make_item("after", datetime(2023, 11, 12, 0, 0, tzinfo=UTC), 5.0),
    ]
    pre, post = scenes.find_scenes(config, fire, AREA)
    assert pre.item_ids == ("before",)
    assert post.item_ids == ("after",)


def test_find_scenes_warns_when_no_date_is_clear(
    config: Config,
    fire: FireConfig,
    fake_search: list[pystac.Item],
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_search += [
        make_item("cloudy", datetime(2023, 10, 10, 0, 0, tzinfo=UTC), 90.0),
        make_item("after", datetime(2023, 11, 12, 0, 0, tzinfo=UTC), 5.0),
    ]
    with caplog.at_level(logging.WARNING, logger="fesmqa"):
        pre, _ = scenes.find_scenes(config, fire, AREA)
    assert pre.item_ids == ("cloudy",)
    assert "no pre-fire date is at or below 20" in caplog.text


def test_find_scenes_skips_clear_sliver_for_covering_date(
    config: Config, fire: FireConfig, fake_search: list[pystac.Item]
) -> None:
    # The sliver is closer to the fire and "0% cloud", but shows only a strip of the outline.
    fake_search += [
        make_item("full", datetime(2023, 10, 1, 0, 0, tzinfo=UTC), 10.0),
        make_item("sliver", datetime(2023, 10, 12, 0, 0, tzinfo=UTC), 0.0, SLIVER),
        make_item("after", datetime(2023, 11, 12, 0, 0, tzinfo=UTC), 5.0),
    ]
    pre, _ = scenes.find_scenes(config, fire, AREA)
    assert pre.item_ids == ("full",)


def test_find_scenes_only_slivers_raises(
    config: Config, fire: FireConfig, fake_search: list[pystac.Item]
) -> None:
    fake_search += [
        make_item("sliver", datetime(2023, 10, 12, 0, 0, tzinfo=UTC), 0.0, SLIVER),
        make_item("after", datetime(2023, 11, 12, 0, 0, tzinfo=UTC), 5.0),
    ]
    with pytest.raises(ValueError, match="no pre-fire date .* covers at least 99"):
        scenes.find_scenes(config, fire, AREA)


def test_find_scenes_empty_window_raises(
    config: Config, fire: FireConfig, fake_search: list[pystac.Item]
) -> None:
    fake_search.append(make_item("after", datetime(2023, 11, 12, 0, 0, tzinfo=UTC), 5.0))
    with pytest.raises(ValueError, match="no pre-fire scenes"):
        scenes.find_scenes(config, fire, AREA)
