# orbit-core

Headless road-network model, OpenStreetMap / OpenDRIVE import, and OpenDRIVE export —
the GUI-free half of [ORBIT](https://github.com/RI-SE/ORBIT).

Nothing here imports PyQt, and nothing requires imagery, so this can be used from a
script, a test, or a data pipeline. The ORBIT desktop application is a shell over it.

**MIT licensed**, unlike the ORBIT application itself (GPL-3.0, because of its PyQt6
dependency). See [LICENSE](LICENSE).

## Install

```bash
pip install "orbit-core @ git+https://github.com/RI-SE/ORBIT.git#subdirectory=orbit-core"
```

Extras, none of which the OSM → OpenDRIVE path needs:

| Extra | Pulls in | For |
|---|---|---|
| `imagery` | `opencv-python` | raster layout export, satellite tile fetching |
| `camera` | `geomag` | oblique-imagery camera model |
| `validation` | `xmlschema` | XSD validation of exported OpenDRIVE |
| `provenance` | `dataprov` | provenance metadata |

## Coordinates to a CARLA-ready map

```python
import orbit_core as oc

bbox = oc.bbox_from_center(57.6968, 11.9865, radius_m=150)
osm = oc.osm_data_from_overpass(bbox)
oc.opendrive_from_osm_data(osm, bbox, "korsvagen.xodr")
```

That writes OpenDRIVE 1.4 (`ExportOptions(carla_compat=True)`), which is what CARLA
reads. Pass `export_options=ExportOptions(carla_compat=False)` for 1.8.

## Working offline

Overpass is a shared public service and does fail. Fetching and converting are separate
calls so you can cache, and both sources produce the same `OSMData`:

```python
import json

try:
    raw = oc.fetch_osm_json(bbox)               # cache the response verbatim
    json.dump(raw, open("cache/area.json", "w"))
    osm = oc.osm_data_from_json(raw)
except oc.OverpassAPIError:
    osm = oc.osm_data_from_json(json.load(open("cache/area.json")))

oc.opendrive_from_osm_data(osm, bbox, "out.xodr")
```

A `.osm` XML file exported from JOSM or ORBIT works too, though it carries no bbox of
its own:

```python
osm = oc.osm_data_from_file("area.osm")
bbox = oc.bbox_of(osm)
```

Note the two are not equivalent for the same area: the Overpass query filters by detail
level, whereas a `.osm` export contains everything inside its bounding box.

## Layout

| Package | Contents |
|---|---|
| `orbit_core.models` | `Project`, `Road`, `Polyline`, `Junction`, `Lane`, signals, objects |
| `orbit_core.importers` | Overpass client, OSM and OpenDRIVE parsers, junction analysis |
| `orbit_core.export` | OpenDRIVE writer, curve fitting, lane/signal/object builders |
| `orbit_core.utils` | coordinate transforms, geometry helpers |

The functions re-exported from `orbit_core` are the supported API; the subpackages are
available but may change shape between releases.

## Related

- [`opendrive-map`](../opendrive-map/) — read-only OpenDRIVE lane geometry (MIT)
- [`orbit-georef`](../orbit-georef/) — pixel ↔ geographic transformation (MIT)
- [ORBIT](../) — the desktop application (GPL-3.0)

## Tests

```bash
pip install -e ".[dev,imagery,camera,validation]"
pytest
```
