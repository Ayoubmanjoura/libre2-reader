# libre2-reader

A read-only Python library for reading FreeStyle Libre 2 glucose data over USB HID.

Strictly read-only: after the connection handshake only `$history?` and
`$arresult?` commands are issued. Nothing on the reader is ever modified.

## Installation

```bash
pip install libre2-reader
```

Requires Python 3.10+. USB access may need additional setup:

- **Windows:** usually works out of the box.
- **Linux:** install `libudev` / add udev rules for HID access (VID `1A61`, PID `3950`).
- **macOS:** supported via [HIDAPI](https://github.com/libusb/hidapi).

## Usage

```python
from libre import LibreReader

with LibreReader() as reader:
    # Automatic CGM sensor readings (with trend arrows)
    for record in reader.read_history():
        print(record.timestamp, record.glucose_mg_dl, record.trend)

    # Manual readings, sensor scans, ketones, and events
    for event in reader.read_events():
        print(event)
```

You can also check whether a reader is plugged in:

```python
from libre import detect_libre2

device = detect_libre2()
if device is None:
    print("No FreeStyle Libre 2 reader found")
```

### CLI probe

The package installs a `libre-probe` command that connects to the reader,
dumps raw CSV records plus parsed objects, and disconnects cleanly:

```bash
libre-probe
```

## License

MIT — see [LICENSE](LICENSE).

Parsing logic is ported from
[glucometerutils](https://github.com/flameeyes/glucometerutils)
(MIT, © The glucometerutils Authors) and uses
[freestyle-hid](https://github.com/glucometers-tech/freestyle-hid)
(Apache-2.0) for the USB protocol.
