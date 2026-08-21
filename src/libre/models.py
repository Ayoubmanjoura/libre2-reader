"""Data models for FreeStyle Libre 2 glucose records."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True, slots=True)
class GlucoseRecord:
    """A single glucose reading from the Libre 2 reader.

    All glucose values are in mg/dL (device native unit).
    Set trend to None if the record does not carry trend information.
    """

    timestamp: datetime.datetime
    glucose_mg_dl: float
    trend: Optional[str] = None
    source: str = "sensor"
    device_id: str = ""
    event: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TimeAdjustment:
    """A clock change event recorded by the reader."""

    timestamp: datetime.datetime
    old_timestamp: datetime.datetime
    device_id: str = ""
