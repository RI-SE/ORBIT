# opendrive-map — development notes & future improvements

Scope: `opendrive-map` is a **read-only road-network + lane-geometry** library for a 2D
map viewer (COSMO `trajectory-explorer`) and a 2D traffic-metrics tool (`data-metrics`).
Keep it focused on roads/lanes/parking + the map offset. Add other categories only when a
consumer actually needs them — resist becoming an everything-parser.

## Done (2026-06-29)
- Parser robustness: negative polynomial `sOffset` clamped to 0; non-finite (NaN/inf)
  width/laneOffset records dropped with a warning; records sorted by `sOffset`.
- Breakpoint-aware sampling: `sample_reference_line(road, interval, breakpoints=...)` forces
  samples at lane-section / width / laneOffset transitions so polygon edges align with
  width changes (not just the interval grid).

---

## Q1 — Other ORBIT-exported elements (potential future parsing)

ORBIT can write these into a `.xodr` (most are absent from current drone maps, e.g.
GbgSaroRound has no objects/signals at all). Add on demand only.

| Element | OpenDRIVE form | Who'd use it | Recommendation |
|---|---|---|---|
| Buildings, land use (forest/farmland/meadow/water), trees, bushes, lampposts, guardrails | `<object>` with point/polyline/polygon `<outline>` (`cornerLocal` + `s/t/hdg`) | **Viewer only** (context layers); irrelevant to metrics | Add a generic `RoadObject(type, subtype, placed_polygon)` parser **iff the viewer wants context layers**. Cheap — reuse the parking placement path (`_parking_polygon` / `_road_point_at_s`). |
| Signals: stop, give-way, speed-limit, traffic-lights, priority | `<signal>` with `type/subtype`, `s/t`, `dynamic`, `<validity>` lanes | **Metrics** (intersection control, speed-limit context) + viewer overlay | Highest-value non-road addition. Add `Signal(type, subtype, s, t, dynamic, validity_lanes)` **when a concrete metric consumes it** (YAGNI until then). |
| Road marks (`<roadMark>`, dashed/solid + `<line>`) | per-lane boundary | Viewer cosmetic only | Skip unless rendering lane markings. |
| Road `type` (town/motorway/…), lane `type` | road/lane attrs | lane type already used as a filter | Road type: add only if a metric needs road-class defaults. |
| Elevation / superelevation profiles | `<elevationProfile>`, `<lateralProfile>` | 3D only | Skip (consumers are 2D). See Q2 §3. |
| Junction lane-links (predecessor/successor, connection lane maps) | `<junction>`, lane `<link>` | routing / turn analysis | Basic `Junction`(id, connections) already parsed; add lane-level links only for routing. |

Note: buildings & land use have **rich semantics only in ORBIT's OSM export**; in OpenDRIVE
they are generic geometry objects. If a consumer needs semantic building/landuse data, read
the OSM export, not the XODR.

---

## Q2 — Ideas from other projects (analyzed, not yet adopted)

### Worth doing later
1. **Spiral via Fresnel integrals** (`src/Geometries/Spiral/odrSpiral.cpp`). Our `geometry.py`
   `_sample_spiral` uses forward-Euler integration; measured error vs exact `scipy.special.fresnel`
   is ~2–5 cm on typical clothoids (R=30–50 m). **Low urgency** — current ORBIT maps use only
   line + paramPoly3 (no spirals). When needed: either `scipy.special.fresnel` (exact, adds a
   scipy dep) or a dependency-free RK2/midpoint integrator (~100× lower error than Euler, free).
2. **Multi-profile s-sampling** — partially done (breakpoints now injected). libOpenDRIVE also
   merges superelevation breakpoints; relevant only if we add 3D.
3. **More parser repair** (`check_and_repair` pattern in `OpenDriveMap.cpp`): enforce lane-0
   width = 0 (we skip center lanes, so N/A), `fromLane <= toLane` in signal validity (when we
   parse signals), reasonable-coefficient checks. Add as we parse more elements.

### Skip for 2D consumers (revisit only if scope changes)
- **3D**: elevation / superelevation / crossfall / lane-height surfaces (`Road::get_xyz`,
  `get_surface_pt`). Big effort; our consumers are 2D.
- **Symbolic border polynomials** (`CubicSpline`/`CubicProfile::add`): compose width polys into
  one border poly. Only pays off with adaptive sampling or 3D.
- **Adaptive Bézier sampling** (`CubicBezier::approximate_linear`, eps-based): a perf/quality
  optimization; our fixed interval + breakpoints is sufficient at current map sizes.
- **Arc-length LUT** for paramPoly3 (`CubicBezier` ctor): only needed for true distance-based
  sampling.
- **Road marks**, **lane predecessor/successor links**: on-demand (see Q1).

### Verified NON-issues (no action)
- **`pRange` default**: a review flagged this as a bug — it is not. Our code already defaults to
  `arcLength`; libOpenDRIVE/esmini default to `normalized`. It is moot for us because ORBIT writes
  `pRange="normalized"` explicitly on every paramPoly3 (and we handle that correctly). If aligning
  to the ecosystem default ever matters, confirm against the ASAM XSD before flipping it.
- **line / arc / poly3 geometry math**: confirmed equivalent to libOpenDRIVE's.
- **Lane assignment**: our shapely `STRtree` + `polygon.covers` handles arbitrary lane shapes;
  no need for libOpenDRIVE's analytic `t -> lane_id` border lookup.
