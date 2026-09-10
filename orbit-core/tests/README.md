# ORBIT Test Suite

This directory contains tests for ORBIT (OpenDrive Road Builder from Imagery Tool).

## Setup

```bash
# Install runtime + development dependencies
uv sync --extra dev
```

## Running tests

```bash
# Full suite
uv run python -m pytest tests/ -v

# Exclude slow/gui tests
uv run python -m pytest tests/ -v -m "not slow and not gui"

# Single file
uv run python -m pytest tests/unit/test_models/test_project.py -v

# Single test
uv run python -m pytest tests/unit/test_models/test_project.py::TestProjectCreation::test_empty_project_creation -v
```

For headless environments (CI), use:

```bash
QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ -v
```

## Coverage

```bash
# Terminal + XML + JSON reports
QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ \
  --cov=orbit \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-report=json:temp/coverage.json

# HTML report
QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ \
  --cov=orbit \
  --cov-report=html
```

## Current baseline

Measured from full suite with coverage:

- `2416` tests passing
- `38%` overall coverage (`orbit`: 10,960 / 28,783 statements)
- Package coverage:
  - `orbit/models`: 84.5%
  - `orbit/utils`: 71.6%
  - `orbit/export`: 64.4%
  - `orbit/import`: 63.5%
  - `orbit/gui`: 9.2%

Largest non-GUI coverage gaps to prioritize:

- `orbit/export/osm_writer.py` (0%)
- `orbit/export/osm_mappings.py` (0%)
- `orbit/roundabout_creator.py` (0%)
- `orbit/utils/geometry_validator.py` (9.2%)
- `orbit/utils/connecting_road_alignment.py` (13.0%)
- `orbit/utils/reproject.py` (34.3%)
- `orbit/import/opendrive_importer.py` (36.7%)
- `orbit/import/osm_importer.py` (31.0%)

## Maintainability report

Use the repo script to inspect large files/functions and uncovered hotspots:

```bash
uv run python tools/maintainability_report.py --coverage-json temp/coverage.json
```

## Writing tests

- Reuse fixtures from `tests/conftest.py` where possible.
- Prefer focused tests around one behavior at a time.
- For float math, use `pytest.approx()`.

See also [DEV_GUIDE.md](../docs/DEV_GUIDE.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).
