"""Detect and read from a FreeStyle Libre 2 reader over USB HID.

This module is strictly read-only.  The only commands issued after the
connection handshake are ``$history?`` and ``$arresult?``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Optional

import freestyle_hid
import hid

from libre.models import GlucoseRecord, TimeAdjustment
from libre.parser import parse_events, parse_history

logger = logging.getLogger(__name__)

LIBRE2_VID = 0x1A61
LIBRE2_PID = 0x3950


class DeviceNotFoundError(Exception):
    """No FreeStyle Libre 2 reader found on USB."""


def detect_libre2() -> Optional[dict]:
    """Enumerate USB HID devices and return the first Libre 2 reader found.

    Returns the raw ``hid.enumerate`` dict (with ``path``, ``serial_number``,
    ``manufacturer_string``, ``product_string``, etc.) or ``None``.
    """
    devices = hid.enumerate(LIBRE2_VID, LIBRE2_PID)
    if not devices:
        return None
    return devices[0]


class LibreReader:
    """Read-only connection to a FreeStyle Libre 2 reader.

    Usage::

        reader = LibreReader()
        try:
            reader.open()
            for record in reader.read_history():
                print(record)
        finally:
            reader.close()

    Or as a context manager::

        with LibreReader() as reader:
            for record in reader.read_history():
                print(record)
    """

    def __enter__(self) -> "LibreReader":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> dict:
        """Open the HID device and perform the encrypted handshake.

        Returns the device info dict from ``hid.enumerate``.
        """
        device_info = detect_libre2()
        if device_info is None:
            raise DeviceNotFoundError(
                "No FreeStyle Libre 2 reader found "
                f"(VID {LIBRE2_VID:04X}, PID {LIBRE2_PID:04X})."
            )

        logger.info(
            "Opening Libre 2 reader: %s (%s, serial %s)",
            device_info["product_string"],
            device_info["manufacturer_string"],
            device_info["serial_number"],
        )

        self._session = freestyle_hid.Session(
            product_id=LIBRE2_PID,
            device_path=None,
            text_message_type=0x60,
            text_reply_message_type=0x60,
            encoding="utf-8",
            encrypted=True,
        )
        self._session.connect()
        return device_info

    def close(self) -> None:
        """Release resources.  Safe to call multiple times."""
        self._session = None

    # -- data retrieval -----------------------------------------------------

    def read_history(self) -> Iterator[GlucoseRecord]:
        """Return all automatic CGM sensor readings from the device."""
        self._ensure_open()
        assert self._session is not None
        raw = self._session.query_multirecord(b"$history?")
        return parse_history(raw)

    def read_events(self) -> Iterator[GlucoseRecord | TimeAdjustment]:
        """Return all manual readings, scans, and events from the device."""
        self._ensure_open()
        assert self._session is not None
        raw = self._session.query_multirecord(b"$arresult?")
        return parse_events(raw)

    # -- internal -----------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._session is None:
            raise RuntimeError("Reader is not open.  Call open() first.")
