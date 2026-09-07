"""Crawl the Mutopia Project archive into an OpenOrchestrion import set.

Output: <out>/files/<Composer>/<piece>/<file>.mid, <out>/catalog.csv (importer
manifest, one rights row per file) and <out>/tags.csv (descriptive metadata).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://www.mutopiaproject.org/ftp/"
OUT = Path(sys.argv[1])
COMPOSERS = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "files").mkdir(exist_ok=True)
NS = {"mp": "http://www.mutopiaproject.org/piece-data/0.1/"}
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
UA = {"User-Agent": "OpenOrchestrion library builder (contact: kurt@hamm.me)"}

LICENSES = {
    "Public Domain": (
        "public-domain",
        "https://creativecommons.org/publicdomain/mark/1.0/",
        "permitted",
    ),
    "Creative Commons Attribution 4.0": (
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
        "permitted-with-attribution",
    ),
    "Creative Commons Attribution 3.0": (
        "CC-BY-3.0",
        "https://creativecommons.org/licenses/by/3.0/",
        "permitted-with-attribution",
    ),
    "Creative Commons Attribution-ShareAlike 4.0": (
        "CC-BY-SA-4.0",
        "https://creativecommons.org/licenses/by-sa/4.0/",
        "permitted-with-attribution",
    ),
    "Creative Commons Attribution-ShareAlike 3.0": (
        "CC-BY-SA-3.0",
        "https://creativecommons.org/licenses/by-sa/3.0/",
        "permitted-with-attribution",
    ),
}
FULL_NAMES = {
    "BachJS": "Johann Sebastian Bach",
    "BeethovenLv": "Ludwig van Beethoven",
    "MozartWA": "Wolfgang Amadeus Mozart",
    "ChopinFF": "Frédéric Chopin",
    "JoplinS": "Scott Joplin",
    "DebussyC": "Claude Debussy",
    "SatieE": "Erik Satie",
    "SchubertF": "Franz Schubert",
    "BrahmsJ": "Johannes Brahms",
    "HaydnFJ": "Joseph Haydn",
    "HandelGF": "George Frideric Handel",
    "ScarlattiD": "Domenico Scarlatti",
    "SchumannR": "Robert Schumann",
    "LisztF": "Franz Liszt",
    "TchaikovskyPI": "Pyotr Ilyich Tchaikovsky",
    "VivaldiA": "Antonio Vivaldi",
    "GriegE": "Edvard Grieg",
    "MendelssohnF": "Felix Mendelssohn",
    "ClementiM": "Muzio Clementi",
    "CzernyC": "Carl Czerny",
    "DiabelliA": "Anton Diabelli",
    "RavelM": "Maurice Ravel",
    "PurcellH": "Henry Purcell",
    "CoupF": "François Couperin",
    "RameauJP": "Jean-Philippe Rameau",
    "TelemannGP": "Georg Philipp Telemann",
    "PachelbelJ": "Johann Pachelbel",
    "BurgmullerJFF": "Friedrich Burgmüller",
    "SchumannC": "Clara Schumann",
    "DvorakA": "Antonín Dvořák",
    "GershwinG": "George Gershwin",
    "AlbenizI": "Isaac Albéniz",
    "GranadosE": "Enrique Granados",
    "FieldJ": "John Field",
    "HellerS": "Stephen Heller",
    "KuhlauF": "Friedrich Kuhlau",
    "SorF": "Fernando Sor",
}


def composers():
    table = {}
    for line in COMPOSERS.read_text().splitlines():
        code, name = line.split("\t", 1)
        m = re.search(r"\((\d{4}|\?+|[0-9?]+)\s*[–-]\s*(\d{4}|\?+|[0-9?]*)\)", name)
        born = died = None
        if m:
            b, d = m.group(1), m.group(2)
            born = int(b) if b.isdigit() else None
            died = int(d) if d.isdigit() else None
        display = re.sub(r"\s*\(.*\)\s*$", "", name).strip()
        table[code] = (FULL_NAMES.get(code, display), born, died)
    return table


COMP = composers()


def get(url, retries=4, binary=False):
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
                return data if binary else data.decode("utf-8", "replace")
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def listing(url):
    html = get(url)
    return [h for h in re.findall(r'href="([^"?]+)"', html) if not h.startswith("/")]


def crawl():
    """Return list of (dir_url, rdf_name). Walk dirs; a dir with .rdf is a piece."""
    pieces, queue, seen = [], [BASE + c for c in listing(BASE) if c.endswith("/")], set()
    with ThreadPoolExecutor(8) as pool:
        while queue:
            batch, queue = queue, []
            for url, entries in zip(batch, pool.map(lambda u: listing(u), batch)):
                rdfs = [e for e in entries if e.endswith(".rdf")]
                if rdfs:
                    pieces.extend((url, r) for r in rdfs)
                    continue
                for e in entries:
                    if e.endswith("/") and not e.endswith("-lys/") and url + e not in seen:
                        seen.add(url + e)
                        queue.append(url + e)
    return pieces


def text(el, tag):
    x = el.find(f"mp:{tag}", NS)
    return (x.text or "").strip() if x is not None and x.text else ""


def performance_type(for_):
    f = for_.lower()
    if re.search(r"two pianos|2 pianos|piano 4 hands|four hands|4 hands|piano duet|piano \(4", f):
        return "TWO_PIANO" if "two pianos" in f or "2 pianos" in f else "PIANO_DUET"
    if f in {
        "piano",
        "harpsichord",
        "organ",
        "clavichord",
        "keyboard",
        "piano solo",
        "harpsichord, piano",
        "piano, harpsichord",
        "harpsichord or piano",
        "piano or harpsichord",
        "fortepiano",
    }:
        return "SOLO_PIANO"
    return "MULTI_INSTRUMENT"


def process(dir_url, rdf_name):
    rdf = ET.fromstring(get(dir_url + rdf_name).encode("utf-8"))
    d = rdf.find(".//rdf:Description", {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"})
    title, code, for_, date, style, licence = (
        text(d, t) for t in ("title", "composer", "for", "date", "style", "licence")
    )
    opus, arranger, mid, mid_id = (
        text(d, "opus"),
        text(d, "arranger"),
        text(d, "midFile"),
        text(d, "id"),
    )
    if not mid:
        return []
    name, born, died = COMP.get(code, (code, None, None))
    lic = LICENSES.get(licence)
    pd_basis = None
    if code in ("Anonymous", "Traditional"):
        pd_basis = f"{code} work; Mutopia publishes only editions of public-domain compositions"
    elif died is not None and died <= 1955:
        pd_basis = f"{name} died {died} (Mutopia composer list); Mutopia publishes only editions of public-domain compositions"
    open_ok = lic is not None and pd_basis is not None
    rel = dir_url[len(BASE) :].strip("/")
    target = OUT / "files" / rel
    target.mkdir(parents=True, exist_ok=True)
    blob = get(dir_url + mid, binary=True)
    files = []
    if mid.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for m in sorted(z.namelist()):
                if m.lower().endswith((".mid", ".midi")):
                    files.append((Path(m).name, z.read(m)))
    else:
        files.append((mid, blob))
    rows = []
    year = re.search(r"\d{4}", date)
    for fname, data in files:
        (target / fname).write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        t = title if len(files) == 1 else f"{title}: {Path(fname).stem}"
        if opus:
            t = f"{t} ({opus})" if opus.lower() not in t.lower() else t
        manifest = dict(
            path=str(Path(rel) / fname).replace("\\", "/"),
            sha256=sha,
            rights_status="verified-open" if open_ok else "personal",
            source_reference=dir_url + rdf_name,
            source_label="Mutopia Project",
            license=lic[0] if lic else licence,
            license_url=lic[1] if lic else "https://www.mutopiaproject.org/legal.html",
            attribution=f"Typeset for the Mutopia Project ({mid_id}); {licence}"
            + (f"; arranged by {arranger}" if arranger else ""),
            composition_rights="public-domain" if pd_basis else "unknown",
            composition_rights_basis=pd_basis or "",
            redistribution=lic[2] if lic else "unknown",
            verified_by="kurthamm via mutopia_crawl",
            verified_at=NOW,
        )
        tags = dict(
            sha256=sha,
            title=t,
            composer=name,
            year_composed=year.group(0) if year else "",
            era=style.lower(),
            performance_type=performance_type(for_),
            genres=",".join(
                g
                for g in {style.lower(), "ragtime" if style == "Jazz" and code == "JoplinS" else ""}
                if g
            ),
            moods="",
            themes="",
            instrumentation=for_,
            familiarity="",
            energy="",
        )
        rows.append((manifest, tags))
    return rows


def main():
    t0 = time.time()
    pieces = crawl()
    print(f"found {len(pieces)} piece records in {time.time() - t0:.0f}s", flush=True)
    (OUT / "pieces.json").write_text(json.dumps(pieces))
    manifest_rows, tag_rows, failures = [], [], []
    with ThreadPoolExecutor(8) as pool:
        futs = {pool.submit(process, u, r): (u, r) for u, r in pieces}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                for m, t in f.result():
                    manifest_rows.append(m)
                    tag_rows.append(t)
            except Exception as e:
                failures.append((futs[f], repr(e)))
            if i % 100 == 0:
                print(
                    f"{i}/{len(pieces)} pieces, {len(manifest_rows)} files, {len(failures)} failures",
                    flush=True,
                )
    with (OUT / "catalog.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest_rows[0].keys()))
        w.writeheader()
        w.writerows(manifest_rows)
    with (OUT / "tags.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(tag_rows[0].keys()))
        w.writeheader()
        w.writerows(tag_rows)
    (OUT / "failures.json").write_text(json.dumps(failures, indent=1))
    open_n = sum(1 for m in manifest_rows if m["rights_status"] == "verified-open")
    print(
        f"DONE: {len(manifest_rows)} files ({open_n} verified-open), {len(failures)} failures, {time.time() - t0:.0f}s"
    )


main()
