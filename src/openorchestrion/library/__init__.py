"""Library ingestion and durable metadata support."""

from .metadata import (
    MetadataConflictError,
    MetadataError,
    MetadataRecord,
    MetadataValidationError,
    read_metadata,
    set_favorite,
    update_metadata,
)
from .importer import (
    ImportFailure,
    ImportReport,
    ImportResult,
    discover_midi_files,
    import_midi,
    import_paths,
)

__all__ = [
    "MetadataConflictError",
    "MetadataError",
    "MetadataRecord",
    "MetadataValidationError",
    "read_metadata",
    "set_favorite",
    "update_metadata",
    "ImportFailure",
    "ImportReport",
    "ImportResult",
    "discover_midi_files",
    "import_midi",
    "import_paths",
]
