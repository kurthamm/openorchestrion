# Player Workflows

OpenOrchestrion keeps the household player state in `player-state.db`, separate from the rebuildable music catalog. The database contains saved playlists, saved stations, the active queue, its current item and position, master volume, and playback modes. An orderly service restart silences MIDI output, records progress, and restores the session stopped at the saved position.

## Saved listening

- **Playlist:** an ordered snapshot of the current queue.
- **Station:** a reusable playback intent. In the web UI, the active library filters can be saved as a station and resolved against the current catalog each time it is loaded.
- Saved collections can be loaded, renamed through the API, or deleted. Names are unique without regard to case.

## Queue and transport

The queue supports individual reordering and removal, multi-select removal, and “play next.” The playback bar timeline is seekable. Seeking reconstructs MIDI controller/program state before continuing, so starting partway through a file does not depend on stale hardware state.

Repeat can target the current track or the queue. Shuffle chooses the next queued item. Continuous mode restarts selection at the end of the queue; it is useful for unattended listening. “Stop after this song” overrides automatic advance once and clears itself. The sleep timer stops and silences playback after 15, 30, 60, or 120 minutes and may be cancelled.

## Recovery and backup

Queue, position, volume, and repeat/shuffle/continuous settings are written after every mutation. Sleep timers are intentionally not restored after a service restart because their wall-clock intent is ambiguous after downtime. `player-state.db` is captured with SQLite's online backup API and validated during application-data restore.
