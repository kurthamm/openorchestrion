"""``openorchestrion-reanalyze`` — repair stored analysis after an analyzer fix.

``deterministic_analysis`` is derived from the MIDI bytes, so correcting the
analyzer makes every existing sidecar stale. The MIDI objects themselves are
immutable and content-addressed, so a library is repaired by re-deriving the
facts in place rather than by re-importing anything.

This exists because of issue #21: ``peak_simultaneous_notes`` over-counted
repeated pitches under a held sustain pedal, and that figure gates device
eligibility. Libraries imported before the fix carry inflated values and will
keep excluding pedal-heavy piano from stations until they are re-analyzed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import reindex_asset
from .metadata import MetadataError, reanalyze_asset, reanalyze_library

DEFAULT_LIBRARY_ROOT = "var/library"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-reanalyze",
        description=(
            "Recompute deterministic analysis for stored MIDI assets. "
            "Curated metadata, provenance and AI enrichment are left untouched."
        ),
    )
    parser.add_argument(
        "asset_id",
        nargs="?",
        help="Asset to re-analyze, as sha256:<hex> or a bare digest. Omit for the whole library.",
    )
    parser.add_argument("--library-root", default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--catalog-db", help="Catalog to reconcile (default: <root>/catalog.db)")
    parser.add_argument(
        "--no-reindex",
        action="store_true",
        help="Skip catalog reconciliation; run openorchestrion-reindex yourself afterwards",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    catalog = Path(args.catalog_db) if args.catalog_db else Path(args.library_root) / "catalog.db"

    try:
        if args.asset_id:
            record = reanalyze_asset(args.library_root, args.asset_id)
            if not args.no_reindex:
                reindex_asset(catalog, args.library_root, record.asset_id)
            if args.json:
                print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
            else:
                print(f"re-analyzed {record.asset_id[:19]}…")
            return
    except MetadataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    result = reanalyze_library(args.library_root)
    if not args.no_reindex:
        for record in result.updated:
            reindex_asset(catalog, args.library_root, record.asset_id)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"re-analyzed {len(result.updated)} assets")
        for failure in result.failed:
            print(f"skipped: {failure.asset_id[:19]}… ({failure.error_type}: {failure.reason})")
        if result.failed:
            print(f"\n{len(result.failed)} skipped.", file=sys.stderr)

    # A partially repaired library must not look like a clean run.
    if result.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
