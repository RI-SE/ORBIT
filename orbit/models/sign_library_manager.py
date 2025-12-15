"""
Sign library manager for discovering and loading sign libraries.

Provides a singleton manager that handles library discovery from both
application and user directories, loading, and caching.
"""

from pathlib import Path
from typing import Optional, List, Dict
import logging

from .sign_library import SignLibrary, SignDefinition

logger = logging.getLogger(__name__)


class SignLibraryManager:
    """
    Singleton manager for sign library discovery and loading.

    Libraries are discovered from two locations:
    - Application directory: orbit/signs/ (bundled with app)
    - User directory: ~/.orbit/signs/ (user-added libraries)

    User libraries with the same ID override application libraries.
    """

    _instance: Optional['SignLibraryManager'] = None

    def __init__(self):
        """Initialize the manager. Use instance() to get the singleton."""
        self._libraries: Dict[str, SignLibrary] = {}
        self._discovered_paths: Dict[str, Path] = {}
        self._discovery_done = False

        # Determine paths
        # App signs path: relative to this file's package
        self._app_signs_path = Path(__file__).parent.parent / "signs"
        # User signs path: in user's home directory
        self._user_signs_path = Path.home() / ".orbit" / "signs"

    @classmethod
    def instance(cls) -> 'SignLibraryManager':
        """
        Get the singleton instance of SignLibraryManager.

        Returns:
            The SignLibraryManager singleton
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance. Useful for testing."""
        cls._instance = None

    def get_app_signs_path(self) -> Path:
        """Get the application signs directory path."""
        return self._app_signs_path

    def get_user_signs_path(self) -> Path:
        """Get the user signs directory path."""
        return self._user_signs_path

    def discover_libraries(self, force: bool = False) -> List[str]:
        """
        Discover all available library IDs from both paths.

        User libraries with the same ID override app libraries.

        Args:
            force: If True, re-scan even if already discovered

        Returns:
            List of available library IDs
        """
        if self._discovery_done and not force:
            return list(self._discovered_paths.keys())

        self._discovered_paths.clear()

        # Scan app directory first
        if self._app_signs_path.exists():
            for subdir in self._app_signs_path.iterdir():
                if subdir.is_dir():
                    manifest = subdir / "manifest.json"
                    if manifest.exists():
                        self._discovered_paths[subdir.name] = manifest
                        logger.debug(f"Discovered app library: {subdir.name}")

        # Scan user directory (overrides app libraries with same ID)
        if self._user_signs_path.exists():
            for subdir in self._user_signs_path.iterdir():
                if subdir.is_dir():
                    manifest = subdir / "manifest.json"
                    if manifest.exists():
                        if subdir.name in self._discovered_paths:
                            logger.info(f"User library '{subdir.name}' overrides app library")
                        self._discovered_paths[subdir.name] = manifest
                        logger.debug(f"Discovered user library: {subdir.name}")

        self._discovery_done = True
        logger.info(f"Discovered {len(self._discovered_paths)} sign libraries")
        return list(self._discovered_paths.keys())

    def load_library(self, library_id: str) -> Optional[SignLibrary]:
        """
        Load a library by ID.

        Libraries are cached after first load.

        Args:
            library_id: The library ID to load

        Returns:
            SignLibrary if successful, None if not found or failed to load
        """
        # Return cached if available
        if library_id in self._libraries:
            return self._libraries[library_id]

        # Ensure discovery has been done
        if not self._discovery_done:
            self.discover_libraries()

        # Check if library exists
        manifest_path = self._discovered_paths.get(library_id)
        if not manifest_path:
            logger.warning(f"Library '{library_id}' not found")
            return None

        # Load from manifest
        library = SignLibrary.from_manifest(manifest_path)
        if library:
            self._libraries[library_id] = library
            logger.info(f"Loaded sign library: {library.name} ({len(library.signs)} signs)")
        return library

    def get_library(self, library_id: str) -> Optional[SignLibrary]:
        """
        Get a library by ID.

        Will attempt to load if not already loaded.

        Args:
            library_id: The library ID

        Returns:
            SignLibrary if available, None otherwise
        """
        if library_id in self._libraries:
            return self._libraries[library_id]
        return self.load_library(library_id)

    def get_enabled_libraries(self, enabled_ids: List[str]) -> List[SignLibrary]:
        """
        Get all enabled libraries in order.

        Args:
            enabled_ids: List of library IDs that are enabled

        Returns:
            List of loaded SignLibrary objects (in order of enabled_ids)
        """
        libraries = []
        for lib_id in enabled_ids:
            library = self.get_library(lib_id)
            if library:
                libraries.append(library)
        return libraries

    def get_sign_definition(
        self,
        library_id: str,
        sign_id: str
    ) -> Optional[SignDefinition]:
        """
        Get a sign definition from a specific library.

        Args:
            library_id: The library ID
            sign_id: The sign ID within the library

        Returns:
            SignDefinition if found, None otherwise
        """
        library = self.get_library(library_id)
        if library:
            return library.get_sign(sign_id)
        return None

    def get_all_available_libraries_info(self) -> List[Dict]:
        """
        Get info about all available libraries without fully loading them.

        Returns:
            List of dicts with 'id', 'name', 'path' for each library
        """
        self.discover_libraries()
        info = []
        for lib_id, manifest_path in self._discovered_paths.items():
            # Try to get name from loaded library or manifest
            if lib_id in self._libraries:
                name = self._libraries[lib_id].name
            else:
                # Quick peek at manifest for name
                try:
                    import json
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        name = data.get('name', lib_id)
                except Exception:
                    name = lib_id

            info.append({
                'id': lib_id,
                'name': name,
                'path': str(manifest_path.parent)
            })
        return info

    def ensure_user_signs_directory(self) -> Path:
        """
        Ensure the user signs directory exists.

        Returns:
            Path to the user signs directory
        """
        self._user_signs_path.mkdir(parents=True, exist_ok=True)
        return self._user_signs_path


# Mapping from legacy SignalType values to library sign IDs
# Used for migrating old projects to the library system
LEGACY_SIGNAL_TYPE_MAPPING = {
    "give_way": ("se", "B1"),
    "speed_limit": ("se", "C31"),  # Template - needs value suffix
    "stop": ("se", "B2"),
    "no_entry": ("se", "C1"),
    "priority_road": ("se", "B4"),
    "end_of_speed_limit": ("se", "C32"),  # Template - needs value suffix
    "traffic_signals": ("se", "X1"),  # May not exist in library
}


def get_legacy_library_mapping(
    legacy_type: str,
    value: Optional[int] = None
) -> tuple[Optional[str], Optional[str]]:
    """
    Get the library ID and sign ID for a legacy signal type.

    Args:
        legacy_type: The legacy SignalType value string (e.g., "give_way")
        value: Optional value for template signs (e.g., 50 for speed limit)

    Returns:
        Tuple of (library_id, sign_id) or (None, None) if no mapping exists
    """
    mapping = LEGACY_SIGNAL_TYPE_MAPPING.get(legacy_type)
    if not mapping:
        return (None, None)

    library_id, base_sign_id = mapping

    # Handle template signs that need value suffix
    if legacy_type in ("speed_limit", "end_of_speed_limit") and value is not None:
        sign_id = f"{base_sign_id}-{value}"
    else:
        sign_id = base_sign_id

    return (library_id, sign_id)
