"""Read-only qualification records published atomically with admission."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3


def qualification(catalog: Path, asset_id: str) -> dict | None:
    path = catalog.resolve().with_name("quality.sqlite3")
    if not path.exists():
        return None
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as conn:
        row = conn.execute("SELECT record FROM quality WHERE asset_id=?", (asset_id,)).fetchone()
    return json.loads(row[0]) if row else None
