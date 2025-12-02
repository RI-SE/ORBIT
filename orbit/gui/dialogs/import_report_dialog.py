"""
Dialog for displaying import results and statistics.

Reusable for both OSM and OpenDrive imports.
"""

from PyQt6.QtWidgets import (
    QHBoxLayout, QPushButton, QTextBrowser, QDialogButtonBox
)

from .base_dialog import BaseDialog


class ImportReportDialog(BaseDialog):
    """Dialog for displaying import report with statistics."""

    def __init__(self, title: str, report_html: str, parent=None):
        """
        Initialize import report dialog.

        Args:
            title: Dialog title (e.g., "OpenDrive Import Complete")
            report_html: HTML-formatted report content
            parent: Parent widget
        """
        super().__init__(title, parent, min_width=600, min_height=500)
        self.setModal(True)

        self.report_html = report_html
        self.setup_ui()
        self.load_properties()

    def setup_ui(self):
        """Create dialog UI."""
        # Report text browser
        self.report_browser = QTextBrowser()
        self.report_browser.setOpenExternalLinks(False)
        self.get_main_layout().addWidget(self.report_browser)

        # Close button (custom, not OK/Cancel)
        button_box = QDialogButtonBox()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        button_box.addButton(close_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.accepted.connect(self.accept)
        self.get_main_layout().addWidget(button_box)

    def load_properties(self):
        """Load report HTML into browser."""
        self.report_browser.setHtml(self.report_html)


def format_opendrive_import_result(result) -> str:
    """
    Format OpenDrive import result as HTML.

    Args:
        result: ImportResult from opendrive_importer

    Returns:
        HTML-formatted report string
    """
    # Determine success/failure icon
    if result.success:
        status_icon = "✓"
        status_color = "green"
        status_text = "Import Successful"
    else:
        status_icon = "✗"
        status_color = "red"
        status_text = "Import Failed"

    html = f"""
<h2 style="color: {status_color};">{status_icon} {status_text}</h2>
"""

    # Show error message if failed
    if not result.success and result.error_message:
        html += f"""
<p style="color: red;"><b>Error:</b> {result.error_message}</p>
"""
        return html

    # Import statistics
    html += """
<h3>Import Statistics</h3>
<table border="0" cellpadding="4" style="margin-left: 20px;">
"""

    stats = [
        ("Roads imported", result.roads_imported),
        ("Connecting roads imported", result.connecting_roads_imported),
        ("Polylines imported", result.polylines_imported),
        ("Junctions imported", result.junctions_imported),
        ("Signals imported", result.signals_imported),
        ("Objects imported", result.objects_imported),
        ("Elevation profiles", result.elevation_profiles_imported),
    ]

    if result.control_points_created > 0:
        stats.append(("Control points created", result.control_points_created))

    for label, count in stats:
        html += f"<tr><td><b>{label}:</b></td><td>{count}</td></tr>\n"

    html += "</table>\n"

    # Skipped/duplicate items
    if result.roads_skipped_duplicate > 0:
        html += f"""
<p style="margin-left: 20px; color: #666;">
<i>Skipped {result.roads_skipped_duplicate} duplicate road(s)</i>
</p>
"""

    # Transform mode info
    if result.transform_mode:
        html += f"""
<h3>Coordinate Transformation</h3>
<p style="margin-left: 20px;">
<b>Mode:</b> {result.transform_mode}
"""
        if result.scale_used:
            html += f"<br><b>Scale:</b> {result.scale_used:.2f} pixels/meter"

        html += "</p>\n"

    # Geometry conversions
    if result.geometry_conversions:
        html += """
<h3>Geometry Conversions</h3>
<p style="margin-left: 20px;">
The following geometry elements were converted to polylines:
</p>
<ul style="margin-left: 40px;">
"""
        # Show first 10 conversions
        for conversion in result.geometry_conversions[:10]:
            html += f"<li>{conversion}</li>\n"

        if len(result.geometry_conversions) > 10:
            remaining = len(result.geometry_conversions) - 10
            html += f"<li><i>... and {remaining} more</i></li>\n"

        html += "</ul>\n"

    # Unsupported features
    if result.features_skipped:
        html += """
<h3>Unsupported Features (Skipped)</h3>
<table border="0" cellpadding="4" style="margin-left: 20px;">
"""
        for feature, count in result.features_skipped.items():
            html += f"<tr><td><b>{feature}:</b></td><td>{count}</td></tr>\n"

        html += "</table>\n"

    # Warnings
    if result.warnings:
        html += """
<h3>Warnings</h3>
<ul style="margin-left: 20px; color: #cc6600;">
"""
        # Show first 20 warnings
        for warning in result.warnings[:20]:
            html += f"<li>{warning}</li>\n"

        if len(result.warnings) > 20:
            remaining = len(result.warnings) - 20
            html += f"<li><i>... and {remaining} more warnings</i></li>\n"

        html += "</ul>\n"

    return html


def show_opendrive_import_report(result, parent=None):
    """
    Show OpenDrive import report dialog.

    Args:
        result: ImportResult from opendrive_importer
        parent: Parent widget
    """
    html = format_opendrive_import_result(result)
    dialog = ImportReportDialog("OpenDrive Import Complete", html, parent)
    dialog.exec()
