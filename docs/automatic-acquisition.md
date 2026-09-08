# Automatic library acquisition

The appliance checks reviewed MIDI sources daily at **04:30–04:45 America/New_York**.
`openorchestrion-acquire.timer` activates the bounded oneshot service; `Persistent=true`
runs a missed check after the appliance returns. This is separate from mDNS device
discovery and the nightly off-site backup. The importer does not restart playback.

See [music-sources.md](music-sources.md) for the verified source routes and disabled
sources. This finds additional files in existing collections as well as later
additions to their listings; it is not a claim that every collection publishes new
music regularly. Adding an entirely new website requires a reviewed adapter.

## Admission and duplicate history

1. Fetch only reviewed HTTPS hosts and paths, observing robots rules, crawl delays,
   TLS verification and retry/backoff. Never follow a redirect to an unreviewed host.
2. Compare SHA-256 against **all 25,893 original identities**, including the 20,061
   archived originals, plus every subsequent assessed download. Rejected originals
   cannot return through a different source.
3. Import to private staging, retaining source URL, title, license and attribution.
   Decode and measure MIDI in a separate bounded process. Reuse the complete-listening-v2
   quality rules: completeness evidence, instrument assignments, musical parts,
   expression, and playable event structure. Filename or source reputation alone
   does not qualify a file. A publisher label identifying a backing track, excerpt
   or incomplete file overrides a positive structural inference.
4. Compare qualified candidates' exact timed-playback fingerprints against the
   same history. Retagging a MIDI does not make it new. Different performances or
   arrangements of the same composition may remain; this is not fuzzy song-title
   deduplication.
5. Publish only qualified, nonduplicate candidates. Copy the immutable MIDI and
   sidecar, persist the quality explanation, add admission, then index that asset.
   Existing metadata, favorites, queues, collections and settings are not rewritten.
   No user review is required. No artistic or acoustic perfection is promised.

Saarland v2's exact download links carry captured publisher evidence of piano
performances, including a hash of the listing and downloaded file. Other enabled
sources require positive structural arrangement evidence. This does not confer an
open-redistribution license: downloads are recorded as Personal Library imports,
with their actual source terms retained. Public repository evidence contains no
downloaded music.

## Budgets and recovery

Default run: 20 MIDI candidates and 8 listing pages per enabled source, requests at
least one second apart, 20-second network timeout, 4 MiB page / 2 MiB MIDI limits,
10,000 inspected links per page and 100,000 queued URLs per source. The appliance
service caps runtime at 45 minutes, CPU at 40%, memory at 512 MiB, and uses idle I/O
priority. A decoder has 384 MiB address space, 45 CPU seconds and 60 wall seconds.
Acquisition defers below 512 MiB free disk. Pending URLs survive each work budget;
visited listings become due weekly, downloaded candidates monthly. Known hashes
are still rejected immediately. HTTP failures back off; Retry-After is respected
for queued requests. A source failure does not stop other sources.

`library/acquisition.sqlite3` retains duplicate history, full decision records,
source cursors, queued URLs and run reports. It is included in appliance backup and
restore. Current state is read at `GET /api/library/acquisition` and shown under
**Playback & devices → Finding new music**, including disabled sources and failures.
An unfinished run older than the service budget is shown as interrupted.

`/var/lib/openorchestrion/acquisition/` holds private staging and publication
journals. Journal writes are fsynced before publication; interrupted additions roll
forward before another scan. A process-owned stale acquisition lock can be recovered
automatically; an unknown/full-curation lock is never stolen. Existing hash collisions
fail closed. Old orphan staging is removed after seven days; unpublished journal
inputs are retained. Assessment process/software failures retain candidates for retry
instead of marking their music low quality. Rejected download bytes are removed after
their measurements and reason are recorded; original archived files are untouched.

Acquisition and backup share a snapshot lock: an overlapping snapshot fails with a
retry message instead of capturing mismatched library files and duplicate history.

Pause the acquisition service as well as other library writers before full curation,
restore, or manual catalog maintenance. A later scan reconciles a published addition
missing from a concurrently rebuilt catalog. The normal backup contains completed
library additions and their SQLite decision history; private pending staging is not
a portable backup payload. On recovery from backup those pending downloads are retried
from the saved discovery frontier.

## Installation and operation

### New public installation

A fresh installation does not need the reference owner's private evidence archive.
Run `openorchestrion-acquire --init-empty` as the service user to create v2
admission and quality/catalog databases. It refuses existing music and never
resets prior rejections. Run a bounded scan first; see [Getting started](getting-started.md).

To enable recurring scans, export deployment templates with
`openorchestrion-deploy --output-dir /tmp/openorchestrion-deploy`, then install
`openorchestrion-acquire.service` and `openorchestrion-acquire.timer` from that
directory into `/etc/systemd/system/`. Create the acquisition state directory
owned by the service user, reload systemd and enable the timer as below.
The timer uses the reference timezone explicitly; change `OnCalendar` locally
if another schedule is desired. Downloads are personal-library imports, not
a license to redistribute files.

### Existing reference collection

The wheel includes the command and unit files. On this appliance, seed history once
from the verified final-curation evidence **before the first acquisition**:

```sh
sudo install -d -o openorchestrion -g openorchestrion -m 0750 /var/lib/openorchestrion/acquisition
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-acquire \
  --seed-zip /var/tmp/openorchestrion-quality-release/library-quality-v2-evidence.zip \
  --facts-sha256 cd0cee2c3e9f71d7386bf486fdbf3307f7a9d33e15c9f4dab43c7ee8528b8fed
sudo install -m 0644 /opt/openorchestrion/venv/lib/python3.13/site-packages/openorchestrion/deployment/openorchestrion-acquire.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openorchestrion-acquire.timer
sudo systemctl start openorchestrion-acquire.service
```

The seed verifies its checksum and exact original inventory. Do not re-seed after
new additions; restore the acquisition database with the library instead. Uncovered
manual imports cause a clear stop until their identity/fingerprint history is supplied.

```sh
systemctl list-timers openorchestrion-acquire.timer
journalctl -u openorchestrion-acquire.service --since yesterday
/opt/openorchestrion/venv/bin/openorchestrion-acquire --status
sudo systemctl disable --now openorchestrion-acquire.timer
```

CLI work budgets can be overridden with `--limit`, `--page-limit` and repeatable
`--source`; do not run concurrently with the timer. The worker lock prevents overlap.
Disabled adapters remain disabled even when explicitly selected. Developers must
test a source's actual MIDI bytes, not just its homepage, before enabling it.

## Evidence

[Source probes](evidence/acquisition/midi-downloads.json) record actual downloaded
MIDI headers and hashes. [The isolated live-source rehearsal](evidence/acquisition/rehearsal.json)
admitted three files and rejected six candidates without changing production.
`tests/test_acquisition.py` covers real MIDI, duplicate history, publication recovery,
metadata collisions, source failures, work budgets, source URL restrictions, worker
failure, publisher partial labels, and backup restoration. Release results are in
[the deployment report](evidence/acquisition/deployment.json).


The first production check examined 86 downloads: **29 admitted, 50 not qualified,
7 duplicates**. The playable library increased from **5,832 to 5,861**. The original
25,893-file audit and 20,061 archived originals did not change. All five enabled
sources completed successfully. The final installed wheel passes 726 tests and
installed-wheel smoke; all 107 packaged runtime files match the source. Its SHA-256
is `79c78b21875e165195d4c4b163182ea2812f4446ab7f4237a037fc0554c3a0d1`.
The first live run preceded the final backup-overlap guard; that additional guard
passed its regression test and is included in the final installed wheel.
