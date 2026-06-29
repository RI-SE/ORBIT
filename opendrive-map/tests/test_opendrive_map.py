"""Tests for opendrive-map, focused on the gaps the old parsers had."""

import math

import numpy as np
import pytest

from opendrive_map import RoadNetwork

# A straight 100 m road, one 3 m driving lane each side, header offset, UTM
# geoReference WITHOUT +lat_0/+lon_0 (the case that silently broke data-metrics).
STRAIGHT = """<OpenDRIVE>
  <header revMajor="1" revMinor="8">
    <geoReference>+proj=utm +zone=33 +north +datum=WGS84 +units=m +no_defs</geoReference>
    <offset x="320000.0" y="6375000.0" z="0.0" hdg="0.0"/>
  </header>
  <road id="1" length="100.0" junction="-1">
    <planView>
      <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0"><line/></geometry>
    </planView>
    <lanes>
      <laneOffset s="0.0" a="0.0" b="0.0" c="0.0" d="0.0"/>
      <laneSection s="0.0">
        <left><lane id="1" type="driving"><width sOffset="0.0" a="3.0" b="0.0" c="0.0" d="0.0"/></lane></left>
        <right><lane id="-1" type="sidewalk"><width sOffset="0.0" a="2.0" b="0.0" c="0.0" d="0.0"/></lane></right>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>"""

# Quarter-circle arc, radius 50 (curvature 0.02), one driving lane.
ARC = """<OpenDRIVE>
  <header revMajor="1" revMinor="8"/>
  <road id="1" length="78.539816" junction="-1">
    <planView>
      <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="78.539816"><arc curvature="0.02"/></geometry>
    </planView>
    <lanes>
      <laneSection s="0.0">
        <left><lane id="1" type="driving"><width sOffset="0.0" a="3.0" b="0.0" c="0.0" d="0.0"/></lane></left>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>"""

# Two lane sections + variable lane width (b != 0).
MULTISECTION = """<OpenDRIVE>
  <header revMajor="1" revMinor="8"/>
  <road id="1" length="100.0" junction="-1">
    <planView>
      <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0"><line/></geometry>
    </planView>
    <lanes>
      <laneSection s="0.0">
        <left><lane id="1" type="driving"><width sOffset="0.0" a="3.0" b="0.02" c="0.0" d="0.0"/></lane></left>
      </laneSection>
      <laneSection s="50.0">
        <left><lane id="1" type="driving"><width sOffset="0.0" a="4.0" b="0.0" c="0.0" d="0.0"/></lane></left>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>"""


def test_offset_from_header_not_georef():
    """Offset must come from <offset>, even when geoReference lacks lat_0/lon_0."""
    net = RoadNetwork.from_text(STRAIGHT)
    assert net.offset == (320000.0, 6375000.0, 0.0)
    assert net.to_global(0.0, 0.0) == (320000.0, 6375000.0)
    assert net.to_local(*net.to_global(12.0, 34.0)) == pytest.approx((12.0, 34.0))


def test_straight_lane_geometry_and_assignment():
    net = RoadNetwork.from_text(STRAIGHT)
    driving = [ln for ln in net.lanes if ln.type == "driving"]
    assert len(driving) == 1
    lane = driving[0]
    assert lane.length_m == pytest.approx(100.0, abs=1e-3)
    assert lane.width_at(0.0) == pytest.approx(3.0)
    # Left lane centre sits at +1.5 m (left of +x heading => +y).
    assert net.assign_lane(50.0, 1.5) is lane
    assert net.assign_lane(50.0, -1.5).type == "sidewalk"
    assert net.assign_lane(50.0, 99.0) is None


def test_lane_type_filter():
    net = RoadNetwork.from_text(STRAIGHT, lane_types=["driving"])
    assert {ln.type for ln in net.lanes} == {"driving"}


def test_arc_is_not_degraded_to_line():
    net = RoadNetwork.from_text(ARC)
    lane = net.lanes[0]
    cl = lane.centerline
    # Reference-line endpoint of a quarter circle radius 50 starting along +x:
    # centre (0,50); end heading pi/2 -> point (50, 50). Lane centre offset +1.5 inward.
    chord_mid = (cl[0] + cl[-1]) / 2.0
    actual_mid = cl[len(cl) // 2]
    # A real arc bows away from the chord midpoint; a line would not.
    assert np.linalg.norm(actual_mid - chord_mid) > 5.0
    # Arc length clearly exceeds the straight chord distance.
    chord = np.linalg.norm(cl[-1] - cl[0])
    assert lane.length_m > chord + 5.0


PARKING = """<OpenDRIVE>
  <header revMajor="1" revMinor="8"/>
  <road id="1" length="100.0" junction="-1">
    <planView>
      <geometry s="0.0" x="0.0" y="0.0" hdg="0.0" length="100.0"><line/></geometry>
    </planView>
    <lanes>
      <laneSection s="0.0">
        <left><lane id="1" type="driving"><width sOffset="0.0" a="3.0" b="0.0" c="0.0" d="0.0"/></lane></left>
      </laneSection>
    </lanes>
    <objects>
      <object type="parking" s="50.0" t="-5.0" hdg="0.0" length="5.0" width="2.5">
        <outline>
          <cornerLocal u="-2.5" v="-1.25"/><cornerLocal u="2.5" v="-1.25"/>
          <cornerLocal u="2.5" v="1.25"/><cornerLocal u="-2.5" v="1.25"/>
        </outline>
      </object>
    </objects>
  </road>
</OpenDRIVE>"""


def test_parking_placement():
    net = RoadNetwork.from_text(PARKING)
    assert len(net.parking) == 1
    assert len(net.parking_polygons) == 1
    poly = net.parking_polygons[0]
    # Road runs along +x; object at s=50, t=-5 (right side) -> centre near (50, -5).
    cx, cy = poly.centroid.x, poly.centroid.y
    assert cx == pytest.approx(50.0, abs=1.0)
    assert cy == pytest.approx(-5.0, abs=0.5)
    assert poly.area == pytest.approx(5.0 * 2.5, rel=1e-6)  # 5.0 x 2.5 outline


def test_variable_width_and_multisection():
    net = RoadNetwork.from_text(MULTISECTION)
    lanes = sorted(net.lanes, key=lambda ln: ln.section_s)
    assert len(lanes) == 2  # both sections built (old parser used only the first)
    s0, s1 = lanes
    assert s0.section_s == 0.0 and s1.section_s == 50.0
    # Variable width: 3.0 at start, 3.0 + 0.02*40 = 3.8 at s_rel=40.
    assert s0.width_at(0.0) == pytest.approx(3.0)
    assert s0.width_at(40.0) == pytest.approx(3.8)
    assert s1.width_at(0.0) == pytest.approx(4.0)
