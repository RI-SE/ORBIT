#!/usr/bin/env python3
"""
Attach surveyed altitudes (and RTK SDs, point type) from a survey CSV to the control points of an ORBIT project.

Projects made before ORBIT stored altitudes (G8) have control points without them, and the CSV import re-places
points by clicking. This tool fills them in by point name, so the georef export can fit the camera model over
terrain and the OpenDRIVE export can write road elevation.

Only the control points' survey fields are changed; the rest of the .orbit file is written back as it was.

    uv run python tools/attach_altitudes.py project.orbit survey.csv            # report only
    uv run python tools/attach_altitudes.py project.orbit survey.csv --write    # update (backup: project.orbit.bak)
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from orbit_core.utils.control_point_csv import MAX_MATCH_DISTANCE_M, attach_survey_data, parse_csv_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Attach survey altitudes to an ORBIT project's control points")
    parser.add_argument("project", type=Path, help="ORBIT project file (.orbit)")
    parser.add_argument("csv", type=Path, help="Survey CSV (point name, latitude, longitude, altitude[, SDs])")
    parser.add_argument("--write", action="store_true", help="Update the project (default: only report)")
    parser.add_argument("--overwrite", action="store_true", help="Replace fields that are already set")
    parser.add_argument("--max-distance", type=float, default=MAX_MATCH_DISTANCE_M, metavar="M",
                        help=f"Reject name matches farther apart than this (default {MAX_MATCH_DISTANCE_M} m)")
    return parser


def print_report(report: dict, total: int) -> None:
    labels = {"updated": "updated", "unchanged": "already set / nothing to add", "unmatched": "no CSV point by name",
              "too_far": "name matches but position differs (rejected)", "duplicate": "name repeated in the CSV"}
    print(f"{total} control point(s):")
    for key, label in labels.items():
        if report[key]:
            print(f"  {len(report[key]):3d} {label}: {', '.join(report[key])}")


def main() -> int:
    args = build_parser().parse_args()
    survey, error = parse_csv_file(args.csv)
    if error:
        print(f"Error reading {args.csv}: {error}", file=sys.stderr)
        return 1
    data = json.loads(args.project.read_text(encoding="utf-8"))
    control_points = data.get("control_points") or []
    report = attach_survey_data(control_points, survey, overwrite=args.overwrite, max_distance_m=args.max_distance)
    print_report(report, len(control_points))
    if not args.write:
        print("Report only; run with --write to update the project.")
        return 0
    if report["updated"]:
        backup = args.project.with_name(args.project.name + ".bak")
        shutil.copy2(args.project, backup)
        args.project.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Updated {args.project} (backup: {backup.name})")
    else:
        print("Nothing to update.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
