# ORBIT Test Suite

This directory contains the test suite for ORBIT (OpenDrive Road Builder from Imagery Tool).

## Setup

Before running tests, install the package in development mode:

```bash
# Install ORBIT in editable mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt
```

## Running Tests

```bash
# Run all tests
pytest tests/unit/

# Run with verbose output
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_models/test_project.py

# Run specific test
pytest tests/unit/test_models/test_project.py::TestProjectCreation::test_empty_project_creation
```

## Coverage

```bash
# Run tests with coverage report
pytest tests/unit/ --cov=orbit --cov-report=term-missing

# Generate HTML coverage report
pytest tests/unit/ --cov=orbit --cov-report=html
# Then open htmlcov/index.html in browser
```

## Test Structure

```
tests/
├── conftest.py                  # Shared fixtures and test configuration
├── test_data/                   # Real test data from examples/
│   ├── ekas_from_overpass2.orbit
│   ├── ekas_geo2.orbit
│   ├── BorasEkas_coords_2025-09-25_C2.csv
│   └── out3_stabilized_vidrectify_first.jpg
│
└── unit/                        # Unit tests
    ├── test_models/             # Tests for data models
    │   ├── test_project.py      # Project save/load, element management
    │   ├── test_polyline.py     # Polyline operations
    │   ├── test_road.py         # Road logic, lane sections
    │   ├── test_lane.py         # Lane properties
    │   └── test_lane_section.py # Section splitting, boundaries
    │
    ├── test_export/             # Tests for export functionality
    │   ├── test_coordinate_transform.py  # Georeferencing transforms
    │   └── test_curve_fitting.py         # Geometric fitting
    │
    └── test_utils/              # Tests for utility functions
        └── test_geometry.py     # Geometric calculations
```

## Current Coverage (Phase 1)

- **274 tests** passing (all tests)
- **13% overall** (includes untested GUI code)
- **60-99% coverage** for tested non-GUI modules:
  - models/polyline.py: 99%
  - models/lane_section.py: 98%
  - utils/geometry.py: 95%
  - models/lane.py: 82%
  - utils/coordinate_transform.py: 79%

**Real-world data tests**: The coordinate transformation tests use real control points extracted from `ekas_from_overpass2.orbit` (6 control points with both pixel and geo coordinates). These verify transformation accuracy with actual georeferencing data.

See `dev_plans/TEST_PLAN.md` for the complete testing roadmap.

## Writing Tests

### Using Fixtures

Fixtures are defined in `conftest.py` and provide reusable test data:

```python
def test_my_feature(sample_project):
    """Test using sample project fixture."""
    assert len(sample_project.polylines) == 3
```

### Test Organization

- Group related tests in classes (e.g., `TestProjectCreation`)
- Use descriptive test names: `test_what_it_does`
- Follow Arrange-Act-Assert pattern
- Use `pytest.approx()` for floating-point comparisons

### Example Test

```python
class TestPolylineCreation:
    """Test polyline initialization."""

    def test_empty_polyline_creation(self):
        """Test creating an empty polyline."""
        # Arrange
        polyline = Polyline()

        # Act & Assert
        assert polyline.points == []
        assert polyline.closed is False
```

## Future Phases

- **Phase 2**: Integration tests, import/export coverage
- **Phase 3**: Minimal GUI tests for dialog validation
- **Phase 4**: CI/CD setup, coverage enforcement

See `dev_plans/TEST_PLAN.md` for details.
