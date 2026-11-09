"""Load and validate config.yaml into typed, read-only settings."""

from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

PositiveDays = Annotated[int, Field(gt=0)]
FmaskValue = Annotated[int, Field(ge=0, le=5)]


class _Section(BaseModel):
    # Unknown keys are errors (catches typos), and settings can't be changed after loading.
    model_config = ConfigDict(extra="forbid", frozen=True)


class StacConfig(_Section):
    endpoint: HttpUrl
    collections: list[str] = Field(min_length=1)
    cloud_cover_property: str
    # A date is clear enough if its cloudiest tile's cloud cover (%) is at or below this.
    max_scene_cloud: float = Field(ge=0, le=100)


class BandsConfig(_Section):
    nir: str
    swir2: str
    fmask: str
    nodata: int
    fmask_keep: list[FmaskValue] = Field(min_length=1)


class GridConfig(_Section):
    resolution: float = Field(gt=0)
    crs: str | None = None


class DatesConfig(_Section):
    pre_fire_days: PositiveDays
    post_fire_days: PositiveDays


class SeverityConfig(_Section):
    thresholds: list[float] = Field(min_length=1)
    classes: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def thresholds_increase(self) -> Self:
        if any(a >= b for a, b in pairwise(self.thresholds)):
            raise ValueError(f"severity thresholds must strictly increase, got {self.thresholds}")
        return self


class QaConfig(_Section):
    """Gate limits are added in 3.1. Until then, any key here is an error."""


class OutlinesConfig(_Section):
    """Where fire outlines come from (1.3): a vector file and the field matching npws_fire_no."""

    path: str
    fire_no_field: str


class OutputsConfig(_Section):
    root: str


class FireConfig(_Section):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    # NPWS Fire History FireNo: the link to this fire's outline (1.3), independent of its name.
    npws_fire_no: str = Field(pattern=r"^\d+$")
    start_date: date
    end_date: date
    pre_fire_days: PositiveDays | None = None
    post_fire_days: PositiveDays | None = None

    @model_validator(mode="after")
    def end_not_before_start(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError(f"fire {self.id}: end_date is before start_date")
        return self


class Config(_Section):
    stac: StacConfig
    bands: BandsConfig
    grid: GridConfig
    dates: DatesConfig
    severity: SeverityConfig
    qa: QaConfig
    outlines: OutlinesConfig
    outputs: OutputsConfig
    fires: list[FireConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def fire_ids_unique(self) -> Self:
        ids = [f.id for f in self.fires]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate fire ids: {duplicates}")
        return self

    def fire(self, fire_id: str) -> FireConfig:
        """Return the fire with this id, or raise KeyError listing the known ids."""
        for f in self.fires:
            if f.id == fire_id:
                return f
        known = ", ".join(f.id for f in self.fires) or "none"
        raise KeyError(f"unknown fire {fire_id!r}; fires in config: {known}")

    def search_windows(self, fire: FireConfig) -> tuple[int, int]:
        """Pre- and post-fire search windows in days: the fire's own values, else the defaults."""
        pre = fire.pre_fire_days or self.dates.pre_fire_days
        post = fire.post_fire_days or self.dates.post_fire_days
        return pre, post


def load_config(path: str | Path) -> Config:
    """Read a YAML config file and validate it. Raises pydantic.ValidationError if it's invalid."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return Config.model_validate(data)
