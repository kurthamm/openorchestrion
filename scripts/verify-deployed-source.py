"""Compare checked-out runtime files with an installed package, without importing it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('src/openorchestrion'))
    parser.add_argument('--installed', type=Path, required=True)
    args = parser.parse_args()
    source, installed = args.source.resolve(), args.installed.resolve()
    if source == installed or not source.is_dir() or not installed.is_dir():
        parser.error('Supply distinct, existing source and installed package directories.')
    checked, differences = 0, []
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        relative = path.relative_to(source)
        target = installed / relative
        checked += 1
        if not target.is_file():
            differences.append({'path': relative.as_posix(), 'reason': 'missing'})
        elif hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
            differences.append({'path': relative.as_posix(), 'reason': 'content mismatch'})
    print(json.dumps({'checked_files': checked, 'differences': differences}, indent=2))
    return 1 if differences or checked == 0 else 0


if __name__ == '__main__':
    raise SystemExit(main())
