"""Wikimedia Commons Category:MIDI files -> OpenOrchestrion import set."""

import collections
import csv
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(sys.argv[1])
(OUT / "files").mkdir(parents=True, exist_ok=True)
API = "https://commons.wikimedia.org/w/api.php"
UA = {
    "User-Agent": "OpenOrchestrion library builder/0.1 (https://github.com/kurthamm/openorchestrion; kurt@hamm.me)"
}
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
LIC = {
    "Public domain": (
        "public-domain",
        "https://creativecommons.org/publicdomain/mark/1.0/",
        "permitted",
    ),
    "CC0": ("CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/", "permitted"),
    "CC BY 3.0": (
        "CC-BY-3.0",
        "https://creativecommons.org/licenses/by/3.0/",
        "permitted-with-attribution",
    ),
    "CC BY 4.0": (
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
        "permitted-with-attribution",
    ),
    "CC BY-SA 3.0": (
        "CC-BY-SA-3.0",
        "https://creativecommons.org/licenses/by-sa/3.0/",
        "permitted-with-attribution",
    ),
    "CC BY-SA 4.0": (
        "CC-BY-SA-4.0",
        "https://creativecommons.org/licenses/by-sa/4.0/",
        "permitted-with-attribution",
    ),
}


def api(**params):
    params.update(format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(6):
        try:
            time.sleep(0.6)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if i == 5:
                raise
            time.sleep(20 if "429" in str(e) else 2 * (i + 1))


titles, cont = [], {}
while True:
    d = api(
        action="query",
        list="categorymembers",
        cmtitle="Category:MIDI files",
        cmtype="file",
        cmlimit=500,
        **cont,
    )
    titles += [m["title"] for m in d["query"]["categorymembers"]]
    if "continue" not in d:
        break
    cont = d["continue"]
print(len(titles), "files listed", flush=True)


def info(batch):
    d = api(
        action="query", prop="imageinfo", iiprop="url|sha1|size|extmetadata", titles="|".join(batch)
    )
    return list(d["query"]["pages"].values())


pages = []
with ThreadPoolExecutor(1) as pool:
    for res in pool.map(info, [titles[i : i + 50] for i in range(0, len(titles), 50)]):
        pages += res


def strip(html):
    return re.sub(r"<[^>]+>", "", str(html) if html is not None else "").strip()


def fetch(page):
    ii = page["imageinfo"][0]
    url = ii["url"]
    meta = {k: strip(v.get("value")) for k, v in ii.get("extmetadata", {}).items()}
    name = re.sub(r"[^\w.\- ]+", "_", page["title"].replace("File:", ""))
    if (OUT / "files" / name).exists():
        data = (OUT / "files" / name).read_bytes()
    else:
        for i in range(6):
            try:
                time.sleep(0.6)
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers=UA), timeout=120
                ) as r:
                    data = r.read()
                    break
            except Exception as e:
                if i == 5:
                    raise
                time.sleep(20 if "429" in str(e) else 2 * (i + 1))
    (OUT / "files" / name).write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    short = meta.get("LicenseShortName", "")
    lic = LIC.get(short)
    title = re.sub(r"\.midi?$", "", page["title"].replace("File:", ""), flags=re.I)
    m = re.search(r"\bby ([A-Z][\w.\-' ]+?)(?:\.|$|,|\))", title)
    composer = m.group(1).strip() if m else ""
    manifest = dict(
        path=name,
        sha256=sha,
        rights_status="personal",
        source_reference="https://commons.wikimedia.org/wiki/"
        + urllib.parse.quote(page["title"].replace(" ", "_")),
        source_label="Wikimedia Commons",
        license=lic[0] if lic else (short or "unknown"),
        license_url=lic[1]
        if lic
        else (meta.get("LicenseUrl") or "https://commons.wikimedia.org/wiki/Commons:Licensing"),
        attribution=(
            meta.get("Attribution")
            or meta.get("Artist")
            or meta.get("Credit")
            or "Wikimedia Commons contributor"
        )[:300],
        composition_rights="unknown",
        composition_rights_basis="",
        redistribution=lic[2] if lic else "unknown",
        verified_by="kurthamm via commons_crawl",
        verified_at=NOW,
    )
    tags = dict(
        sha256=sha,
        title=title[:200],
        composer=composer,
        year_composed="",
        era="",
        performance_type="",
        genres="",
        moods="",
        themes="",
        instrumentation="",
        familiarity="",
        energy="",
    )
    return manifest, tags


rows, fails = [], []
with ThreadPoolExecutor(1) as pool:
    for page, res in zip(
        pages, pool.map(lambda p: (lambda: fetch(p))() if "imageinfo" in p else None, pages)
    ):
        if res:
            rows.append(res)
        else:
            fails.append(page.get("title"))
with open(OUT / "catalog.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0][0]))
    w.writeheader()
    w.writerows(m for m, _ in rows)
with open(OUT / "tags.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0][1]))
    w.writeheader()
    w.writerows(t for _, t in rows)

print(
    "DONE",
    len(rows),
    "files;",
    len(fails),
    "skipped; licenses:",
    collections.Counter(m["license"] for m, _ in rows).most_common(8),
)
