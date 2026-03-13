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

## Tier 2 — Medium impact, medium effort

### 10. Extract `ProjectController` from MainWindow — DONE
- Created `orbit/gui/project_controller.py` (404 lines)
- MainWindow reduced from 4428 → 4062 lines
- Extracted to controller:
  - `get_current_scale()` — scale computation from georeferencing
  - `snap_connecting_road_endpoints()` — CR pixel endpoint snapping
  - `refresh_connecting_road_geo_path()` — CR geo-path regeneration
  - `align_all_junction_crs()` — junction CR lane alignment
  - `regenerate_affected_crs()` — full CR regeneration pipeline
  - `_regenerate_parampoly3_cr()` — single ParamPoly3D CR regeneration
  - `_snap_polyline_cr_endpoints()` — polyline CR endpoint snapping
  - `_align_affected_junction_crs()` — affected junction alignment
  - `link_roads()` / `unlink_roads()` — road link mutation logic
  - `build_batch_delete_info()` — batch delete info query
  - `get_contact_pos_heading()` — module-level utility function
- MainWindow delegates to controller; undo commands unchanged

### 11. Split remaining 200+ line functions — DONE
- `create_connecting_roads_from_patterns` (370→~35 lines, junction_analyzer.py) — DONE
  - `_generate_connection_path()`, `_add_cr_to_project_and_junction()`, `_add_lane_connections()`,
    `_create_bidirectional_cr()`, `_create_unidirectional_cr()`
- `create_roundabout_connectors` (309→~60 lines, roundabout_handler.py) — DONE
  - `_create_through_connector()`, `_create_entry_exit_connector()`
- `setup_ui` in georeference_dialog (260→~30 lines) — DONE
  - `_create_control_points_section()`, `_create_add_point_section()`,
    `_create_status_section()`, `_create_uncertainty_section()`,
    `_create_uncertainty_params_layout()`
- `offset_road_endpoints_from_junctions` (229→~70 lines, osm_to_orbit.py) — DONE
  - `_apply_endpoint_offset()`
- `create_roundabout_from_params` (215→~50 lines, roundabout_creator.py) — DONE
  - `_find_connection_indices()`, `_create_ring_segments()`,
    `_link_ring_segments()`, `_create_entry_junctions()`
- `_create_section_based_lanes` (215→~25 lines, lane_item.py) — DONE
  - `_is_inner_lane()`, `_cumulative_inner_offset()`, `_compute_lane_polygon()`,
    `_compute_explicit_boundary_polygon()`, `_compute_width_based_polygon()`,
    `_compute_polynomial_polygon()`, `_compute_variable_width_polygon()`,
    `_compute_constant_width_polygon()`, `_add_lane_scene_item()`
- `setup_ui` in properties_dialog (219→~30 lines) — DONE
  - `_create_basic_properties_section()`, `_create_centerline_section()`,
    `_create_road_links_section()`, `_create_lane_config_section()`
- `setup_ui` in lane_properties_dialog (210→~25 lines) — DONE
  - `_create_lane_properties_section()`, `_create_width_controls()`,
    `_create_access_controls()`, `_create_boundary_section()`
- `_migrate_uuid_ids` (204→~45 lines, project.py) — DONE
  - `_remap_entities()` (local), `_remap_all_cross_references()`

### 12. Consolidate scattered constants — DONE
- GUI: `DEFAULT_SCALE_M_PER_PX` (0.058) consolidated from 4 scattered files
  into `gui/constants.py`; `lane_item.py`, `connecting_road_item.py`,
  `lane_connection_dialog.py`, `project_controller.py` now import from there
- Import: Magic `3.5` lane width fallbacks in `junction_analyzer.py` and
  `opendrive_importer.py` named as `_DEFAULT_LANE_WIDTH` constants
- Note: `layout_mask_exporter.py` keeps its own inline 0.058 (computed fallback
  in export layer; importing gui constants would cross layers)

### 13. Replace `importlib` with standard late imports — SKIPPED
- `orbit.import` is a Python keyword; `importlib` is the correct approach

### 14. Add export builder tests — ALREADY DONE
- 466 export tests already exist across 12 test files
- `test_opendrive_writer.py` (65 tests), `test_lane_builder.py` (42),
  `test_signal_builder.py` (30), plus 9 more export test files

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
