import hashlib
import json
from pathlib import Path

from openorchestrion.library.quality import analyze, decide


def test_new_ensemble_starters_remain_complete_expressive_and_correctly_voiced():
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root / "docs/evidence/repertoire/donizetti-quality.json").read_text())
    for row in evidence:
        raw = (root / "music/starter" / row["path"]).read_bytes()
        assert "sha256:" + hashlib.sha256(raw).hexdigest() == row["asset_id"]
        facts = analyze(raw)
        assert len(facts["parts"]) == 4
        assert [part["patches"][0]["program"] for part in facts["parts"]] == [41, 41, 42, 43]
        assert facts["duration"] > 300
        assert decide({"asset_id": row["asset_id"], "facts": facts},
                      {row["asset_id"]: row["evidence"][0]})["status"] == "qualified"
