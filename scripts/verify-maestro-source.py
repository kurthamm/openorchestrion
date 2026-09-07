"""Build content-hash evidence from the publisher's checksum-verified v3 archive."""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output_directory", type=Path)
root = parser.parse_args().output_directory
root.mkdir(parents=True, exist_ok=True)
url = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip"
expected = "70470ee253295c8d2c71e6d9d4a815189e35c89624b76d22fce5a019d5dde12c"
path = root / "maestro-v3.0.0-midi.zip"
if not path.exists():
    urllib.request.urlretrieve(url, path)
if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
    raise ValueError("publisher archive checksum mismatch")
evidence = {}
with zipfile.ZipFile(path) as archive:
    for name in archive.namelist():
        if name.lower().endswith((".mid", ".midi")):
            asset = "sha256:" + hashlib.sha256(archive.read(name)).hexdigest()
            evidence[asset] = {
                "completeness": "complete",
                "performance_capture": True,
                "basis": "Exact MIDI bytes match publisher-verified MAESTRO v3 individual performance",
                "source": url,
                "archive_sha256": expected,
                "member": name,
                "arrangement": "solo_piano",
            }
(root / "maestro-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps({"verified_performances": len(evidence), "archive_sha256": expected}), flush=True)
