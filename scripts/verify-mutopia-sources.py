"""Re-fetch referenced publisher bundles; match bytes and identify explicit scores/parts.

Unclear filenames/instrumentation remain unresolved. Network failure never admits.
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from openorchestrion.library.midi_scan import read_events

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("library_root", type=Path)
parser.add_argument("cache_directory", type=Path)
args = parser.parse_args()
ROOT = args.library_root
CACHE = args.cache_directory
CACHE.mkdir(parents=True, exist_ok=True)
SOLO = {
    "piano",
    "piano solo",
    "organ",
    "harpsichord",
    "clavichord",
    "keyboard",
    "guitar",
    "guitar solo",
    "flute",
    "violin",
    "cello",
    "violoncello",
    "fortepiano",
    "harpsichord or piano",
    "piano or harpsichord",
}
PART = re.compile(
    r"(?i)(?:^|[-_. ])(?:violin[12]?|viola|cello|violoncello|flute|oboe|clarinet|bassoon|horn|trumpet|trombone|soprano|alto|tenor|bass|right|left|rh|lh)(?:[-_. 0-9]|$)"
)
FULL = re.compile(
    r"(?i)(?:^|[-_. ])(?:score|full|complete|quartet|quatuor|quintet|trio|orchestra|gesamt)(?:[-_. 0-9]|$)"
)


def fetch(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in (
        "www.mutopiaproject.org",
        "mutopiaproject.org",
    ):
        raise ValueError("untrusted publisher URL")
    path = CACHE / hashlib.sha256(url.encode()).hexdigest()
    if path.exists():
        return path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "OpenOrchestrion source verification"})
    with urllib.request.urlopen(req, timeout=20) as response:
        if urllib.parse.urlparse(response.url).hostname not in (
            "www.mutopiaproject.org",
            "mutopiaproject.org",
        ):
            raise ValueError("unexpected redirect")
        raw = response.read(20_000_001)
    if len(raw) > 20_000_000:
        raise ValueError("source bundle too large")
    path.write_bytes(raw)
    return raw


def verify(item):
    url, local = item
    result = {}
    try:
        raw = fetch(url)
        rdf = ET.fromstring(raw)
        tags = {
            element.tag.rsplit("}", 1)[-1]: (element.text or "").strip() for element in rdf.iter()
        }
        mid = tags.get("midFile", "")
        instrumentation = tags.get("for", "").lower().strip()
        source = urllib.parse.urljoin(url, mid)
        blob = fetch(source)
        if mid.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                members = [
                    (n, archive.read(n))
                    for n in archive.namelist()
                    if n.lower().endswith((".mid", ".midi"))
                ]
        else:
            members = [(mid, blob)]
        for name, data in members:
            asset = "sha256:" + hashlib.sha256(data).hexdigest()
            if asset not in local:
                continue
            _, _, events = read_events(data)
            channels = {
                status & 15
                for _, _, _, status, payload in events
                if status < 240 and status >> 4 == 9 and payload[1] > 0
            }
            filename = Path(name).name
            partial = (
                bool(PART.search(filename))
                and instrumentation not in SOLO
                and len(members) > 1
                and len(channels) == 1
            )
            complete = instrumentation in SOLO and not re.search(
                r"(?i)(?:right|left|treble|bass|[rl]h)[-_. ]", filename
            )
            # A directly published sole MIDI is the score export, except when
            # its own filename contradicts that interpretation. Ensemble exports
            # must also contain more than one note-bearing channel.
            if len(members) == 1 and not partial and len(channels) >= 2:
                complete = True
            if FULL.search(filename) and not partial and len(channels) >= 2:
                complete = True
            result[asset] = {
                "completeness": "partial" if partial else "complete" if complete else "unresolved",
                "performance_capture": False,
                "source": source,
                "metadata_source": url,
                "metadata_sha256": hashlib.sha256(raw).hexdigest(),
                "bundle_sha256": hashlib.sha256(blob).hexdigest(),
                "member": name,
                "published_instrumentation": instrumentation,
                "bundle_midi_count": len(members),
                "sounding_channels": len(channels),
                "basis": "Exact publisher MIDI match; explicit solo-work/score export or named ensemble part",
                "arrangement": "solo_piano"
                if instrumentation in ("piano", "piano solo", "fortepiano") and complete
                else "published_score",
            }
        return result, None
    except Exception as exc:
        return {}, {"source": url, "error": str(exc)}


def main():
    groups = {}
    for path in list(ROOT.glob("assets/*.json")) + list(ROOT.glob("archive/*/assets/*.json")):
        doc = json.loads(path.read_bytes())
        provenance = doc.get("provenance", {})
        if provenance.get("source_label") == "Mutopia Project":
            groups.setdefault(provenance["source_reference"], set()).add(doc["asset_id"])
    evidence = {}
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, (found, error) in enumerate(pool.map(verify, sorted(groups.items())), 1):
            evidence.update(found)
            if error:
                errors.append(error)
            if i % 100 == 0:
                print(
                    json.dumps(
                        {
                            "sources": i,
                            "total": len(groups),
                            "matched": len(evidence),
                            "errors": len(errors),
                        }
                    ),
                    flush=True,
                )
                (CACHE / "mutopia-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (CACHE / "mutopia-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (CACHE / "errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
    print(
        json.dumps({"sources": len(groups), "matched": len(evidence), "errors": len(errors)}),
        flush=True,
    )


if __name__ == "__main__":
    main()
