"""Logging configuration for ORBIT application.

Provides centralized logging setup to replace scattered print statements.
"""

import logging
import sys
from typing import Optional

#: Logger namespaces owned by the toolchain: the headless core and the GUI app.
LOGGER_NAMESPACES = ('orbit_core', 'orbit')
DEFAULT_NAMESPACE = 'orbit_core'


def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """Configure logging for the ORBIT application.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
        log_file: Optional path to write logs to a file.
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        '%(name)s - %(levelname)s - %(message)s'
    )

    # `orbit_core` is a sibling of `orbit` in the logging hierarchy, not a child,
    # so both namespaces must be configured for either to be affected.
    for namespace in LOGGER_NAMESPACES:
        root_logger = logging.getLogger(namespace)
        root_logger.setLevel(level)

        # Clear existing handlers to avoid duplicates on re-initialization
        root_logger.handlers.clear()

        # Console handler
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # Optional file handler
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)  # Always log everything to file
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the specified module.

    Args:
        name: Module name, typically __name__. Prefixed with 'orbit_core.' unless
              it already sits under one of LOGGER_NAMESPACES.

    Returns:
        Logger instance for the module.

    Example:
        logger = get_logger(__name__)
        logger.debug("Detailed debug info")
        logger.info("General information")
        logger.warning("Warning message")
        logger.error("Error occurred")
    """
    # Keep every logger under a namespace setup_logging actually configures.
    if not any(name == ns or name.startswith(f'{ns}.') for ns in LOGGER_NAMESPACES):
        name = f'{DEFAULT_NAMESPACE}.{name}'
    return logging.getLogger(name)
