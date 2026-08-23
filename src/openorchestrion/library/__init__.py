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
    CurationEntry,
    ImportFailure,
    ImportReport,
    ImportResult,
    discover_midi_files,
    ManifestError,
    import_manifest,
    import_midi,
    import_paths,
    read_curation_manifest,
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
    "CurationEntry",
    "ManifestError",
    "import_manifest",
    "read_curation_manifest",
    "ImportFailure",
    "ImportReport",
    "ImportResult",
    "discover_midi_files",
    "import_midi",
    "import_paths",
]
