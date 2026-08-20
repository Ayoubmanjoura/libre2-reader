# libre2-reader

A Python library for reading FreeStyle Libre 2 glucose data via USB.

## Installation ( - future - )

```bash
pip install libre
```

## Usage

```python
from libre import detect_libre2, parse_history

reader = detect_libre2()
records = parse_history(reader)
```

## License

MIT see [LICENSE](LICENSE).
