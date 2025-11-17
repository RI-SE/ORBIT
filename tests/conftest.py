"""
Pytest configuration and shared fixtures for ORBIT tests.

Provides reusable test data and helper functions for unit and integration tests.
"""

import pytest
from pathlib import Path
from typing import List

from orbit.models import (
    Project, ControlPoint, Polyline, LineType, RoadMarkType,
    Road, RoadType, LaneInfo, Lane, LaneType, LaneSection,
    Junction
)


# ============================================================================
# Path Fixtures
# ============================================================================

@pytest.fixture
def test_data_dir() -> Path:
    """Path to test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture
def example_project_path(test_data_dir: Path) -> Path:
    """Path to example .orbit project file."""
    return test_data_dir / "ekas_from_overpass2.orbit"


@pytest.fixture
def georef_project_path(test_data_dir: Path) -> Path:
    """Path to georeferenced example project."""
    return test_data_dir / "ekas_geo2.orbit"


@pytest.fixture
def control_points_csv(test_data_dir: Path) -> Path:
    """Path to control points CSV file with pixel coordinates (for testing)."""
    return test_data_dir / "control_points_with_pixels.csv"


# ============================================================================
# Model Fixtures - ControlPoint
# ============================================================================

@pytest.fixture
def sample_control_points() -> List[ControlPoint]:
    """
    Create sample control points for testing.

    Returns three non-collinear control points suitable for affine transformation.
    """
    return [
        ControlPoint(
            pixel_x=100.0, pixel_y=100.0,
            longitude=12.940000, latitude=57.720000,
            name="CP1"
        ),
        ControlPoint(
            pixel_x=500.0, pixel_y=100.0,
            longitude=12.945000, latitude=57.720000,
            name="CP2"
        ),
        ControlPoint(
            pixel_x=300.0, pixel_y=400.0,
            longitude=12.942500, latitude=57.718000,
            name="CP3"
        ),
    ]


@pytest.fixture
def validation_control_point() -> ControlPoint:
    """Create a validation control point (GVP)."""
    return ControlPoint(
        pixel_x=250.0, pixel_y=250.0,
        longitude=12.942000, latitude=57.719000,
        name="GVP1",
        is_validation=True
    )


# ============================================================================
# Model Fixtures - Polyline
# ============================================================================

@pytest.fixture
def sample_polyline() -> Polyline:
    """
    Create a simple polyline with 5 points.

    Forms a roughly straight line from (0,0) to (400,0).
    """
    polyline = Polyline(
        line_type=LineType.LANE_BOUNDARY,
        road_mark_type=RoadMarkType.SOLID,
        color=(255, 255, 0)
    )
    for x in [0, 100, 200, 300, 400]:
        polyline.add_point(float(x), 0.0)
    return polyline


@pytest.fixture
def centerline_polyline() -> Polyline:
    """
    Create a centerline polyline.

    10 points from (0,100) to (900,100) - straight horizontal line.
    """
    polyline = Polyline(
        line_type=LineType.CENTERLINE,
        road_mark_type=RoadMarkType.NONE,
        color=(255, 0, 0)
    )
    for x in range(0, 1000, 100):
        polyline.add_point(float(x), 100.0)
    return polyline


@pytest.fixture
def boundary_polyline_left() -> Polyline:
    """Create a left boundary polyline parallel to centerline."""
    polyline = Polyline(
        line_type=LineType.LANE_BOUNDARY,
        road_mark_type=RoadMarkType.SOLID,
        color=(0, 255, 255)
    )
    for x in range(0, 1000, 100):
        polyline.add_point(float(x), 85.0)  # 15 pixels above centerline
    return polyline


@pytest.fixture
def boundary_polyline_right() -> Polyline:
    """Create a right boundary polyline parallel to centerline."""
    polyline = Polyline(
        line_type=LineType.LANE_BOUNDARY,
        road_mark_type=RoadMarkType.BROKEN,
        color=(0, 255, 255)
    )
    for x in range(0, 1000, 100):
        polyline.add_point(float(x), 115.0)  # 15 pixels below centerline
    return polyline


# ============================================================================
# Model Fixtures - Lane
# ============================================================================

@pytest.fixture
def sample_lane_left() -> Lane:
    """Create a left driving lane (lane ID = 1)."""
    return Lane(
        id=1,
        lane_type=LaneType.DRIVING,
        road_mark_type=RoadMarkType.SOLID,
        width=3.5
    )


@pytest.fixture
def sample_lane_center() -> Lane:
    """Create a center lane (lane ID = 0)."""
    return Lane(
        id=0,
        lane_type=LaneType.NONE,
        road_mark_type=RoadMarkType.NONE,
        width=0.0
    )


@pytest.fixture
def sample_lane_right() -> Lane:
    """Create a right driving lane (lane ID = -1)."""
    return Lane(
        id=-1,
        lane_type=LaneType.DRIVING,
        road_mark_type=RoadMarkType.BROKEN,
        width=3.5
    )


# ============================================================================
# Model Fixtures - LaneSection
# ============================================================================

@pytest.fixture
def sample_lane_section() -> LaneSection:
    """
    Create a lane section with 2 lanes (1 left, 1 right).

    Section covers s=0 to s=500 (pixels).
    """
    section = LaneSection(
        section_number=1,
        s_start=0.0,
        s_end=500.0,
        end_point_index=5
    )
    section.lanes = [
        Lane(id=1, lane_type=LaneType.DRIVING, width=3.5),
        Lane(id=0, lane_type=LaneType.NONE, width=0.0),
        Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5),
    ]
    return section


@pytest.fixture
def two_section_lane_sections() -> List[LaneSection]:
    """Create two lane sections for testing section management."""
    section1 = LaneSection(
        section_number=1,
        s_start=0.0,
        s_end=300.0,
        end_point_index=3
    )
    section1.lanes = [
        Lane(id=1, lane_type=LaneType.DRIVING, width=3.5),
        Lane(id=0, lane_type=LaneType.NONE, width=0.0),
        Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5),
    ]

    section2 = LaneSection(
        section_number=2,
        s_start=300.0,
        s_end=900.0,
        end_point_index=None  # Last section
    )
    section2.lanes = [
        Lane(id=1, lane_type=LaneType.DRIVING, width=3.5),
        Lane(id=0, lane_type=LaneType.NONE, width=0.0),
        Lane(id=-1, lane_type=LaneType.DRIVING, width=3.5),
        Lane(id=-2, lane_type=LaneType.DRIVING, width=3.0),  # Additional right lane
    ]

    return [section1, section2]


# ============================================================================
# Model Fixtures - Road
# ============================================================================

@pytest.fixture
def sample_road(centerline_polyline: Polyline,
                boundary_polyline_left: Polyline,
                boundary_polyline_right: Polyline,
                sample_lane_section: LaneSection) -> Road:
    """
    Create a sample road with centerline, boundaries, and one lane section.

    Road has:
    - 1 centerline polyline
    - 2 boundary polylines
    - 1 lane section with 2 driving lanes
    """
    road = Road(
        name="Test Road",
        road_type=RoadType.TOWN,
        centerline_id=centerline_polyline.id,
        polyline_ids=[
            centerline_polyline.id,
            boundary_polyline_left.id,
            boundary_polyline_right.id
        ],
        lane_sections=[sample_lane_section]
    )
    return road


@pytest.fixture
def complex_road(centerline_polyline: Polyline,
                 boundary_polyline_left: Polyline,
                 boundary_polyline_right: Polyline,
                 two_section_lane_sections: List[LaneSection]) -> Road:
    """Create a road with multiple lane sections."""
    road = Road(
        name="Complex Road",
        road_type=RoadType.MOTORWAY,
        centerline_id=centerline_polyline.id,
        polyline_ids=[
            centerline_polyline.id,
            boundary_polyline_left.id,
            boundary_polyline_right.id
        ],
        lane_sections=two_section_lane_sections,
        speed_limit=110
    )
    return road


# ============================================================================
# Model Fixtures - Junction
# ============================================================================

@pytest.fixture
def sample_junction() -> Junction:
    """Create a simple junction for testing."""
    from orbit.models.junction import JunctionConnection

    junction = Junction(
        name="Test Junction",
        junction_type="default"
    )

    # Add a connection
    connection = JunctionConnection(
        incoming_road_id="road1",
        connecting_road_id="road2",
        contact_point="start"
    )
    junction.connections.append(connection)

    return junction


# ============================================================================
# Model Fixtures - Project
# ============================================================================

@pytest.fixture
def empty_project() -> Project:
    """Create an empty project with no data."""
    return Project()


@pytest.fixture
def sample_project(centerline_polyline: Polyline,
                   boundary_polyline_left: Polyline,
                   boundary_polyline_right: Polyline,
                   sample_road: Road,
                   sample_control_points: List[ControlPoint]) -> Project:
    """
    Create a sample project with basic data.

    Project contains:
    - 3 polylines (1 centerline, 2 boundaries)
    - 1 road with 1 lane section
    - 3 control points for georeferencing
    """
    project = Project(
        image_path=Path("/fake/path/to/image.jpg"),
        polylines=[centerline_polyline, boundary_polyline_left, boundary_polyline_right],
        roads=[sample_road],
        control_points=sample_control_points,
        transform_method='affine'
    )
    return project


@pytest.fixture
def complex_project(example_project_path: Path) -> Project:
    """
    Load a complex real project from test data.

    Note: This fixture requires the test data file to exist.
    Use for integration-like tests.
    """
    if not example_project_path.exists():
        pytest.skip(f"Test data file not found: {example_project_path}")

    return Project.load(example_project_path)


# ============================================================================
# Helper Functions
# ============================================================================

def assert_polyline_equal(poly1: Polyline, poly2: Polyline, check_id: bool = False) -> None:
    """
    Assert that two polylines are equal.

    Args:
        poly1: First polyline
        poly2: Second polyline
        check_id: If True, also check that IDs match
    """
    if check_id:
        assert poly1.id == poly2.id
    assert poly1.points == poly2.points
    assert poly1.color == poly2.color
    assert poly1.closed == poly2.closed
    assert poly1.line_type == poly2.line_type
    assert poly1.road_mark_type == poly2.road_mark_type


def assert_lane_equal(lane1: Lane, lane2: Lane) -> None:
    """Assert that two lanes are equal."""
    assert lane1.id == lane2.id
    assert lane1.lane_type == lane2.lane_type
    assert lane1.road_mark_type == lane2.road_mark_type
    assert lane1.width == pytest.approx(lane2.width)
    assert lane1.left_boundary_id == lane2.left_boundary_id
    assert lane1.right_boundary_id == lane2.right_boundary_id
