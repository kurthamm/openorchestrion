"""MAESTRO v3 -> OpenOrchestrion import set (personal library: CC BY-NC-SA 4.0)."""

import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(sys.argv[1])
BASE = ROOT / "maestro-v3.0.0"
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
DIED = {
    "Alban Berg": 1935,
    "Alexander Scriabin": 1915,
    "Antonio Soler": 1783,
    "Carl Maria von Weber": 1826,
    "Charles Gounod": 1893,
    "Franz Liszt": 1886,
    "Claude Debussy": 1918,
    "César Franck": 1890,
    "Domenico Scarlatti": 1757,
    "Edvard Grieg": 1907,
    "Felix Mendelssohn": 1847,
    "Sergei Rachmaninoff": 1943,
    "Camille Saint-Saëns": 1921,
    "Vladimir Horowitz": 1989,
    "Franz Schubert": 1828,
    "Leopold Godowsky": 1938,
    "Fritz Kreisler": 1962,
    "Frédéric Chopin": 1849,
    "George Enescu": 1955,
    "George Frideric Handel": 1759,
    "Georges Bizet": 1875,
    "Ferruccio Busoni": 1924,
    "Moritz Moszkowski": 1925,
    "Giuseppe Verdi": 1901,
    "Henry Purcell": 1695,
    "Isaac Albéniz": 1909,
    "Jean-Philippe Rameau": 1764,
    "Johann Christian Fischer": 1800,
    "Wolfgang Amadeus Mozart": 1791,
    "Johann Pachelbel": 1706,
    "Johann Sebastian Bach": 1750,
    "Egon Petri": 1962,
    "Myra Hess": 1965,
    "Johann Strauss": 1899,
    "Alfred Grünfeld": 1924,
    "Johannes Brahms": 1897,
    "Joseph Haydn": 1809,
    "Leoš Janáček": 1928,
    "Ludwig van Beethoven": 1827,
    "Mikhail Glinka": 1857,
    "Mily Balakirev": 1910,
    "Modest Mussorgsky": 1881,
    "Muzio Clementi": 1832,
    "Niccolò Paganini": 1840,
    "Nikolai Medtner": 1951,
    "Nikolai Rimsky-Korsakov": 1908,
    "Orlando Gibbons": 1625,
    "Percy Grainger": 1961,
    "Pyotr Ilyich Tchaikovsky": 1893,
    "Mikhail Pletnev": None,
    "Richard Wagner": 1883,
    "Robert Schumann": 1856,
    "György Cziffra": 1994,
    "Vyacheslav Gryaznov": None,
}
ERA = {
    "Baroque": [
        "Antonio Soler",
        "Domenico Scarlatti",
        "George Frideric Handel",
        "Henry Purcell",
        "Jean-Philippe Rameau",
        "Johann Pachelbel",
        "Johann Sebastian Bach",
        "Orlando Gibbons",
    ],
    "Classical": [
        "Carl Maria von Weber",
        "Joseph Haydn",
        "Ludwig van Beethoven",
        "Muzio Clementi",
        "Wolfgang Amadeus Mozart",
        "Johann Christian Fischer",
    ],
    "Modern": [
        "Alban Berg",
        "Alexander Scriabin",
        "Claude Debussy",
        "George Enescu",
        "Leoš Janáček",
        "Nikolai Medtner",
        "Percy Grainger",
        "Sergei Rachmaninoff",
        "Isaac Albéniz",
    ],
}


def era(c):
    return next((k.lower() for k, v in ERA.items() if c in v), "romantic")


man, tags = [], []
for r in csv.DictReader(open(ROOT / "maestro-v3.0.0.csv")):
    p = BASE / r["midi_filename"]
    data = p.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    names = [n.strip() for n in r["canonical_composer"].split("/")]
    composer, arranger = names[0], (names[1] if len(names) > 1 else "")
    deaths = [DIED.get(n) for n in names]
    pd = all(d is not None and d <= 1955 for d in deaths)
    basis = "; ".join(f"{n} died {DIED[n]}" for n in names if DIED.get(n)) if pd else ""
    title = r["canonical_title"] + (f" (arr. {arranger})" if arranger else "")
    man.append(
        dict(
            path=str(Path("maestro-v3.0.0") / r["midi_filename"]),
            sha256=sha,
            rights_status="personal",
            source_reference="https://magenta.tensorflow.org/datasets/maestro",
            source_label="MAESTRO v3.0.0 (International Piano-e-Competition)",
            license="CC-BY-NC-SA-4.0",
            license_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
            attribution="Hawthorne et al., MAESTRO dataset, Google Magenta / International Piano-e-Competition; CC BY-NC-SA 4.0",
            composition_rights="public-domain" if pd else "unknown",
            composition_rights_basis=basis,
            redistribution="prohibited",
            verified_by="kurthamm via maestro_manifest",
            verified_at=NOW,
        )
    )
    tags.append(
        dict(
            sha256=sha,
            title=f"{title} (e-Competition {r['year']} performance)",
            composition_title=title,
            composer=composer,
            artist=f"International Piano-e-Competition {r['year']}",
            year_composed="",
            era=era(composer),
            performance_type="SOLO_PIANO",
            quality_grade="A",
            genres="classical",
            moods="",
            themes="",
            instrumentation="piano",
            familiarity="",
            energy="",
        )
    )
csv.DictWriter(
    open(ROOT / "catalog.csv", "w", newline=""), fieldnames=list(man[0])
).writeheader() or None
with open(ROOT / "catalog.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(man[0]))
    w.writeheader()
    w.writerows(man)
with open(ROOT / "tags.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(tags[0]))
    w.writeheader()
    w.writerows(tags)
print(
    len(man),
    "files;",
    sum(1 for m in man if m["composition_rights"] == "public-domain"),
    "with public-domain compositions;",
    len({t["composition_title"] for t in tags}),
    "distinct works",
)
