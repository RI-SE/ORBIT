# Refactoring Roadmap & Progress

## Tier 1 — High impact, moderate effort

### 1. Split `mousePressEvent` (image_view.py) — DONE
- **Before**: 433 lines, giant switch on interaction mode
- **After**: 10-line dispatcher + 7 focused methods:
  - `_handle_left_press()` — dispatches by mode (draw/junction/signal/object/parking/pick/select)
  - `_handle_select_mode_press()` — Alt+area-select, Ctrl+insert, drag, selection
  - `_handle_ctrl_click_insert()` — Ctrl+click point insertion on segments
  - `_insert_polyline_point()` — polyline point insertion with metadata
  - `_try_start_drag()` — drag detection for junctions, objects, polylines, CRs
  - `_handle_click_selection()` — entity hit-testing
  - `_deselect_all()` — DRY deselect pattern (was duplicated 5×)
  - `_handle_right_press()` — right-button dispatch
  - `_handle_right_click_context_menu()` — context menus for signals/objects/polylines/CRs

### 2. Split `create_road_from_osm` (osm_to_orbit.py) — DONE
- **Before**: 311 lines mixing path/road creation, lane config, surface parsing
- **After**: Orchestrator + 8 focused functions:
  - `_create_path_road()` — bicycle/pedestrian path creation
  - `_create_normal_road()` — standard highway road creation
  - `_resolve_lane_width()` — lane width from OSM tags
  - `_apply_speed_limit()` — maxspeed tag parsing
  - `_parse_turn_lane_tags()` — turn:lanes parsing
  - `_resolve_surface_material()` — surface/smoothness tag parsing
  - `_build_lane_section()` — lane section construction
  - `_add_oneway_lanes()` / `_add_twoway_lanes()` — lane creation

### 3. Split `_create_connecting_road` (opendrive_writer.py) — DONE
- **Before**: 249 lines mixing geometry computation, XML construction
- **After**: Orchestrator + 5 focused methods:
  - `_compute_parampoly3_geometry()` — ParamPoly3D curve computation
  - `_resolve_cr_heading()` — heading from stored/fallback
  - `_override_with_road_heading()` — C1 continuity heading override
  - `_build_cr_road_xml()` — XML element construction

### 4. Split `split_road_at_point` (project.py) — DONE
- **Before**: 215 lines
- **After**: Orchestrator + 3 focused methods:
  - `_split_centerline()` — split centerline polyline with all per-point metadata
  - `_split_boundaries()` — split boundary polylines at s-coordinate
  - `_generate_split_names()` — segment naming logic

### 5. Split `_create_road` (opendrive_writer.py) — DONE
- **Before**: 224 lines
- **After**: Extracted `_build_road_link_xml()` and `_build_surface_crg_xml()`

### 6. Split `create_actions` (main_window.py) — DONE
- **Before**: 221 lines sequential action creation
- **After**: 5-line dispatcher + group methods:
  - `_create_file_actions()`
  - `_create_edit_actions()`
  - `_create_view_actions()`
  - `_create_tools_actions()`
  - `_create_help_actions()`

### 7. Split `import_osm_data` (main_window.py) — DONE
- **Before**: 226 lines mixing dialog setup, import execution, result handling
- **After**: Orchestrator + 2 methods:
  - `_setup_osm_import()` — bbox/transformer/dialog setup
  - `_process_osm_import_result()` — success/error message handling

### 8. Split `regenerate_affected_connecting_roads` (main_window.py) — DONE
- **Before**: 200 lines mixing ParamPoly3D regen, polyline snapping, lane alignment
- **After**: Orchestrator + 4 methods:
  - `_regenerate_parampoly3_cr()` — single CR curve regeneration
  - `_get_contact_pos_heading()` — endpoint position/heading extraction
  - `_snap_polyline_cr_endpoints()` — polyline CR endpoint snapping
  - `_align_affected_junction_crs()` — lane alignment application

### 9. Split `_import_connecting_road` (opendrive_importer.py) — DONE
- **Before**: 228 lines
- **After**: Extracted 3 methods:
  - `_parse_cr_lane_counts()` — lane count/width from ODR sections
  - `_build_cr_geometry_kwargs()` — ParamPoly3D geometry kwargs
  - `_import_cr_lane_connections()` — lane connection import

---

## Tier 2 — Medium impact, medium effort (TODO)

### 10. Extract `ProjectController` from MainWindow
- Decouple business logic (add/remove road, split, junction ops) from UI
- Highest-value god-object extraction

### 11. Split remaining 200+ line functions
- `create_connecting_roads_from_patterns` (370 lines, junction_analyzer.py)
- `create_roundabout_connectors` (309 lines, roundabout_handler.py)
- `setup_ui` in georeference_dialog (260 lines)
- `offset_road_endpoints_from_junctions` (229 lines, osm_to_orbit.py)
- `create_roundabout_from_params` (215 lines, roundabout_creator.py)
- `_create_section_based_lanes` (215 lines, lane_item.py)
- `setup_ui` in properties_dialog (219 lines)
- `setup_ui` in lane_properties_dialog (210 lines)
- `_migrate_uuid_ids` (204 lines, project.py)

### 12. Consolidate scattered constants
- GUI constants into `gui/constants.py`
- Import defaults into `import/defaults.py`

### 13. Replace `importlib` with standard late imports
- `import_osm_data` and `import_opendrive_file` in main_window.py

### 14. Add export builder tests
- `opendrive_writer.py` — XML generation
- `lane_builder.py`, `signal_builder.py` — pure builders

---

## Tier 3 — Nice to have (TODO)

### 15. Extract `GraphicsItemManager` from ImageView
### 16. Split large test files by domain class
### 17. Add `ExportOptions` dataclass to reduce parameter count
### 18. Extract migration logic from `Project.from_dict()` if it grows

---

## Verification checklist (for any refactoring step)
1. `uv run pytest tests/` — all 2416 tests pass
2. `uv run ruff check orbit/` — no lint errors
3. Manual smoke test: open project, edit road, export OpenDRIVE
