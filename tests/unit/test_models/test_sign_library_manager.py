"""Tests for orbit.models.sign_library_manager module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from orbit.models.sign_library_manager import (
    SignLibraryManager,
    get_legacy_library_mapping,
    LEGACY_SIGNAL_TYPE_MAPPING
)
from orbit.models.sign_library import SignLibrary


class TestSignLibraryManagerSingleton:
    """Tests for singleton pattern."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_instance_returns_same_object(self):
        """Singleton returns same instance."""
        manager1 = SignLibraryManager.instance()
        manager2 = SignLibraryManager.instance()

        assert manager1 is manager2

    def test_reset_instance(self):
        """Reset creates new instance."""
        manager1 = SignLibraryManager.instance()
        SignLibraryManager.reset_instance()
        manager2 = SignLibraryManager.instance()

        assert manager1 is not manager2


class TestSignLibraryManagerInit:
    """Tests for manager initialization."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_init_sets_paths(self):
        """Initialization sets path attributes."""
        manager = SignLibraryManager()

        assert manager._app_signs_path is not None
        assert manager._user_signs_path is not None
        assert "signs" in str(manager._app_signs_path)
        assert ".orbit" in str(manager._user_signs_path)

    def test_init_empty_state(self):
        """Initialization creates empty state."""
        manager = SignLibraryManager()

        assert manager._libraries == {}
        assert manager._discovered_paths == {}
        assert manager._discovery_done is False

    def test_get_app_signs_path(self):
        """Get app signs path."""
        manager = SignLibraryManager()

        path = manager.get_app_signs_path()

        assert isinstance(path, Path)

    def test_get_user_signs_path(self):
        """Get user signs path."""
        manager = SignLibraryManager()

        path = manager.get_user_signs_path()

        assert isinstance(path, Path)
        assert ".orbit" in str(path)


class TestDiscoverLibraries:
    """Tests for discover_libraries method."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_discover_from_app_path(self, tmp_path):
        """Discovers libraries from app path."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        # Create a library directory with manifest
        lib_dir = tmp_path / "se"
        lib_dir.mkdir()
        manifest = lib_dir / "manifest.json"
        manifest.write_text(json.dumps({"library_id": "se", "name": "Swedish"}))

        result = manager.discover_libraries()

        assert "se" in result
        assert manager._discovery_done is True

    def test_discover_from_user_path(self, tmp_path):
        """Discovers libraries from user path."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path / "nonexistent"
        manager._user_signs_path = tmp_path

        # Create a library directory with manifest
        lib_dir = tmp_path / "custom"
        lib_dir.mkdir()
        manifest = lib_dir / "manifest.json"
        manifest.write_text(json.dumps({"library_id": "custom", "name": "Custom"}))

        result = manager.discover_libraries()

        assert "custom" in result

    def test_user_library_overrides_app(self, tmp_path):
        """User library with same ID overrides app library."""
        manager = SignLibraryManager()
        app_path = tmp_path / "app"
        user_path = tmp_path / "user"
        app_path.mkdir()
        user_path.mkdir()
        manager._app_signs_path = app_path
        manager._user_signs_path = user_path

        # Create same library in both locations
        app_lib = app_path / "se"
        app_lib.mkdir()
        (app_lib / "manifest.json").write_text(json.dumps({"name": "App Swedish"}))

        user_lib = user_path / "se"
        user_lib.mkdir()
        (user_lib / "manifest.json").write_text(json.dumps({"name": "User Swedish"}))

        manager.discover_libraries()

        # User path should be used
        assert manager._discovered_paths["se"] == user_lib / "manifest.json"

    def test_skip_directories_without_manifest(self, tmp_path):
        """Skips directories without manifest.json."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        # Create a directory without manifest
        (tmp_path / "no_manifest").mkdir()
        # Create a directory with manifest
        lib_dir = tmp_path / "valid"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text("{}")

        result = manager.discover_libraries()

        assert "valid" in result
        assert "no_manifest" not in result

    def test_cached_discovery(self, tmp_path):
        """Discovery is cached."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        # First discovery
        manager.discover_libraries()
        assert manager._discovery_done is True

        # Add new library after discovery
        lib_dir = tmp_path / "new_lib"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text("{}")

        # Second discovery should use cache
        result = manager.discover_libraries()
        assert "new_lib" not in result

    def test_force_rediscovery(self, tmp_path):
        """Force parameter triggers rediscovery."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        # First discovery
        manager.discover_libraries()

        # Add new library after discovery
        lib_dir = tmp_path / "new_lib"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text("{}")

        # Force rediscovery
        result = manager.discover_libraries(force=True)
        assert "new_lib" in result


class TestLoadLibrary:
    """Tests for load_library method."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_load_valid_library(self, tmp_path):
        """Load a valid library."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        # Create library with valid manifest
        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        manifest = lib_dir / "manifest.json"
        manifest.write_text(json.dumps({
            "library_id": "test",
            "name": "Test Library",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        manager.discover_libraries()
        library = manager.load_library("test")

        assert library is not None
        assert library.name == "Test Library"

    def test_load_caches_library(self, tmp_path):
        """Loaded library is cached."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "test",
            "name": "Test",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        manager.discover_libraries()
        library1 = manager.load_library("test")
        library2 = manager.load_library("test")

        assert library1 is library2

    def test_load_unknown_library(self, tmp_path):
        """Loading unknown library returns None."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        manager.discover_libraries()
        library = manager.load_library("nonexistent")

        assert library is None

    def test_load_triggers_discovery(self, tmp_path):
        """Loading triggers discovery if not done."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "test",
            "name": "Test",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        assert manager._discovery_done is False
        manager.load_library("test")
        assert manager._discovery_done is True


class TestGetLibrary:
    """Tests for get_library method."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_get_cached_library(self, tmp_path):
        """Get returns cached library."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "test",
            "name": "Test",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        manager.discover_libraries()
        manager.load_library("test")
        library = manager.get_library("test")

        assert library is not None
        assert library in manager._libraries.values()

    def test_get_loads_if_not_cached(self, tmp_path):
        """Get loads library if not cached."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "test",
            "name": "Test",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        manager.discover_libraries()
        # Don't explicitly load, just get
        library = manager.get_library("test")

        assert library is not None


class TestGetEnabledLibraries:
    """Tests for get_enabled_libraries method."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_get_enabled_libraries(self, tmp_path):
        """Get multiple enabled libraries."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        # Create two libraries
        for lib_id in ["lib1", "lib2"]:
            lib_dir = tmp_path / lib_id
            lib_dir.mkdir()
            (lib_dir / "manifest.json").write_text(json.dumps({
                "library_id": lib_id,
                "name": f"Library {lib_id}",
                "version": "1.0.0",
                "country_code": "XX",
                "description": "",
                "categories": [],
                "signs": []
            }))

        manager.discover_libraries()
        libraries = manager.get_enabled_libraries(["lib1", "lib2"])

        assert len(libraries) == 2

    def test_get_enabled_skips_missing(self, tmp_path):
        """Skips missing libraries."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "lib1"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "lib1",
            "name": "Library 1",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        manager.discover_libraries()
        libraries = manager.get_enabled_libraries(["lib1", "missing"])

        assert len(libraries) == 1


class TestGetSignDefinition:
    """Tests for get_sign_definition method."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_get_sign_definition(self, tmp_path):
        """Get sign definition from library."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "test",
            "name": "Test",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [{"id": "A", "name": "Category A"}],
            "signs": [{
                "id": "A1",
                "name": "Sign A1",
                "category": "A",
                "identifiers": {}
            }]
        }))

        manager.discover_libraries()
        sign = manager.get_sign_definition("test", "A1")

        assert sign is not None
        assert sign.name == "Sign A1"

    def test_get_sign_definition_unknown_library(self, tmp_path):
        """Returns None for unknown library."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        manager.discover_libraries()
        sign = manager.get_sign_definition("unknown", "A1")

        assert sign is None

    def test_get_sign_definition_unknown_sign(self, tmp_path):
        """Returns None for unknown sign."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "test",
            "name": "Test",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        manager.discover_libraries()
        sign = manager.get_sign_definition("test", "unknown")

        assert sign is None


class TestGetAllAvailableLibrariesInfo:
    """Tests for get_all_available_libraries_info method."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_get_info_for_loaded_library(self, tmp_path):
        """Get info uses loaded library name."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "library_id": "test",
            "name": "Test Library",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }))

        manager.discover_libraries()
        manager.load_library("test")
        info = manager.get_all_available_libraries_info()

        assert len(info) == 1
        assert info[0]["id"] == "test"
        assert info[0]["name"] == "Test Library"

    def test_get_info_without_loading(self, tmp_path):
        """Get info reads manifest for unloaded libraries."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "test"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text(json.dumps({
            "name": "Test Library From Manifest"
        }))

        info = manager.get_all_available_libraries_info()

        assert len(info) == 1
        assert info[0]["name"] == "Test Library From Manifest"

    def test_get_info_falls_back_to_id(self, tmp_path):
        """Falls back to library ID if name not in manifest."""
        manager = SignLibraryManager()
        manager._app_signs_path = tmp_path
        manager._user_signs_path = tmp_path / "nonexistent"

        lib_dir = tmp_path / "mylib"
        lib_dir.mkdir()
        (lib_dir / "manifest.json").write_text("{}")  # No name field

        info = manager.get_all_available_libraries_info()

        assert len(info) == 1
        assert info[0]["name"] == "mylib"


class TestEnsureUserSignsDirectory:
    """Tests for ensure_user_signs_directory method."""

    def teardown_method(self):
        """Reset singleton after each test."""
        SignLibraryManager.reset_instance()

    def test_creates_directory(self, tmp_path):
        """Creates user signs directory if not exists."""
        manager = SignLibraryManager()
        user_path = tmp_path / "user_signs"
        manager._user_signs_path = user_path

        assert not user_path.exists()

        result = manager.ensure_user_signs_directory()

        assert result == user_path
        assert user_path.exists()

    def test_returns_existing_directory(self, tmp_path):
        """Returns path if directory already exists."""
        manager = SignLibraryManager()
        user_path = tmp_path / "user_signs"
        user_path.mkdir(parents=True)
        manager._user_signs_path = user_path

        result = manager.ensure_user_signs_directory()

        assert result == user_path


class TestLegacyMapping:
    """Tests for legacy signal type mapping."""

    def test_mapping_exists_for_common_types(self):
        """Mapping exists for common signal types."""
        assert "give_way" in LEGACY_SIGNAL_TYPE_MAPPING
        assert "stop" in LEGACY_SIGNAL_TYPE_MAPPING
        assert "speed_limit" in LEGACY_SIGNAL_TYPE_MAPPING
        assert "no_entry" in LEGACY_SIGNAL_TYPE_MAPPING

    def test_get_legacy_mapping_simple(self):
        """Get mapping for simple sign type."""
        lib_id, sign_id = get_legacy_library_mapping("give_way")

        assert lib_id == "se"
        assert sign_id == "B1"

    def test_get_legacy_mapping_stop(self):
        """Get mapping for stop sign."""
        lib_id, sign_id = get_legacy_library_mapping("stop")

        assert lib_id == "se"
        assert sign_id == "B2"

    def test_get_legacy_mapping_template_with_value(self):
        """Get mapping for template sign with value."""
        lib_id, sign_id = get_legacy_library_mapping("speed_limit", value=50)

        assert lib_id == "se"
        assert sign_id == "C31-50"

    def test_get_legacy_mapping_template_without_value(self):
        """Get mapping for template sign without value."""
        lib_id, sign_id = get_legacy_library_mapping("speed_limit")

        assert lib_id == "se"
        assert sign_id == "C31"

    def test_get_legacy_mapping_end_speed_limit(self):
        """Get mapping for end of speed limit."""
        lib_id, sign_id = get_legacy_library_mapping("end_of_speed_limit", value=70)

        assert lib_id == "se"
        assert sign_id == "C32-70"

    def test_get_legacy_mapping_unknown(self):
        """Get mapping for unknown type returns None."""
        lib_id, sign_id = get_legacy_library_mapping("unknown_type")

        assert lib_id is None
        assert sign_id is None
