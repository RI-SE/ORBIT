"""Tests for orbit.models.sign_library module."""

import json

import pytest

from orbit.models.sign_library import SignCategory, SignDefinition, SignLibrary


class TestSignDefinition:
    """Tests for SignDefinition dataclass."""

    def test_basic_creation(self):
        """Create sign definition with required fields."""
        sign = SignDefinition(
            id="B1",
            name="Give Way",
            category_id="B",
            library_id="se"
        )

        assert sign.id == "B1"
        assert sign.name == "Give Way"
        assert sign.category_id == "B"
        assert sign.library_id == "se"

    def test_default_values(self):
        """Default values are set correctly."""
        sign = SignDefinition(
            id="B1",
            name="Give Way",
            category_id="B",
            library_id="se"
        )

        assert sign.image_filename is None
        assert sign.default_width == 0.6
        assert sign.default_height == 0.6
        assert sign.opendrive_type == "-1"
        assert sign.opendrive_subtype == "-1"
        assert sign.is_template is False
        assert sign.template_value is None

    def test_custom_values(self):
        """Custom values override defaults."""
        sign = SignDefinition(
            id="C31-50",
            name="Speed Limit",
            category_id="C",
            library_id="se",
            image_filename="C31_50.png",
            default_width=0.8,
            default_height=0.8,
            opendrive_type="274",
            opendrive_subtype="50",
            is_template=True,
            template_value=50,
            value_unit="km/h"
        )

        assert sign.image_filename == "C31_50.png"
        assert sign.default_width == 0.8
        assert sign.opendrive_type == "274"
        assert sign.opendrive_subtype == "50"
        assert sign.is_template is True
        assert sign.template_value == 50
        assert sign.value_unit == "km/h"

    def test_get_display_name_simple(self):
        """Display name for non-template sign."""
        sign = SignDefinition(
            id="B1",
            name="Give Way",
            category_id="B",
            library_id="se"
        )

        assert sign.get_display_name() == "Give Way"

    def test_get_display_name_template(self):
        """Display name for template sign includes value."""
        sign = SignDefinition(
            id="C31-50",
            name="Speed Limit",
            category_id="C",
            library_id="se",
            is_template=True,
            template_value=50
        )

        assert sign.get_display_name() == "Speed Limit 50"

    def test_get_display_name_template_no_value(self):
        """Display name for template sign without value."""
        sign = SignDefinition(
            id="C31",
            name="Speed Limit",
            category_id="C",
            library_id="se",
            is_template=True,
            template_value=None
        )

        assert sign.get_display_name() == "Speed Limit"


class TestSignCategory:
    """Tests for SignCategory dataclass."""

    def test_basic_creation(self):
        """Create sign category."""
        category = SignCategory(
            id="B",
            name="Priority Signs",
            description="Skyltar for foretradesratt",
            library_id="se"
        )

        assert category.id == "B"
        assert category.name == "Priority Signs"
        assert category.description == "Skyltar for foretradesratt"
        assert category.library_id == "se"


class TestSignLibrary:
    """Tests for SignLibrary dataclass."""

    @pytest.fixture
    def sample_categories(self):
        """Sample categories."""
        return [
            SignCategory(id="A", name="Warning Signs", description="", library_id="se"),
            SignCategory(id="B", name="Priority Signs", description="", library_id="se"),
        ]

    @pytest.fixture
    def sample_signs(self):
        """Sample signs."""
        return [
            SignDefinition(id="A1", name="Curve", category_id="A", library_id="se"),
            SignDefinition(id="A2", name="S-Curve", category_id="A", library_id="se"),
            SignDefinition(id="B1", name="Give Way", category_id="B", library_id="se"),
        ]

    @pytest.fixture
    def sample_library(self, sample_categories, sample_signs, tmp_path):
        """Sample library."""
        return SignLibrary(
            id="se",
            name="Swedish Road Signs",
            version="1.0.0",
            country_code="SE",
            description="Swedish traffic signs",
            base_path=tmp_path,
            categories=sample_categories,
            signs=sample_signs
        )

    def test_basic_creation(self, tmp_path):
        """Create library with required fields."""
        library = SignLibrary(
            id="se",
            name="Swedish Road Signs",
            version="1.0.0",
            country_code="SE",
            description="Swedish traffic signs",
            base_path=tmp_path
        )

        assert library.id == "se"
        assert library.name == "Swedish Road Signs"
        assert library.version == "1.0.0"
        assert library.country_code == "SE"

    def test_caches_built_on_init(self, sample_library):
        """Caches are built during initialization."""
        assert "A1" in sample_library._signs_by_id
        assert "B1" in sample_library._signs_by_id
        assert "A" in sample_library._signs_by_category
        assert "B" in sample_library._signs_by_category

    def test_get_sign_found(self, sample_library):
        """Get sign by ID."""
        sign = sample_library.get_sign("B1")

        assert sign is not None
        assert sign.name == "Give Way"

    def test_get_sign_not_found(self, sample_library):
        """Get sign returns None for unknown ID."""
        sign = sample_library.get_sign("unknown")

        assert sign is None

    def test_get_signs_by_category(self, sample_library):
        """Get signs by category."""
        signs = sample_library.get_signs_by_category("A")

        assert len(signs) == 2
        assert all(s.category_id == "A" for s in signs)

    def test_get_signs_by_category_not_found(self, sample_library):
        """Get signs by unknown category returns empty list."""
        signs = sample_library.get_signs_by_category("unknown")

        assert signs == []

    def test_get_category_found(self, sample_library):
        """Get category by ID."""
        category = sample_library.get_category("B")

        assert category is not None
        assert category.name == "Priority Signs"

    def test_get_category_not_found(self, sample_library):
        """Get category returns None for unknown ID."""
        category = sample_library.get_category("unknown")

        assert category is None

    def test_get_sign_image_path_no_filename(self, sample_library):
        """Image path returns None when no filename."""
        sign = SignDefinition(
            id="test", name="Test", category_id="A", library_id="se",
            image_filename=None
        )

        result = sample_library.get_sign_image_path(sign)

        assert result is None

    def test_get_sign_image_path_not_exists(self, sample_library):
        """Image path returns None when file doesn't exist."""
        sign = SignDefinition(
            id="test", name="Test", category_id="A", library_id="se",
            image_filename="nonexistent.png"
        )

        result = sample_library.get_sign_image_path(sign)

        assert result is None

    def test_get_sign_image_path_exists(self, sample_library, tmp_path):
        """Image path returns path when file exists."""
        # Create the image file
        image_file = tmp_path / "test_sign.png"
        image_file.write_bytes(b"PNG")

        sign = SignDefinition(
            id="test", name="Test", category_id="A", library_id="se",
            image_filename="test_sign.png"
        )

        result = sample_library.get_sign_image_path(sign)

        assert result is not None
        assert result == image_file


class TestSignLibraryFromManifest:
    """Tests for SignLibrary.from_manifest class method."""

    @pytest.fixture
    def sample_manifest(self):
        """Sample manifest data."""
        return {
            "library_id": "se",
            "name": "Swedish Road Signs",
            "version": "1.0.0",
            "country_code": "SE",
            "description": "Swedish traffic signs",
            "license": "CC-BY-SA",
            "source": "Transportstyrelsen",
            "categories": [
                {"id": "A", "name": "Warning Signs", "description": "Varningsskyltar"},
                {"id": "B", "name": "Priority Signs", "description": "Foretradesregler"}
            ],
            "signs": [
                {
                    "id": "A1",
                    "name": "Curve Right",
                    "category": "A",
                    "image": "A1.png",
                    "default_width": 0.6,
                    "default_height": 0.6,
                    "identifiers": {
                        "opendrive": {"type": "103", "subtype": "10"},
                        "opendrive_de": {"type": "103", "subtype": "10"},
                        "country": "A1",
                        "osm": "SE:A1"
                    }
                },
                {
                    "id": "B1",
                    "name": "Give Way",
                    "category": "B",
                    "image": "B1.png",
                    "identifiers": {
                        "opendrive": {"type": "B", "subtype": "1"},
                        "country": "B1",
                        "osm": "SE:B1"
                    }
                }
            ]
        }

    def test_load_manifest(self, sample_manifest, tmp_path):
        """Load library from manifest file."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(sample_manifest))

        library = SignLibrary.from_manifest(manifest_path)

        assert library is not None
        assert library.id == "se"
        assert library.name == "Swedish Road Signs"
        assert library.version == "1.0.0"
        assert library.country_code == "SE"
        assert library.license == "CC-BY-SA"
        assert library.source == "Transportstyrelsen"

    def test_load_manifest_categories(self, sample_manifest, tmp_path):
        """Manifest categories are loaded."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(sample_manifest))

        library = SignLibrary.from_manifest(manifest_path)

        assert len(library.categories) == 2
        assert library.categories[0].id == "A"
        assert library.categories[0].name == "Warning Signs"

    def test_load_manifest_signs(self, sample_manifest, tmp_path):
        """Manifest signs are loaded."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(sample_manifest))

        library = SignLibrary.from_manifest(manifest_path)

        assert len(library.signs) == 2
        sign = library.get_sign("A1")
        assert sign is not None
        assert sign.name == "Curve Right"
        assert sign.opendrive_type == "103"
        assert sign.opendrive_subtype == "10"
        assert sign.osm_id == "SE:A1"

    def test_load_manifest_template_signs(self, tmp_path):
        """Template signs are expanded."""
        manifest = {
            "library_id": "se",
            "name": "Test Library",
            "version": "1.0.0",
            "country_code": "SE",
            "description": "",
            "categories": [{"id": "C", "name": "Mandatory", "description": ""}],
            "signs": [
                {
                    "id": "C31",
                    "name": "Speed Limit",
                    "category": "C",
                    "is_template": True,
                    "template_values": [30, 50, 70],
                    "value_unit": "km/h",
                    "image_template": "C31_{value}.png",
                    "identifiers": {
                        "opendrive": {"type": "274", "subtype": "{value}"},
                        "opendrive_de": {"type": "274", "subtype": "{value}"},
                        "country": "C31-{value}",
                        "osm": "SE:C31-{value}"
                    }
                }
            ]
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        library = SignLibrary.from_manifest(manifest_path)

        # Template should expand to 3 signs
        assert len(library.signs) == 3

        sign_30 = library.get_sign("C31-30")
        assert sign_30 is not None
        assert sign_30.is_template is True
        assert sign_30.template_value == 30
        assert sign_30.opendrive_subtype == "30"
        assert sign_30.image_filename == "C31_30.png"
        assert sign_30.country_id == "C31-30"
        assert sign_30.osm_id == "SE:C31-30"

        sign_50 = library.get_sign("C31-50")
        assert sign_50 is not None
        assert sign_50.template_value == 50

    def test_load_manifest_file_not_found(self, tmp_path):
        """Returns None for missing file."""
        manifest_path = tmp_path / "nonexistent.json"

        library = SignLibrary.from_manifest(manifest_path)

        assert library is None

    def test_load_manifest_invalid_json(self, tmp_path):
        """Returns None for invalid JSON."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("not valid json {")

        library = SignLibrary.from_manifest(manifest_path)

        assert library is None

    def test_load_manifest_uses_directory_name_as_id(self, tmp_path):
        """Uses directory name as library ID if not specified."""
        manifest = {
            "name": "Test Library",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [],
            "signs": []
        }
        lib_dir = tmp_path / "my_library"
        lib_dir.mkdir()
        manifest_path = lib_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        library = SignLibrary.from_manifest(manifest_path)

        assert library.id == "my_library"

    def test_load_manifest_missing_optional_fields(self, tmp_path):
        """Handles missing optional fields gracefully."""
        manifest = {
            "library_id": "minimal",
            "name": "Minimal Library",
            "version": "1.0.0",
            "country_code": "XX",
            "description": "",
            "categories": [{"id": "A", "name": "Category A"}],
            "signs": [
                {
                    "id": "S1",
                    "name": "Sign 1",
                    "category": "A",
                    "identifiers": {}
                }
            ]
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        library = SignLibrary.from_manifest(manifest_path)

        assert library is not None
        assert library.license == ""
        assert library.source == ""
        assert len(library.categories) == 1
        assert library.categories[0].description == ""
        sign = library.get_sign("S1")
        assert sign is not None
        assert sign.opendrive_type == "-1"
        assert sign.opendrive_subtype == "-1"


class TestSignLibraryRebuildCaches:
    """Tests for _rebuild_caches method."""

    def test_rebuild_caches_after_modification(self, tmp_path):
        """Caches can be rebuilt after modification."""
        library = SignLibrary(
            id="test",
            name="Test",
            version="1.0.0",
            country_code="XX",
            description="",
            base_path=tmp_path,
            signs=[]
        )

        # Add a sign manually
        new_sign = SignDefinition(
            id="NEW", name="New Sign", category_id="A", library_id="test"
        )
        library.signs.append(new_sign)
        library._rebuild_caches()

        assert library.get_sign("NEW") is not None
