"""Minimal read-only probe for a physical FreeStyle Libre 2 reader.

Connects, retrieves history and events, prints both raw CSV records
and the parsed model objects, then disconnects cleanly.

No modifications are made to the reader.  Only $history? and $arresult?
commands are issued (via the existing LibreReader implementation).
"""

from __future__ import annotations

import itertools
import logging
import sys

from libre.models import GlucoseRecord, TimeAdjustment
from libre.parser import parse_events, parse_history
from libre.reader import DeviceNotFoundError, LibreReader


def _print_separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _print_glucose(r: GlucoseRecord, index: int) -> None:
    print(
        f"  [{index:3d}] {r.timestamp}  "
        f"{r.glucose_mg_dl:>6.0f} mg/dL  "
        f"source={r.source}  trend={r.trend or '-'}  "
        f"id={r.device_id}"
    )
    if r.event:
        print(f"        event: {r.event}")


def _print_time_adj(t: TimeAdjustment, index: int) -> None:
    print(
        f"  [{index:3d}] {t.timestamp}  "
        f"old={t.old_timestamp}  id={t.device_id}"
    )


def probe() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
    )

    _print_separator("FreeStyle Libre 2 — Read-Only Probe")

    # --- Step 1: enumerate ------------------------------------------------
    import hid

    from libre.reader import LIBRE2_PID, LIBRE2_VID

    devices = hid.enumerate(LIBRE2_VID, LIBRE2_PID)
    if not devices:
        print(
            f"No device found (VID {LIBRE2_VID:04X} / PID {LIBRE2_PID:04X})."
        )
        sys.exit(1)

    dev = devices[0]
    print(f"\nDevice found:")
    print(f"  path             : {dev.get('path', b'')!r}")
    print(f"  serial_number    : {dev.get('serial_number', '?')}")
    print(f"  manufacturer     : {dev.get('manufacturer_string', '?')}")
    print(f"  product          : {dev.get('product_string', '?')}")
    print(f"  usage_page       : 0x{dev.get('usage_page', 0):04X}")
    print(f"  usage            : 0x{dev.get('usage', 0):04X}")

    # --- Step 2: connect & handshake --------------------------------------
    try:
        reader = LibreReader()
        device_info = reader.open()
    except DeviceNotFoundError as exc:
        print(f"\nConnection failed: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nUnexpected error connecting: {type(exc).__name__}: {exc}")
        sys.exit(1)

    print(f"\nConnected and handshake OK.")

    # --- Step 3: retrieve & display data ----------------------------------
    try:
        # -- $history? (automatic CGM sensor readings) --------------------
        _print_separator("$history? — Sensor Readings")
        raw_hist = reader._session.query_multirecord(b"$history?")
        raw_hist_a, raw_hist_b = itertools.tee(raw_hist)

        raw_rows = list(raw_hist_a)
        for i, row in enumerate(raw_rows, 1):
            print(f"  RAW [{i:3d}]: {list(row)}")
        if not raw_rows:
            print("  (no raw records)")

        parsed_list = list(parse_history(iter(raw_rows)))

        _print_separator("Parsed GlucoseRecord (history)")
        if not parsed_list:
            print("  (no valid records after parsing)")
        for i, rec in enumerate(parsed_list, 1):
            _print_glucose(rec, i)
        print(f"\n  Total history records parsed: {len(parsed_list)}")

        # -- $arresult? (manual readings, scans, events) ------------------
        _print_separator("$arresult? — Events & Manual Readings")
        raw_events = reader._session.query_multirecord(b"$arresult?")
        raw_ev_a, raw_ev_b = itertools.tee(raw_events)

        raw_ev_rows = list(raw_ev_a)
        for i, row in enumerate(raw_ev_rows, 1):
            print(f"  RAW [{i:3d}]: {list(row)}")
        if not raw_ev_rows:
            print("  (no raw records)")

        parsed_events = list(parse_events(iter(raw_ev_rows)))

        _print_separator("Parsed Events (arresult)")
        if not parsed_events:
            print("  (no valid events after parsing)")
        for i, rec in enumerate(parsed_events, 1):
            if isinstance(rec, GlucoseRecord):
                _print_glucose(rec, i)
            elif isinstance(rec, TimeAdjustment):
                _print_time_adj(rec, i)
            else:
                print(f"  [{i:3d}] Unknown: {rec}")
        print(f"\n  Total event records parsed: {len(parsed_events)}")

    finally:
        reader.close()
        print(f"\nReader closed cleanly.")


if __name__ == "__main__":
    probe()
