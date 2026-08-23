"""``openorchestrion-tag`` — curate descriptive metadata from the command line.

Until this existed the importer wrote an empty ``descriptive_metadata`` block
and nothing could fill it, so Smart Stations scored against nothing and browse
screens showed untitled assets. This is the way a library gets its titles,
composers, genres and moods.

Two shapes, because tagging one piece and tagging a collection are different
jobs: flags for a single asset, and a CSV keyed by SHA-256 for the whole
library at once.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import reindex_asset
from .metadata import (
    CURATED_FIELDS,
    LIST_FIELDS,
    MetadataError,
    apply_edits,
    read_csv_edits,
    read_metadata,
    update_metadata,
)

DEFAULT_LIBRARY_ROOT = "var/library"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-tag",
        description="Edit curated descriptive metadata on imported MIDI assets.",
        epilog=(
            "Values are free text: they are trimmed and de-duplicated, but not "
            "restricted to a fixed vocabulary."
        ),
    )
    parser.add_argument(
        "asset_id",
        nargs="?",
        help="Asset to edit, as sha256:<hex> or a bare digest. Omit with --from-csv.",
    )
    parser.add_argument("--library-root", default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--catalog-db", help="Catalog to reconcile (default: <root>/catalog.db)")

    parser.add_argument("--title")
    parser.add_argument("--composition-title")
    parser.add_argument("--composer")
    parser.add_argument("--artist")
    parser.add_argument("--era")
    parser.add_argument("--year-composed")
    parser.add_argument("--composition-id")
    parser.add_argument("--performance-type")
    parser.add_argument("--quality-grade")
    parser.add_argument("--familiarity", help="1-5, or low/medium/high")
    parser.add_argument("--energy", help="1-5, or low/medium/high")

    for field in LIST_FIELDS:
        parser.add_argument(
            f"--{field[:-1] if field.endswith('s') and field != 'instrumentation' else field}",
            dest=field,
            action="append",
            help=f"Add to {field}; repeatable, or comma-separated",
        )

    favorite = parser.add_mutually_exclusive_group()
    favorite.add_argument("--favorite", dest="favorite", action="store_true", default=None)
    favorite.add_argument("--no-favorite", dest="favorite", action="store_false")

    parser.add_argument(
        "--clear",
        action="append",
        default=[],
        metavar="FIELD",
        help="Remove a curated field entirely; repeatable",
    )
    parser.add_argument(
        "--expect-revision",
        help="Refuse the write if the sidecar changed since this revision",
    )
    parser.add_argument("--from-csv", help="Bulk edit file keyed by asset_id or sha256")
    parser.add_argument("--show", action="store_true", help="Print current metadata and exit")
    parser.add_argument("--no-reindex", action="store_true", help="Skip catalog reconciliation")
    parser.add_argument("--json", action="store_true")
    return parser


_FLAG_TO_FIELD = {
    "title": "title",
    "composition_title": "composition_title",
    "composer": "composer",
    "artist": "artist",
    "era": "era",
    "year_composed": "year_composed",
    "composition_id": "composition_id",
    "performance_type": "performance_type",
    "quality_grade": "quality_grade",
    "familiarity": "familiarity",
    "energy": "energy",
    "favorite": "favorite",
}


def _changes_from_args(args: argparse.Namespace) -> dict[str, object]:
    changes: dict[str, object] = {}
    for attribute, field in _FLAG_TO_FIELD.items():
        value = getattr(args, attribute, None)
        if value is not None:
            changes[field] = value
    for field in LIST_FIELDS:
        values = getattr(args, field, None)
        if values:
            # Repeated flags and comma-separated values both land here; the
            # domain layer splits and de-duplicates.
            changes[field] = ",".join(values)
    return changes


def _catalog_path(args: argparse.Namespace) -> Path:
    if args.catalog_db:
        return Path(args.catalog_db)
    return Path(args.library_root) / "catalog.db"


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.from_csv and args.asset_id:
        parser.error("give an asset_id or --from-csv, not both")
    if not args.from_csv and not args.asset_id:
        parser.error("an asset_id is required unless --from-csv is used")

    try:
        if args.show:
            record = read_metadata(args.library_root, args.asset_id)
            if args.json:
                print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
            else:
                print(f"{record.asset_id}  revision {record.revision[:12]}")
                for name in CURATED_FIELDS:
                    if name in record.descriptive_metadata:
                        print(f"  {name}: {record.descriptive_metadata[name]}")
                if not record.descriptive_metadata:
                    print("  (no curated metadata yet)")
            return

        if args.from_csv:
            result = apply_edits(args.library_root, read_csv_edits(args.from_csv))
            if not args.no_reindex:
                for record in result.updated:
                    reindex_asset(_catalog_path(args), args.library_root, record.asset_id)
            if args.json:
                print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            else:
                for record in result.updated:
                    print(f"tagged: {record.asset_id[:19]}…")
                for failure in result.failed:
                    print(f"skipped: {failure.asset_id} ({failure.error_type}: {failure.reason})")
                print(f"\n{len(result.updated)} tagged, {len(result.failed)} skipped.")
            if result.failed:
                raise SystemExit(1)
            return

        changes = _changes_from_args(args)
        if not changes and not args.clear:
            parser.error("nothing to change; pass a field, --clear, or --show")

        record = update_metadata(
            args.library_root,
            args.asset_id,
            changes,
            remove=args.clear,
            expected_revision=args.expect_revision,
        )
        if not args.no_reindex:
            reindex_asset(_catalog_path(args), args.library_root, record.asset_id)

        if args.json:
            print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
        else:
            fields = ", ".join(sorted(set(changes) | set(args.clear)))
            print(f"tagged {record.asset_id[:19]}… ({fields})")
            print(f"revision {record.revision[:12]}")
    except MetadataError as exc:
        # A curation mistake is a user error, not a crash: say what was wrong
        # and leave the previous valid sidecar untouched.
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
