# Pi timing evidence, September 7

- `headless-idle-sync-*.json`: invalid original collector measurements; startup reset messages were mistaken for notes.
- `corrected-headless-idle-sync-*.json`: three passing diagnostic baseline reports from the corrected wheel.
- `headless-active-one-output-sync-*.json` and `headless-active-one-output-120m.json`: final passing reports after operator Auto Power Off setup.
- `loaded-environment.json`, `operator-setup.json`, `loaded-result.json`: final run identity, operator confirmation and outcome. The result's playback field precedes cleanup; final state was independently checked stopped with the queue preserved.
- `loaded-observation-summary.json`: aggregate of complete local observations; source hash and percentile method included. Full observations remain on the Pi under `/var/tmp/openorchestrion-release-20260907/post-auto-power-off/observations.jsonl`.
- `interrupted-attempt.json`, `monitor-interrupted-attempt.json`: external monitor wrongly interpreted volume updates as transport interruptions. These are harness failures, not scheduler target misses.
- `setup-interrupted-result.json` and `setup-interruption.json`: explicitly terminated earlier test after the owner performed the required startup; its negative exit is not a scheduler failure.
- `baseline-environment.json`: earlier machine inventory, with private IPs omitted from this published copy.
- `run-profile.py`: archived exact script for the final run, including fixed paths specific to this appliance. This is evidence, not a general-purpose CLI. Do not rerun it against an occupied queue or reuse its output directory; create an isolated run directory and obtain an uninterrupted hardware window first.

See [the release record](../../../single-keyboard-release-2026-09.md) for interpretation. No acoustic timing, gapless playback or Chromium kiosk result is claimed.
