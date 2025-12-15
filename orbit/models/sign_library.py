"""
Sign library models for traffic sign definitions.

Provides data classes for representing sign libraries loaded from JSON manifests.
Libraries contain categories and sign definitions with OpenDRIVE mappings.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class SignDefinition:
    """
    Definition of a traffic sign from a library.

    Attributes:
        id: Unique sign ID within library (e.g., "B1", "C31-50")
        name: Display name (e.g., "Give Way", "Speed Limit 50")
        category_id: Category this sign belongs to (e.g., "B", "C")
        library_id: ID of the library containing this sign
        image_filename: Filename of the sign image (e.g., "B1_give_way.png")
        default_width: Default physical width in meters
        default_height: Default physical height in meters
        opendrive_type: OpenDRIVE type code using country-specific codes (e.g., "B", "C31")
        opendrive_subtype: OpenDRIVE subtype code (e.g., "-1", "1", "50")
        opendrive_de_type: Optional German VzKat type code (e.g., "205", "274")
        opendrive_de_subtype: Optional German VzKat subtype code (e.g., "-1", "50")
        country_id: Country-specific sign ID (e.g., "B1", "C31-50")
        osm_id: OpenStreetMap sign ID (e.g., "SE:B1")
        is_template: True if this is a parameterized sign (e.g., speed limit)
        template_value: The specific value for template signs (e.g., 50 for speed limit)
        value_unit: Unit for template values (e.g., "km/h")
    """
    id: str
    name: str
    category_id: str
    library_id: str
    image_filename: Optional[str] = None
    default_width: float = 0.6
    default_height: float = 0.6
    opendrive_type: str = "-1"
    opendrive_subtype: str = "-1"
    opendrive_de_type: str = ""
    opendrive_de_subtype: str = ""
    country_id: str = ""
    osm_id: str = ""
    is_template: bool = False
    template_value: Optional[int] = None
    value_unit: str = ""

    def get_display_name(self) -> str:
        """Get display name, including value for template signs."""
        if self.is_template and self.template_value is not None:
            return f"{self.name} {self.template_value}"
        return self.name


@dataclass
class SignCategory:
    """
    Category grouping for signs within a library.

    Attributes:
        id: Category ID (e.g., "A", "B", "C")
        name: Display name (e.g., "Warning Signs")
        description: Localized description (e.g., "Varningsskyltar")
        library_id: ID of the library containing this category
    """
    id: str
    name: str
    description: str
    library_id: str


@dataclass
class SignLibrary:
    """
    A loaded sign library containing categories and sign definitions.

    Attributes:
        id: Unique library ID (e.g., "se", "de", "us")
        name: Display name (e.g., "Swedish Road Signs")
        version: Library version string
        country_code: ISO 3166-1 country code
        description: Library description
        license: License information
        source: Source of sign images
        base_path: Path to the library directory
        categories: List of sign categories
        signs: List of sign definitions
    """
    id: str
    name: str
    version: str
    country_code: str
    description: str
    base_path: Path
    license: str = ""
    source: str = ""
    categories: List[SignCategory] = field(default_factory=list)
    signs: List[SignDefinition] = field(default_factory=list)

    # Internal lookup caches
    _signs_by_id: Dict[str, SignDefinition] = field(default_factory=dict, repr=False)
    _signs_by_category: Dict[str, List[SignDefinition]] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        """Build lookup caches after initialization."""
        self._rebuild_caches()

    def _rebuild_caches(self):
        """Rebuild internal lookup caches."""
        self._signs_by_id = {sign.id: sign for sign in self.signs}
        self._signs_by_category = {}
        for sign in self.signs:
            if sign.category_id not in self._signs_by_category:
                self._signs_by_category[sign.category_id] = []
            self._signs_by_category[sign.category_id].append(sign)

    def get_sign(self, sign_id: str) -> Optional[SignDefinition]:
        """
        Get a sign definition by ID.

        Args:
            sign_id: The sign ID to look up

        Returns:
            SignDefinition if found, None otherwise
        """
        return self._signs_by_id.get(sign_id)

    def get_signs_by_category(self, category_id: str) -> List[SignDefinition]:
        """
        Get all signs in a category.

        Args:
            category_id: The category ID to filter by

        Returns:
            List of SignDefinition objects in the category
        """
        return self._signs_by_category.get(category_id, [])

    def get_category(self, category_id: str) -> Optional[SignCategory]:
        """
        Get a category by ID.

        Args:
            category_id: The category ID to look up

        Returns:
            SignCategory if found, None otherwise
        """
        for cat in self.categories:
            if cat.id == category_id:
                return cat
        return None

    def get_sign_image_path(self, sign_def: SignDefinition) -> Optional[Path]:
        """
        Get the full path to a sign's image file.

        Args:
            sign_def: The sign definition

        Returns:
            Path to image file if it exists, None otherwise
        """
        if not sign_def.image_filename:
            return None
        image_path = self.base_path / sign_def.image_filename
        if image_path.exists():
            return image_path
        return None

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> Optional['SignLibrary']:
        """
        Load a sign library from a manifest.json file.

        Args:
            manifest_path: Path to the manifest.json file

        Returns:
            SignLibrary instance if successful, None on error
        """
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load sign library manifest {manifest_path}: {e}")
            return None

        library_id = data.get('library_id', manifest_path.parent.name)
        base_path = manifest_path.parent

        # Parse categories
        categories = []
        for cat_data in data.get('categories', []):
            categories.append(SignCategory(
                id=cat_data['id'],
                name=cat_data['name'],
                description=cat_data.get('description', ''),
                library_id=library_id
            ))

        # Parse signs
        signs = []
        for sign_data in data.get('signs', []):
            identifiers = sign_data.get('identifiers', {})
            opendrive = identifiers.get('opendrive', {})
            opendrive_de = identifiers.get('opendrive_de', {})

            is_template = sign_data.get('is_template', False)

            if is_template:
                # Expand template into multiple sign definitions
                template_values = sign_data.get('template_values', [])
                image_template = sign_data.get('image_template', '')
                for value in template_values:
                    # Replace {value} placeholder in strings
                    sign_id = f"{sign_data['id']}-{value}"
                    image_filename = image_template.replace('{value}', str(value)) if image_template else None
                    od_subtype = str(opendrive.get('subtype', '-1')).replace('{value}', str(value))
                    od_de_subtype = str(opendrive_de.get('subtype', '')).replace('{value}', str(value)) if opendrive_de else ''
                    country_id = identifiers.get('country', '').replace('{value}', str(value))
                    osm_id = identifiers.get('osm', '').replace('{value}', str(value))

                    signs.append(SignDefinition(
                        id=sign_id,
                        name=sign_data['name'],
                        category_id=sign_data['category'],
                        library_id=library_id,
                        image_filename=image_filename,
                        default_width=sign_data.get('default_width', 0.6),
                        default_height=sign_data.get('default_height', 0.6),
                        opendrive_type=str(opendrive.get('type', '-1')),
                        opendrive_subtype=od_subtype,
                        opendrive_de_type=str(opendrive_de.get('type', '')) if opendrive_de else '',
                        opendrive_de_subtype=od_de_subtype,
                        country_id=country_id,
                        osm_id=osm_id,
                        is_template=True,
                        template_value=value,
                        value_unit=sign_data.get('value_unit', '')
                    ))
            else:
                # Simple non-template sign
                signs.append(SignDefinition(
                    id=sign_data['id'],
                    name=sign_data['name'],
                    category_id=sign_data['category'],
                    library_id=library_id,
                    image_filename=sign_data.get('image'),
                    default_width=sign_data.get('default_width', 0.6),
                    default_height=sign_data.get('default_height', 0.6),
                    opendrive_type=str(opendrive.get('type', '-1')),
                    opendrive_subtype=str(opendrive.get('subtype', '-1')),
                    opendrive_de_type=str(opendrive_de.get('type', '')) if opendrive_de else '',
                    opendrive_de_subtype=str(opendrive_de.get('subtype', '')) if opendrive_de else '',
                    country_id=identifiers.get('country', ''),
                    osm_id=identifiers.get('osm', ''),
                    is_template=False,
                    template_value=None,
                    value_unit=''
                ))

        return cls(
            id=library_id,
            name=data.get('name', library_id),
            version=data.get('version', '1.0.0'),
            country_code=data.get('country_code', ''),
            description=data.get('description', ''),
            base_path=base_path,
            license=data.get('license', ''),
            source=data.get('source', ''),
            categories=categories,
            signs=signs
        )
