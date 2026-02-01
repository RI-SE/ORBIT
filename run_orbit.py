#!/usr/bin/env python3
"""
ORBIT - OpenDrive Road Builder from Imagery Tool

A GUI application for annotating roads in aerial/satellite imagery
and exporting to ASAM OpenDrive format.

Usage:
    orbit [image_path] [--verbose] [--xodr_schema PATH]

    image_path: Optional path to image file to load on startup
"""

import sys
import argparse
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from orbit import __version__
from orbit.gui.main_window import MainWindow
from orbit.utils import setup_logging


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="ORBIT - OpenDrive Road Builder from Imagery Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  orbit                             Start with empty project
  orbit image.jpg                   Load image on startup
  orbit /path/to/aerial.jpg         Load image with full path
  orbit --verbose                   Enable debug logging
        """
    )

    parser.add_argument(
        'image',
        nargs='?',
        type=str,
        default=None,
        help='Optional path to image file to load on startup'
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'ORBIT {__version__}'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug output'
    )

    parser.add_argument(
        '--xodr_schema',
        type=str,
        default=None,
        metavar='PATH',
        help='Path to OpenDRIVE XSD schema file (OpenDRIVE_Core.xsd) for export validation. '
             'If not provided, schema validation is skipped during export.'
    )

    return parser.parse_args()


def main():
    """Main entry point for ORBIT application."""
    # Parse command line arguments
    args = parse_arguments()

    # Initialize logging early
    setup_logging(verbose=args.verbose)

    # Validate image path if provided
    image_path = None
    if args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"Error: Image file not found: {image_path}", file=sys.stderr)
            return 1
        if not image_path.is_file():
            print(f"Error: Path is not a file: {image_path}", file=sys.stderr)
            return 1

    # Validate schema path if provided
    xodr_schema_path = None
    if args.xodr_schema:
        xodr_schema_path = Path(args.xodr_schema)
        if not xodr_schema_path.exists():
            print(f"Error: Schema file not found: {xodr_schema_path}", file=sys.stderr)
            return 1
        if not xodr_schema_path.is_file():
            print(f"Error: Schema path is not a file: {xodr_schema_path}", file=sys.stderr)
            return 1
        xodr_schema_path = str(xodr_schema_path)

    # Enable high DPI scaling (must be set before creating QApplication)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("ORBIT")
    app.setOrganizationName("RISE Research Institutes of Sweden")

    # Create and show main window
    main_window = MainWindow(image_path=image_path, verbose=args.verbose, xodr_schema_path=xodr_schema_path)
    main_window.show()

    # Start event loop
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
