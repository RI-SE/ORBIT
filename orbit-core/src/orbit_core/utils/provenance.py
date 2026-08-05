"""Optional data provenance tracking via the dataprov library.

Provenance sidecar files are created alongside .orbit project files and exports
when the user enables the feature in Preferences and the dataprov package is installed.

File names are resolved from a configurable template stored in QSettings
(key ``provenance/name_template``, default ``{stem}{ext}.prov.json``).

Template variables (resolved against the target output file's path):
    {dir}  — parent directory of the output file
    {stem} — filename stem (without extension)
    {ext}  — file extension including the leading dot
    {name} — full filename (stem + ext)
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit_core.models.project import Project

DEFAULT_TEMPLATE = "{stem}{ext}.prov.json"
_ORBIT_SOURCE = "RISE Research Institutes of Sweden"


def is_dataprov_available() -> bool:
    """Return True if the dataprov package is importable."""
    return importlib.util.find_spec("dataprov") is not None


def prov_path_for(file_path: Path | str, template: str = DEFAULT_TEMPLATE) -> Path:
    """Resolve the provenance sidecar path from *file_path* and *template*.

    Template variables ``{dir}``, ``{stem}``, ``{ext}``, ``{name}`` are substituted
    from *file_path*. If *template* contains ``{dir}``, the result is used as-is;
    otherwise the resolved path is placed in the same directory as *file_path*.
    """
    p = Path(file_path)
    resolved = template.format(
        dir=str(p.parent),
        stem=p.stem,
        ext=p.suffix,
        name=p.name,
    )
    result = Path(resolved)
    # If the template didn't include {dir}, put it alongside the original file.
    if "{dir}" not in template and not result.is_absolute():
        result = p.parent / result
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def record_project_save(
    project: "Project",
    orbit_path: Path,
    start_time: datetime,
    template: str = DEFAULT_TEMPLATE,
) -> bool:
    """Create or update the provenance sidecar for an .orbit project file.

    Records the source image and any imported files as inputs.
    Returns True on success, False if dataprov is unavailable or an error occurs.
    """
    if not is_dataprov_available():
        return False

    try:
        from dataprov import ProvenanceChain

        prov_file = prov_path_for(orbit_path, template)
        ended_at = _now_iso()
        started_at = start_time.isoformat().replace("+00:00", "Z")

        initial_source = str(project.image_path) if project.image_path else str(orbit_path)

        chain = ProvenanceChain.load_or_create(
            str(prov_file),
            entity_id="orbit_project",
            initial_source=initial_source,
            description=f"ORBIT project: {project.map_name or orbit_path.stem}",
            tags=["orbit", "road-annotation", "opendrive"],
        )

        inputs: list[str] = []
        input_formats: list[str] = []

        if project.image_path:
            inputs.append(str(project.image_path))
            input_formats.append(_format_for(project.image_path))

        for src in getattr(project, "source_files", []):
            path = src.get("path", "")
            src_type = src.get("type", "")
            if path and path != "api":
                inputs.append(path)
                input_formats.append(_format_for(Path(path)))
            elif src_type == "osm_api":
                # API import – use URL placeholder
                inputs.append(src.get("path", "https://overpass-api.de/api/interpreter"))
                input_formats.append("XML")

        if not inputs:
            # Nothing useful to record
            inputs = [str(orbit_path)]
            input_formats = ["ORBIT"]

        chain.add(
            started_at=started_at,
            ended_at=ended_at,
            tool_name="orbit",
            tool_version=_orbit_version(),
            operation="road network annotation",
            inputs=inputs,
            input_formats=input_formats,
            outputs=[str(orbit_path)],
            output_formats=["ORBIT"],
            source=_ORBIT_SOURCE,
            capture_agent=True,
            capture_environment=True,
        )

        chain.save(str(prov_file))
        return True

    except Exception as exc:  # noqa: BLE001
        import sys
        print(f"Warning: provenance recording failed: {exc}", file=sys.stderr)
        return False


def record_export(
    output_path: Path,
    orbit_path: Path | None,
    operation: str,
    output_format: str,
    start_time: datetime,
    template: str = DEFAULT_TEMPLATE,
) -> bool:
    """Create a provenance sidecar for an exported file.

    Links to the .orbit project's own provenance chain when available.
    Returns True on success, False if dataprov is unavailable or an error occurs.
    """
    if not is_dataprov_available():
        return False

    try:
        from dataprov import ProvenanceChain

        prov_file = prov_path_for(output_path, template)
        ended_at = _now_iso()
        started_at = start_time.isoformat().replace("+00:00", "Z")

        inputs: list[str] = []
        input_formats: list[str] = []
        input_provenance_files: list[str | None] = []

        if orbit_path is not None:
            inputs.append(str(orbit_path))
            input_formats.append("ORBIT")
            orbit_prov = prov_path_for(orbit_path, template)
            input_provenance_files.append(str(orbit_prov) if orbit_prov.exists() else None)

        chain = ProvenanceChain.create(
            entity_id=f"orbit_{output_format.lower()}_export",
            initial_source=str(orbit_path) if orbit_path else str(output_path),
            description=f"ORBIT export: {output_path.name}",
            tags=["orbit", "export", output_format.lower()],
        )

        chain.add(
            started_at=started_at,
            ended_at=ended_at,
            tool_name="orbit",
            tool_version=_orbit_version(),
            operation=operation,
            inputs=inputs,
            input_formats=input_formats,
            outputs=[str(output_path)],
            output_formats=[output_format],
            input_provenance_files=input_provenance_files if any(input_provenance_files) else None,
            source=_ORBIT_SOURCE,
            capture_agent=True,
            capture_environment=True,
        )

        chain.save(str(prov_file))
        return True

    except Exception as exc:  # noqa: BLE001
        import sys
        print(f"Warning: provenance recording failed: {exc}", file=sys.stderr)
        return False


def _format_for(path: Path) -> str:
    """Return a short format label for a file extension."""
    return {
        ".jpg": "JPEG", ".jpeg": "JPEG",
        ".png": "PNG", ".tif": "TIFF", ".tiff": "TIFF",
        ".bmp": "BMP", ".orbit": "ORBIT", ".xodr": "XODR",
        ".osm": "OSM", ".json": "JSON",
    }.get(path.suffix.lower(), path.suffix.lstrip(".").upper() or "UNKNOWN")


def _orbit_version() -> str:
    try:
        from importlib.metadata import version
        return version("orbit")
    except Exception:
        return "unknown"
