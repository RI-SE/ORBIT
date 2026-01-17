"""Tests for orbit.utils.logging_config module."""

import logging
import pytest
from pathlib import Path

from orbit.utils.logging_config import setup_logging, get_logger


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_with_orbit_prefix(self):
        """Logger with orbit prefix keeps the name."""
        logger = get_logger('orbit.models.project')

        assert logger.name == 'orbit.models.project'
        assert isinstance(logger, logging.Logger)

    def test_get_logger_without_orbit_prefix(self):
        """Logger without orbit prefix gets it added."""
        logger = get_logger('my_module')

        assert logger.name == 'orbit.my_module'

    def test_get_logger_with_dunder_name(self):
        """Logger with __name__ pattern works correctly."""
        # Simulate typical usage: get_logger(__name__)
        logger = get_logger('models.road')

        assert logger.name == 'orbit.models.road'

    def test_get_logger_returns_same_logger(self):
        """Same logger is returned for same name."""
        logger1 = get_logger('orbit.test.same')
        logger2 = get_logger('orbit.test.same')

        assert logger1 is logger2

    def test_get_logger_different_names(self):
        """Different names return different loggers."""
        logger1 = get_logger('orbit.test.one')
        logger2 = get_logger('orbit.test.two')

        assert logger1 is not logger2
        assert logger1.name != logger2.name


class TestSetupLogging:
    """Tests for setup_logging function."""

    def setup_method(self):
        """Clear orbit logger handlers before each test."""
        orbit_logger = logging.getLogger('orbit')
        orbit_logger.handlers.clear()

    def teardown_method(self):
        """Clean up after each test."""
        orbit_logger = logging.getLogger('orbit')
        orbit_logger.handlers.clear()

    def test_setup_logging_default(self):
        """Default setup creates INFO level console handler."""
        setup_logging()

        orbit_logger = logging.getLogger('orbit')

        assert orbit_logger.level == logging.INFO
        assert len(orbit_logger.handlers) == 1
        assert isinstance(orbit_logger.handlers[0], logging.StreamHandler)

    def test_setup_logging_verbose(self):
        """Verbose mode sets DEBUG level."""
        setup_logging(verbose=True)

        orbit_logger = logging.getLogger('orbit')

        assert orbit_logger.level == logging.DEBUG
        assert orbit_logger.handlers[0].level == logging.DEBUG

    def test_setup_logging_with_file(self, tmp_path):
        """Setup with log file creates file handler."""
        log_file = tmp_path / "test.log"
        setup_logging(log_file=str(log_file))

        orbit_logger = logging.getLogger('orbit')

        # Should have 2 handlers: console and file
        assert len(orbit_logger.handlers) == 2

        # Find the file handler
        file_handlers = [h for h in orbit_logger.handlers
                        if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

        # File handler should be DEBUG level (always log everything to file)
        assert file_handlers[0].level == logging.DEBUG

    def test_setup_logging_file_created(self, tmp_path):
        """Log file is created when specified."""
        log_file = tmp_path / "orbit.log"
        setup_logging(log_file=str(log_file))

        # Log a message
        logger = get_logger('test')
        logger.info("Test message")

        # File should exist
        assert log_file.exists()

    def test_setup_logging_file_contains_messages(self, tmp_path):
        """Log file contains logged messages."""
        log_file = tmp_path / "orbit.log"
        setup_logging(verbose=True, log_file=str(log_file))

        # Log messages at different levels
        logger = get_logger('test.logging')
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        # Flush handlers
        for handler in logging.getLogger('orbit').handlers:
            handler.flush()

        content = log_file.read_text()

        assert "Debug message" in content
        assert "Info message" in content
        assert "Warning message" in content
        assert "Error message" in content

    def test_setup_logging_clears_existing_handlers(self):
        """Re-calling setup_logging clears existing handlers."""
        setup_logging()
        setup_logging()
        setup_logging()

        orbit_logger = logging.getLogger('orbit')

        # Should only have 1 handler, not 3
        assert len(orbit_logger.handlers) == 1

    def test_setup_logging_formatter(self):
        """Setup creates correct formatter."""
        setup_logging()

        orbit_logger = logging.getLogger('orbit')
        handler = orbit_logger.handlers[0]

        # Check formatter format includes expected parts
        assert handler.formatter is not None
        # The format is '%(name)s - %(levelname)s - %(message)s'
        record = logging.LogRecord(
            name='orbit.test',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg='Test message',
            args=(),
            exc_info=None
        )
        formatted = handler.formatter.format(record)

        assert 'orbit.test' in formatted
        assert 'INFO' in formatted
        assert 'Test message' in formatted


class TestLoggingIntegration:
    """Integration tests for logging functionality."""

    def setup_method(self):
        """Clear orbit logger handlers before each test."""
        orbit_logger = logging.getLogger('orbit')
        orbit_logger.handlers.clear()

    def teardown_method(self):
        """Clean up after each test."""
        orbit_logger = logging.getLogger('orbit')
        orbit_logger.handlers.clear()

    def test_child_logger_inherits_level(self):
        """Child loggers inherit parent log level."""
        setup_logging(verbose=True)

        parent_logger = logging.getLogger('orbit')
        child_logger = get_logger('orbit.models')

        # Child should have effective level from parent
        assert child_logger.getEffectiveLevel() == logging.DEBUG

    def test_logging_with_different_modules(self, tmp_path):
        """Multiple module loggers write to same file."""
        log_file = tmp_path / "multi.log"
        setup_logging(verbose=True, log_file=str(log_file))

        logger1 = get_logger('module1')
        logger2 = get_logger('module2')

        logger1.info("Message from module1")
        logger2.info("Message from module2")

        # Flush
        for handler in logging.getLogger('orbit').handlers:
            handler.flush()

        content = log_file.read_text()

        assert "orbit.module1" in content
        assert "orbit.module2" in content
        assert "Message from module1" in content
        assert "Message from module2" in content

    def test_info_not_logged_in_non_verbose(self, tmp_path, capfd):
        """DEBUG messages not logged when verbose=False."""
        setup_logging(verbose=False)

        logger = get_logger('test')
        logger.debug("Debug message should not appear")
        logger.info("Info message should appear")

        # Capture stderr output
        captured = capfd.readouterr()

        assert "Debug message should not appear" not in captured.err
        assert "Info message should appear" in captured.err

    def test_all_levels_logged_in_verbose(self, capfd):
        """All levels logged when verbose=True."""
        setup_logging(verbose=True)

        logger = get_logger('test.verbose')
        logger.debug("Debug")
        logger.info("Info")
        logger.warning("Warning")
        logger.error("Error")

        captured = capfd.readouterr()

        assert "Debug" in captured.err
        assert "Info" in captured.err
        assert "Warning" in captured.err
        assert "Error" in captured.err
