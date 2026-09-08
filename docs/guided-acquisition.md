# Add music from the browser

**Music library → Add music** and **Playback & devices → Find new music** lead to
the same guided screen. Empty Discover and Library views link directly to it.
Saarland Music Data v2 is preselected for an initial recorded-piano check. Available
sources and their terms come from the reviewed acquisition registry; disabled
sources are explained separately and cannot be submitted.

Select one to five available sources and click **Find qualifying music**. This
authorizes one bounded personal-library download run, not a recurring subscription.
The server assesses at most five MIDI candidates and four index pages per source.
The screen shows progress, additions, quality exclusions, duplicates and source
failures/backoff. A zero-addition result is a valid outcome. You can browse/play
existing music or leave the browser while the server works. Return to Add music
to see the durable result. Retry retains deduplication and source waiting periods.

The source has to meet existing rights/access rules and the unchanged v2 quality
policy. Titles use the shared metadata normalizer. MIDI parsing runs in the existing
resource-limited worker. The guided parent runs at reduced process priority and is
terminated with its child group after 30 minutes or application shutdown. An
interrupted result is shown honestly; previously admitted songs remain available.

## API and lifecycle

- `GET /api/library/acquisition/job`: read-only job state and reviewed source choices.
  It never initializes or downloads music.
- `POST /api/library/acquisition/job`, JSON `{"sources":["smd"]}`: accepts a bounded
  server job (202). Invalid, duplicate, disabled or arbitrary URL inputs are refused.
  Foreign browser origins are refused; the normal household-LAN trust model still applies.
- `GET /api/library/acquisition` remains the CLI/nightly source-report endpoint.

The server owns `AcquisitionJobs`, starts a separate process, and shuts it down in
the application lifespan. A file lock prevents concurrent browser launches across
server processes. A library-root `.acquisition-run.lock` serializes all current
CLI/nightly/browser scans, even if callers choose different staging directories.
The existing snapshot/publication locks and journal remain authoritative for data
publication. Older workers using the old staging-only lock must be stopped at upgrade.

Job state lives at `library/web-acquisition.json`; PID, boot and process-start
identity distinguish a live job from a stale record. The normal acquisition
database retains progress, source cursors, decisions and duplicate history. On the
reference layout, staging remains `/var/lib/openorchestrion/acquisition`.

Only a genuinely empty library can be bootstrapped automatically. An existing
unseeded collection is refused and remains untouched; use the documented operator
curation/seed procedure. No browser operation replaces admission, enables systemd
timers, writes service credentials or restores a backup.
