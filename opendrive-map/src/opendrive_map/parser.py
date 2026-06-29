"""Parse OpenDRIVE XML into the raw road model (local frame; no lanes built yet)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from .model import (
    Connection,
    GeomSegment,
    Junction,
    LaneSection,
    ParkingObject,
    Poly,
    RawLane,
    Road,
)

_GEOM_KINDS = ("line", "arc", "spiral", "poly3", "paramPoly3")


def _polys(elements, *, with_soffset_attr: str = "sOffset") -> List[Poly]:
    out: List[Poly] = []
    for el in elements:
        out.append(
            Poly(
                sOffset=float(el.get(with_soffset_attr, 0.0)),
                a=float(el.get("a", 0.0)),
                b=float(el.get("b", 0.0)),
                c=float(el.get("c", 0.0)),
                d=float(el.get("d", 0.0)),
            )
        )
    out.sort(key=lambda p: p.sOffset)
    return out


def parse_offset(root: ET.Element) -> Tuple[float, float, float]:
    """Authoritative header <offset> (absolute = local + offset). Defaults to 0."""
    off = root.find("header/offset")
    if off is None:
        return 0.0, 0.0, 0.0
    return float(off.get("x", 0.0)), float(off.get("y", 0.0)), float(off.get("z", 0.0))


def parse_geo_reference(root: ET.Element) -> Optional[str]:
    """Raw <geoReference> PROJ string, or None."""
    geo = root.find("header/geoReference")
    return geo.text.strip() if geo is not None and geo.text else None


def _parse_road(road_el: ET.Element) -> Road:
    road = Road(
        id=road_el.get("id", ""),
        length=float(road_el.get("length", 0.0)),
        junction=road_el.get("junction", "-1"),
    )

    for g in road_el.findall("./planView/geometry"):
        children = list(g)
        kind = children[0].tag if children else "line"
        params = dict(children[0].attrib) if children and kind in _GEOM_KINDS else {}
        road.geom_segments.append(
            GeomSegment(
                s=float(g.get("s", 0.0)),
                x=float(g.get("x", 0.0)),
                y=float(g.get("y", 0.0)),
                hdg=float(g.get("hdg", 0.0)),
                length=float(g.get("length", 0.0)),
                kind=kind if kind in _GEOM_KINDS else "line",
                params=params,
            )
        )

    road.lane_offsets = _polys(road_el.findall("./lanes/laneOffset"), with_soffset_attr="s")

    for ls_el in road_el.findall("./lanes/laneSection"):
        section = LaneSection(s=float(ls_el.get("s", 0.0)))
        for side in ("left", "center", "right"):
            side_el = ls_el.find(side)
            if side_el is None:
                continue
            for lane_el in side_el.findall("lane"):
                lid = int(lane_el.get("id", 0))
                if lid == 0:
                    continue
                section.lanes.append(
                    RawLane(
                        id=lid,
                        type=lane_el.get("type", "none"),
                        widths=_polys(lane_el.findall("width")),
                    )
                )
        road.lane_sections.append(section)

    return road


def _parse_parking(road_el: ET.Element, road_id: str) -> List[ParkingObject]:
    out: List[ParkingObject] = []
    for obj in road_el.findall("./objects/object"):
        if obj.get("type") != "parking":
            continue
        outline = [
            (float(c.get("u", 0.0)), float(c.get("v", 0.0)))
            for c in obj.findall("./outline/cornerLocal")
        ]
        out.append(ParkingObject(
            road_id=road_id,
            s=float(obj.get("s", 0.0)),
            t=float(obj.get("t", 0.0)),
            hdg=float(obj.get("hdg", 0.0)),
            length=float(obj.get("length", 5.0)),
            width=float(obj.get("width", 2.0)),
            outline=outline,
        ))
    return out


def _parse_junction(j_el: ET.Element) -> Junction:
    junction = Junction(id=j_el.get("id", ""))
    for c in j_el.findall("connection"):
        junction.connections.append(
            Connection(
                incoming_road=c.get("incomingRoad", ""),
                connecting_road=c.get("connectingRoad", ""),
                contact_point=c.get("contactPoint", ""),
            )
        )
    return junction


def parse_xodr_text(text: str):
    """Parse XODR text → (roads, junctions, parking, offset, geo_reference)."""
    text = re.sub(r'\s+xmlns="[^"]+"', "", text)  # strip default namespace
    root = ET.fromstring(text)
    roads = [_parse_road(r) for r in root.findall("road")]
    junctions = [_parse_junction(j) for j in root.findall("junction")]
    parking = [
        p for r in root.findall("road") for p in _parse_parking(r, r.get("id", ""))
    ]
    return roads, junctions, parking, parse_offset(root), parse_geo_reference(root)
