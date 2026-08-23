"""Library ingestion and durable metadata support."""

from .metadata import (
    MetadataConflictError,
    MetadataError,
    MetadataRecord,
    MetadataValidationError,
    read_metadata,
    reanalyze_asset,
    reanalyze_library,
    set_favorite,
    update_metadata,
)
from .rights import RightsError, RightsEvidence
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
    "reanalyze_asset",
    "reanalyze_library",
    "set_favorite",
    "update_metadata",
    "RightsError",
    "RightsEvidence",
    "ImportFailure",
    "ImportReport",
    "ImportResult",
    "discover_midi_files",
    "import_midi",
    "import_paths",
]
