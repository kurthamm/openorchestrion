# OpenOrchestrion — Claude Code project context

## Layout
- `src/openorchestrion/` — FastAPI app (`app.py`), API (`api/`), playback engine (`playback/`), MIDI analysis/routing (`midi/`), library import/curation (`library/`), web UI (`web/`, no build step), deployment templates (`deployment/`).
- `tests/` — pytest; `testrepo` runs the canonical suite. Also `ruff check --select E4,E7,E9,F .` and `python .github/scripts/validate_repo.py`.
- `docs/` — living architecture docs indexed by `docs/README.md`; `docs/adr/` decisions; `ROADMAP.md`, `PROJECT_STATUS.md`.
- `music/starter/` — verified-open starter catalog with `catalog.csv` (rights) and `tags.csv` (metadata). Import it with `--from-csv`, never as a bare directory.
- `tools/acquire/` — bulk library acquisition and curation scripts (Mutopia, MAESTRO, Wikimedia Commons, BitMidi).

## Reference appliance (as of 2026-09-06)
- Raspberry Pi 5 "openOrchestrion", reachable over Tailscale as `kurt@openorchestrion`; the service listens on port 8000 (LAN allowed via ufw; Tailscale allowed).
- Keyboard today: Casio WK-220 (USB, ALSA `hw:2,0,0`, client 24). CT-X700 is unavailable as of September 7. Its validation and `docs/two-engine-orchestration.md` implementation are deferred until the owner resumes that work.
- Install/upgrade: `cd ~/openorchestrion && git pull && sudo sh src/openorchestrion/deployment/install-appliance.sh --package "$PWD" --mode headless`. **This restarts the service and empties the in-memory queue** — do not run it while the owner is listening without telling them.
- Library root `/var/lib/openorchestrion/library` (service user `openorchestrion`, mode 0750). Import staging must be world-readable, e.g. `/srv/openorchestrion-import/` (home dirs are private on Raspberry Pi OS). Run `openorchestrion-import-midi`, `openorchestrion-tag`, `openorchestrion-reindex` as the service user; run `openorchestrion-smoke` with sudo.
- The importer is single-threaded (~80 files/min for large files); shard manifests and run 4 in parallel on the 4-core Pi.
- Historical acquisition inventory before admission curation: starter (16) + MAESTRO v3 (1,276 performances, quality A) + Mutopia (5,195 files, 4,374 verified-open, 1,430 orchestral) + BitMidi top 20,000 by plays + Wikimedia Commons (~1,082). Curated tags come from `tools/acquire/curate_tags.py` / `curate_bitmidi.py`.

The active listening library now contains **20,549 admitted performances**. Another 5,344 are archived; all 25,893 originals remain preserved. Follow `docs/library-curation.md` and the admission manifest when reindexing; do not restore archived material through a bulk import.

## Behaviour notes learned on hardware
- Every track starts from GM defaults (`reset_channels`): files without Program Change are piano, not whatever the previous track left.
- Kernel `Midi Through` is never an output; hot-plug is detected via device presence plus the ALSA sequencer subscription table (`/proc/asound/seq/clients`); the port is opened with python-rtmidi directly (mido's `client_name` makes a *virtual* port).
- Orchestral score exports (LilyPond) get automatic voicing when a queue request omits `rendering`; explicit `ORIGINAL` disables it.
- Master volume scales CC7, never velocity; it is not persisted across restarts yet.
- Stations rank rather than filter: a small genre pads its queue with the nearest other material.

## Owner priorities
- Correct instruments above all; real human performances (MAESTRO) sound far better on the Casio than score exports.
- Prioritizes a smaller, high-quality library with correct MIDI instrumentation and usable discovery. AI activation, new-keyboard/two-engine implementation, and volume changes are outside the current release scope. See `docs/next-steps.md`.
- Warn before anything that stops playback.
