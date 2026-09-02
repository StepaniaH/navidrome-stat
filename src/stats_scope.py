"""Validated, immutable scope shared by dashboard reads and cache keys."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.artist_credits import ARTIST_MODES
from src.schemas import (
    RANKING_METRIC_DEFAULT,
    RANKING_METRICS,
    STATS_DAYS_ALL,
    STATS_DAYS_MAX,
    STATS_DAYS_MIN,
    TIMEZONE_DEFAULT,
)
from src.windows import resolve_timezone


@dataclass(frozen=True, slots=True)
class StatsScope:
    """One validated historical-statistics selection.

    The object is hashable, so the values used to build SQL predicates are
    exactly the values used in the snapshot-cache key.
    """

    days: int
    timezone_name: str = TIMEZONE_DEFAULT
    metric: str = RANKING_METRIC_DEFAULT
    source_id: str | None = None
    username: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    artist_mode: str = "combined"

    @classmethod
    def create(
        cls,
        *,
        days: int,
        timezone_name: str = TIMEZONE_DEFAULT,
        metric: str = RANKING_METRIC_DEFAULT,
        source_id: str | None = None,
        username: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        artist_mode: str = "combined",
    ) -> StatsScope:
        if days != STATS_DAYS_ALL and not STATS_DAYS_MIN <= days <= STATS_DAYS_MAX:
            raise ValueError(
                f"days must be {STATS_DAYS_ALL} (all history) or between "
                f"{STATS_DAYS_MIN} and {STATS_DAYS_MAX}"
            )
        try:
            resolve_timezone(timezone_name)
        except ValueError as exc:
            raise ValueError("timezone must be a valid IANA timezone name") from exc
        if metric not in RANKING_METRICS:
            raise ValueError("metric must be one of: plays, listen_time")
        if artist_mode not in ARTIST_MODES:
            raise ValueError("artist_mode must be one of: combined, separate")
        if (start_date is None) != (end_date is None):
            raise ValueError("start_date and end_date must be provided together")
        if start_date is not None and end_date is not None:
            if start_date > end_date:
                raise ValueError("start_date must not be after end_date")
            if (end_date - start_date).days + 1 > 366:
                raise ValueError("custom date range must not exceed 366 days")
        return cls(
            days=days,
            timezone_name=timezone_name,
            metric=metric,
            source_id=source_id,
            username=username,
            start_date=start_date,
            end_date=end_date,
            artist_mode=artist_mode,
        )

    def query_kwargs(self) -> dict:
        """Return the shared keyword arguments consumed by statistics queries."""
        return {
            "days": self.days,
            "timezone_name": self.timezone_name,
            "source_id": self.source_id,
            "username": self.username,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }
