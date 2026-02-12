# Example Projects

## SaroRound -- Roundabout

A roundabout captured from aerial imagery, demonstrating the full ORBIT workflow from OSM import to OpenDRIVE export.

### Files

**Imagery and control points:**

- `SaroRound_firstframe.png` -- aerial image used as the project base
- `SaroRound_coords_visualmarkers.csv` -- control points (pixel to lat/lon)
- `SaroRound_fig_visualmarkers.png` -- visualization of control point locations

**Project files (workflow stages):**

1. `SaroRound_osm.orbit` -- after importing roads from OpenStreetMap
2. `SaroRound_geo.orbit` -- after applying georeferencing via control points
3. `SaroRound_adjusted.orbit` -- after manual adjustment of road geometry
4. `SaroRound_adjusted_2lane.orbit` -- variant with 2-lane road configuration

**OpenDRIVE exports:**

- `SaroRound_adjusted.xodr` -- exported from the adjusted project
- `SaroRound_2lane.xodr` -- 2-lane variants

### How to open

```bash
# Open the aerial image in ORBIT
orbit examples/SaroRound/SaroRound_firstframe.png
```

Then use **File > Open Project** to load any of the `.orbit` files. Each file represents a different stage in the workflow, so you can inspect the progression from raw OSM import through georeferencing to the final adjusted result.
