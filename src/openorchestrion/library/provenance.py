"""``openorchestrion-rights`` — record rights research from the command line.

Rights research arrives after the bytes do. A file is downloaded, imported as
``personal`` because nothing is known about it yet, and only later does someone
track down the archive record and read the actual license. ``set_rights`` is the
domain operation for that, but a curator should not have to write Python to use
it, and they should not have to remember a second command afterwards to stop the
catalog disagreeing with the sidecar.

``rights_status`` gates what a station may play, so a sidecar that says
``verified-open`` while ``catalog.db`` still says ``personal`` means the research
silently had no effect on what the appliance will actually play. This command
writes and reconciles in one step for exactly that reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .catalog import reindex_asset
from .metadata import MetadataError, read_rights, set_rights
from .rights import COMPOSITION_RIGHTS, ESTABLISHED_LICENSES, REDISTRIBUTION, RIGHTS_STATUSES

DEFAULT_LIBRARY_ROOT = "var/library"

# Flag name -> provenance field, for the fields a curator sets directly.
_FIELD_FLAGS: dict[str, str] = {
    "rights_status": "rights_status",
    "source_reference": "source_reference",
    "source_label": "source_label",
    "license_name": "license",
    "license_url": "license_url",
    "attribution": "attribution",
    "composition_rights": "composition_rights",
    "composition_rights_basis": "composition_rights_basis",
    "redistribution": "redistribution",
    "verified_at": "verified_at",
    "verified_by": "verified_by",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-rights",
        description="Record or revise the rights evidence on an imported MIDI asset.",
        epilog=(
            "Only the fields you pass are changed; the rest of the provenance block "
            "is left alone. A verified-open claim is refused unless the merged "
            "result supports it, so an incomplete revision fails rather than "
            "producing a claim that outruns its evidence."
        ),
    )
    parser.add_argument("asset_id", help="Asset to edit, as sha256:<hex> or a bare digest")
    parser.add_argument("--library-root", default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--catalog-db", help="Catalog to reconcile (default: <root>/catalog.db)")

    parser.add_argument("--rights-status", choices=RIGHTS_STATUSES)
    parser.add_argument(
        "--source-reference",
        help="Where this file came from: a URL or citation someone can re-check",
    )
    parser.add_argument("--source-label", help="Human-readable source name")
    parser.add_argument(
        "--license",
        dest="license_name",
        help=(
            "License of the MIDI file/arrangement itself, a separate work from the "
            f"composition. Established ids: {', '.join(ESTABLISHED_LICENSES)}"
        ),
    )
    parser.add_argument("--license-url", help="Where the license terms were read")
    parser.add_argument("--attribution", help="Credit text this license obliges us to display")
    parser.add_argument(
        "--composition-rights",
        choices=COMPOSITION_RIGHTS,
        help="Rights in the underlying musical work, independent of this file",
    )
    parser.add_argument(
        "--composition-rights-basis",
        help=(
            "Why the composition is clear, e.g. 'composer died 1917, published 1899' "
            "or 'licensed by the arranger under CC-BY-4.0, see <url>'"
        ),
    )
    parser.add_argument(
        "--redistribution",
        choices=REDISTRIBUTION,
        help="Whether this file may be redistributed",
    )
    parser.add_argument("--verified-by", help="Who established these terms")
    parser.add_argument(
        "--verified-at",
        help=(
            "When these terms were established (ISO 8601). Defaults to now when a "
            "claim is raised to verified-open."
        ),
    )

    parser.add_argument(
        "--expect-revision",
        help="Refuse the write if the sidecar has changed since this revision",
    )
    parser.add_argument("--show", action="store_true", help="Print current rights and exit")
    parser.add_argument("--no-reindex", action="store_true", help="Skip catalog reconciliation")
    parser.add_argument("--json", action="store_true")
    return parser


def _changes_from_args(args: argparse.Namespace) -> dict[str, str]:
    """Only what the curator actually passed.

    Argparse defaults are ``None`` rather than ``"unknown"`` so that omitting a
    flag leaves the stored value alone. Defaulting to ``unknown`` here would
    quietly erase established evidence every time someone corrected a typo in
    one other field.
    """
    changes: dict[str, str] = {}
    for flag, field in _FIELD_FLAGS.items():
        value = getattr(args, flag, None)
        if value is not None:
            changes[field] = value

    # Establishing the terms is what this command does, so the moment it runs is
    # the moment they were established. Only stamped when the claim is actually
    # being raised, and never over a value the curator supplied.
    if changes.get("rights_status") == "verified-open" and "verified_at" not in changes:
        changes["verified_at"] = datetime.now(UTC).isoformat()
    return changes


def _catalog_path(args: argparse.Namespace) -> Path:
    if args.catalog_db:
        return Path(args.catalog_db)
    return Path(args.library_root) / "catalog.db"


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.show:
            record = read_rights(args.library_root, args.asset_id)
            if args.json:
                print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
            else:
                print(f"{record.asset_id}  revision {record.revision[:12]}")
                for name, value in sorted(record.provenance.items()):
                    print(f"  {name}: {value}")
            return

        changes = _changes_from_args(args)
        if not changes:
            parser.error("nothing to change; pass a rights field or --show")

        record = set_rights(
            args.library_root,
            args.asset_id,
            changes,
            expected_revision=args.expect_revision,
        )
        if not args.no_reindex:
            # The sidecar is authoritative, but the catalog is what stations
            # query. Leaving them disagreeing would make the research invisible
            # to the only consumer that acts on it.
            reindex_asset(_catalog_path(args), args.library_root, record.asset_id)

        if args.json:
            print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"rights updated on {record.asset_id[:19]}… ({', '.join(sorted(changes))})")
            print(f"revision {record.revision[:12]}")
            if record.provenance.get("rights_status") == "verified-open":
                print("claim: verified-open, supported by the recorded evidence")
    except MetadataError as exc:
        # A rights mistake is a user error, not a crash: say what is missing and
        # leave the previous valid sidecar untouched.
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
