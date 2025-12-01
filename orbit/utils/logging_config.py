"""Logging configuration for ORBIT application.

Provides centralized logging setup to replace scattered print statements.
"""

import logging
import sys
from typing import Optional


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

    # Configure root logger
    root_logger = logging.getLogger('orbit')
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
        name: Module name, typically __name__. Will be prefixed with 'orbit.'
              if not already.

    Returns:
        Logger instance for the module.

    Example:
        logger = get_logger(__name__)
        logger.debug("Detailed debug info")
        logger.info("General information")
        logger.warning("Warning message")
        logger.error("Error occurred")
    """
    # Ensure the logger is under the 'orbit' namespace
    if not name.startswith('orbit'):
        name = f'orbit.{name}'
    return logging.getLogger(name)
