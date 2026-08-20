"""Parse CSV records from FreeStyle Libre 2 $history? and $arresult? commands.

Field maps and parsing logic ported from glucometerutils/support/freestyle_libre.py
(MIT-licensed, (c) The glucometerutils Authors).
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterator, Sequence
from typing import Optional

from libre.models import GlucoseRecord, TimeAdjustment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field index maps (CSV column → named field)
# ---------------------------------------------------------------------------

_BASE_ENTRY_MAP: tuple[tuple[int, str], ...] = (
    (1, "type"),
    (2, "month"),
    (3, "day"),
    (4, "year"),
    (5, "hour"),
    (6, "minute"),
    (7, "second"),
)

_HISTORY_ENTRY_MAP: tuple[tuple[int, str], ...] = _BASE_ENTRY_MAP + (
    (13, "value"),
    (15, "errors"),
)

_ARRESULT_TYPE2_MAP: tuple[tuple[int, str], ...] = (
    (9, "reading_type"),
    (12, "value"),
    (15, "sport_flag"),
    (16, "medication_flag"),
    (17, "rapid_acting_flag"),
    (18, "long_acting_flag"),
    (19, "custom_comments_bitfield"),
    (23, "double_long_acting_insulin"),
    (25, "food_flag"),
    (26, "food_carbs_grams"),
    (28, "errors"),
)

_ARRESULT_TIME_ADJUSTMENT_MAP: tuple[tuple[int, str], ...] = (
    (9, "old_month"),
    (10, "old_day"),
    (11, "old_year"),
    (12, "old_hour"),
    (13, "old_minute"),
    (14, "old_second"),
)

_ARRESULT_RAPID_INSULIN_MAP: tuple[tuple[int, str], ...] = ((43, "double_rapid_acting_insulin"),)

# Trend arrow values from field 14 in $history? records.
# The protocol documentation defines these but the glucometerutils driver
# does not currently map them, so we define the mapping here.
_TREND_MAP: dict[int, str] = {
    0: "",
    1: "down-fast",
    2: "down",
    3: "steady",
    4: "up",
    5: "up-fast",
}


def _parse_fields(
    record: Sequence[str], entry_map: tuple[tuple[int, str], ...]
) -> dict[str, int]:
    """Extract named integer fields from a CSV row using an entry map."""
    if not record:
        return {}
    try:
        return {name: int(record[idx]) for idx, name in entry_map}
    except (IndexError, ValueError):
        return {}


def _get_device_id(record: Sequence[str]) -> str:
    """Extract the device ID (record ID) from column 0 as a string."""
    try:
        return record[0]
    except IndexError:
        return ""


def _build_timestamp(
    parsed: dict[str, int], prefix: str = ""
) -> datetime.datetime:
    """Build a datetime from parsed year/month/day/hour/minute/second fields."""
    return datetime.datetime(
        parsed[prefix + "year"] + 2000,
        parsed[prefix + "month"],
        parsed[prefix + "day"],
        parsed[prefix + "hour"],
        parsed[prefix + "minute"],
        parsed[prefix + "second"],
    )


def parse_history(records: Iterator[Sequence[str]]) -> Iterator[GlucoseRecord]:
    """Parse $history? CSV rows into GlucoseRecord objects.

    These are automatic CGM sensor measurements.
    """
    for record in records:
        parsed = _parse_fields(record, _HISTORY_ENTRY_MAP)
        if not parsed or parsed["errors"] != 0:
            continue

        raw_trend = 0
        try:
            raw_trend = int(record[14])
        except (IndexError, ValueError):
            pass

        trend = _TREND_MAP.get(raw_trend) or None

        yield GlucoseRecord(
            timestamp=_build_timestamp(parsed),
            glucose_mg_dl=float(parsed["value"]),
            trend=trend,
            source="sensor",
            device_id=_get_device_id(record),
        )


def parse_events(records: Iterator[Sequence[str]]) -> Iterator[GlucoseRecord | TimeAdjustment]:
    """Parse $arresult? CSV rows into GlucoseRecord or TimeAdjustment objects.

    Handles record types:
      2 = manual reading (blood strip, sensor scan, or ketone)
      5 = time adjustment event
    """
    for record in records:
        parsed_base = _parse_fields(record, _BASE_ENTRY_MAP)
        if not parsed_base:
            continue

        record_type = parsed_base["type"]

        if record_type == 5:
            yield _parse_time_adjustment(record, parsed_base)
            continue

        if record_type != 2:
            continue

        result = _parse_type2(record, parsed_base)
        if result is not None:
            yield result


def _parse_time_adjustment(
    record: Sequence[str], parsed_base: dict[str, int]
) -> TimeAdjustment:
    parsed_old = _parse_fields(record, _ARRESULT_TIME_ADJUSTMENT_MAP)
    return TimeAdjustment(
        timestamp=_build_timestamp(parsed_base),
        old_timestamp=_build_timestamp(parsed_old, "old_"),
        device_id=_get_device_id(record),
    )


def _parse_type2(
    record: Sequence[str], parsed_base: dict[str, int]
) -> Optional[GlucoseRecord]:
    parsed = _parse_fields(record, _ARRESULT_TYPE2_MAP)
    if not parsed:
        return None
    if parsed.get("errors", 0) != 0:
        return None

    reading_type = parsed["reading_type"]

    if reading_type == 2:
        source = "scan"
    elif reading_type == 0:
        source = "blood"
    elif reading_type == 1:
        source = "ketone"
    else:
        return None

    value = float(parsed["value"])
    if source == "ketone":
        value = value / 18.0

    # If the device flagged rapid-acting insulin, try to read that field.
    if parsed.get("rapid_acting_flag"):
        rapid_parsed = _parse_fields(record, _ARRESULT_RAPID_INSULIN_MAP)
        parsed.update(rapid_parsed)

    event: dict[str, object] = {}

    # Custom comments (fields 29-34, bits 0-5 of custom_comments_bitfield)
    comments: list[str] = []
    bitfield = parsed.get("custom_comments_bitfield", 0)
    for bit in range(6):
        if bitfield & (1 << bit):
            try:
                comments.append(record[29 + bit])
            except IndexError:
                pass
    if comments:
        event["comments"] = comments

    if parsed.get("sport_flag"):
        event["sport"] = True

    if parsed.get("medication_flag"):
        event["medication"] = True

    if parsed.get("food_flag"):
        event["food"] = True
        grams = parsed.get("food_carbs_grams", 0)
        if grams:
            event["carbohydrates_g"] = grams

    if parsed.get("long_acting_flag"):
        units = parsed.get("double_long_acting_insulin", 0) / 2
        event["long_acting_insulin_u"] = units

    if parsed.get("rapid_acting_flag"):
        raw = parsed.get("double_rapid_acting_insulin")
        if raw is not None:
            event["rapid_acting_insulin_u"] = raw / 2
        else:
            event["rapid_acting_insulin_u"] = None

    return GlucoseRecord(
        timestamp=_build_timestamp(parsed_base),
        glucose_mg_dl=value,
        trend=None,
        source=source,
        device_id=_get_device_id(record),
        event=event,
    )
