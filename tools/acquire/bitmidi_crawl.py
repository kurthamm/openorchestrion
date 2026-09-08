"""BitMidi (bitmidi.com) -> OpenOrchestrion personal-library import set, ordered by plays."""

import csv
import hashlib
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from openorchestrion.library.title_identity import source_identity

OUT = Path(sys.argv[1])
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
(OUT / "files").mkdir(parents=True, exist_ok=True)
UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) OpenOrchestrion library builder (kurt@hamm.me)"
}
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get(url, binary=False, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read() if binary else json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


index_path = OUT / "index.json"
if index_path.exists():
    entries = json.load(open(index_path))
else:
    entries, page = [], 0
    while len(entries) < LIMIT:
        d = get(f"https://bitmidi.com/api/midi/all?page={page}&pageSize=100")["result"]
        entries += d["results"]
        if page % 50 == 0:
            print(f"index page {page}/{d['pageTotal']}: {len(entries)}", flush=True)
        if page >= d["pageTotal"]:
            break
        page += 1
    json.dump(entries, open(index_path, "w"))
entries = entries[:LIMIT]
print(len(entries), "entries", flush=True)


def parse_name(name):
    identity = source_identity(name, source="BitMidi")
    return identity.get("source_context", ""), identity["title"]


def fetch(e):
    target = OUT / "files" / f"{e['id']}.mid"
    if not target.exists():
        target.write_bytes(get("https://bitmidi.com" + e["downloadUrl"], binary=True))
    data = target.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    artist, title = parse_name(e["name"])
    man = dict(
        path=f"files/{e['id']}.mid",
        sha256=sha,
        rights_status="personal",
        source_reference="https://bitmidi.com" + e["url"],
        source_label="BitMidi",
        license="unknown",
        license_url="https://bitmidi.com/about",
        attribution=f"BitMidi upload '{e['name']}' (original sequencer unknown)",
        composition_rights="unknown",
        composition_rights_basis="",
        redistribution="unknown",
        verified_by="kurthamm via bitmidi_crawl",
        verified_at=NOW,
    )
    tags = dict(
        sha256=sha,
        title=title[:200],
        composer="",
        artist="",
        source_context=artist[:120],
        source_title=e["name"],
        title_status=source_identity(e["name"], source="BitMidi")["title_status"],
        year_composed="",
        era="",
        performance_type="MULTI_INSTRUMENT",
        genres="popular",
        moods="",
        themes="",
        instrumentation="",
        familiarity=("high" if e["plays"] > 20000 else "medium" if e["plays"] > 2000 else "low"),
        energy="",
    )
    return man, tags


rows, fails = [], 0
with ThreadPoolExecutor(6) as pool:
    futs = [pool.submit(fetch, e) for e in entries]
    for i, f in enumerate(as_completed(futs), 1):
        try:
            rows.append(f.result())
        except Exception:
            fails += 1
        if i % 1000 == 0:
            print(f"{i}/{len(entries)} downloaded, {fails} failures", flush=True)
with open(OUT / "catalog.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0][0]))
    w.writeheader()
    w.writerows(m for m, _ in rows)
with open(OUT / "tags.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0][1]))
    w.writeheader()
    w.writerows(t for _, t in rows)
print(f"DONE {len(rows)} files, {fails} failures")
