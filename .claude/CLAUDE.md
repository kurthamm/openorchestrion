# OpenOrchestrion — Claude Code project context

## Layout
- `src/openorchestrion/` — FastAPI app (`app.py`), API (`api/`), playback engine (`playback/`), MIDI analysis/routing (`midi/`), library import/curation (`library/`), web UI (`web/`, no build step), deployment templates (`deployment/`).
- `tests/` — run `pytest -q` for the canonical suite. Also `ruff check --select E4,E7,E9,F .` and `python .github/scripts/validate_repo.py`.
- `docs/` — living architecture docs indexed by `docs/README.md`; `docs/adr/` decisions; `ROADMAP.md`, `PROJECT_STATUS.md`.
- `music/starter/` — verified-open starter catalog with `catalog.csv` (rights) and `tags.csv` (metadata). Import it with `--from-csv`, never as a bare directory.
- `tools/acquire/` — historical bulk acquisition scripts. Current qualified acquisition uses `openorchestrion-acquire` and `docs/automatic-acquisition.md`; do not rerun historical bulk imports against production.

## Reference appliance (as of 2026-09-07)

Read `docs/developer-handoff.md`, `docs/next-steps.md` and `docs/repository-maintenance.md` before changing the deployment. They contain the current release, verification and deferred work.
- Raspberry Pi 5 "openOrchestrion", reachable over Tailscale as `kurt@openorchestrion`; the service listens on port 8000 (LAN allowed via ufw; Tailscale allowed).
- Keyboard today: Casio WK-220 (USB, ALSA `hw:2,0,0`, client 24). CT-X700 is unavailable as of September 7. Its validation and `docs/two-engine-orchestration.md` implementation are deferred until the owner resumes that work.
- Install/upgrade: `cd ~/openorchestrion && git pull && sudo sh src/openorchestrion/deployment/install-appliance.sh --package "$PWD" --mode headless`. **This briefly restarts the service**. Queues, playlists, stations and settings are durable; playback restores stopped. The installer prepares dependencies before stopping the old service and rolls back its runtime/units on install or health failure. Tell the owner before interrupting listening.
- Library root `/var/lib/openorchestrion/library` (service user `openorchestrion`, mode 0750). Import staging must be world-readable, e.g. `/srv/openorchestrion-import/` (home dirs are private on Raspberry Pi OS). Run `openorchestrion-import-midi`, `openorchestrion-tag`, `openorchestrion-reindex` as the service user; run `openorchestrion-smoke` with sudo.
- Use the documented acquisition/admission locking and service-user commands. Do not bypass the quality gate or run competing bulk publishers to increase import throughput.
- Historical acquisition inventory before admission curation: starter (16) + MAESTRO v3 (1,276 performances, quality A) + Mutopia (5,195 files, 4,374 verified-open, 1,430 orchestral) + BitMidi top 20,000 by plays + Wikimedia Commons (~1,082). Curated tags come from `tools/acquire/curate_tags.py` / `curate_bitmidi.py`.

The original inventory was **25,893** files. The final v2 cull retained **5,832** and archived **20,061**, preserving every original. The first nightly acquisition admitted another **29**, so the personal system library contains **5,861** as of this record. Future admitted acquisitions can increase that count; use the live API for current totals. The public starter catalog is a separate **18-file** redistributable set, not the owner's personal library. Follow `docs/library-quality-publication.md`, `docs/automatic-acquisition.md` and the current admission manifest. Never republish historical v1 admission or archived material over v2.

## Behaviour notes learned on hardware
- Every track starts from GM defaults (`reset_channels`): files without Program Change are piano, not whatever the previous track left.
- Kernel `Midi Through` is never an output; hot-plug is detected via device presence plus the ALSA sequencer subscription table (`/proc/asound/seq/clients`); the port is opened with python-rtmidi directly (mido's `client_name` makes a *virtual* port).
- Orchestral score exports (LilyPond) get automatic voicing when a queue request omits `rendering`; explicit `ORIGINAL` disables it.
- Master volume scales CC7, never velocity; it is persisted with player settings. The keyboard's physical volume knob remains an independent audio-level control.
- Stations rank rather than filter: a small genre pads its queue with the nearest other material.

## Owner priorities
- Correct instruments above all; real human performances (MAESTRO) sound far better on the Casio than score exports.
- Prioritizes a smaller, high-quality library with correct MIDI instrumentation and usable discovery. AI activation, new-keyboard/two-engine implementation, and volume changes are outside the current release scope. See `docs/next-steps.md`.
- Warn before anything that stops playback.
