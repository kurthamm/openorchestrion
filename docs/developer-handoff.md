# Developer handoff — 7 September 2026

## Automatic acquisition release

[Runbook](automatic-acquisition.md), [source access research](music-sources.md#verified-automatic-source-registry--2026-09-07),
and [deployment evidence](evidence/acquisition/deployment.json) describe the current
release. It includes PR #93 core player operations. The nightly timer is enabled;
first run added 29 new performances, taking the available library from **5,832 to
5,861**, with all 25,893 original identities retained in duplicate history.
The original curation counts below are historical and have not been recategorized.

Enabled sources: Saarland v2, Classical Archives' free Schwob collection, VGMusic,
Mutopia and MIDKAR. Four disabled sources and their access reasons are visible in
the app. This is a bounded autonomous collector, not a human-review queue or a
promise of daily new releases. Preserve `library/acquisition.sqlite3` with backups;
do not delete rejected identities or bypass the admission list for future imports.
Stop the acquisition timer/service before full curation or restore. Ordinary nightly
acquisition adds files without restarting the player. The backup snapshot lock
prevents inconsistent capture during admission.

Validation: 726 tests, Ruff, repository contracts, browser checks, packaged virtual
server smoke and a live systemd acquisition run. The 107-file installed package
matches the repository. Final wheel SHA-256:
`79c78b21875e165195d4c4b163182ea2812f4446ab7f4237a037fc0554c3a0d1`.

## Complete-listening v2 release

The [quality publication record](library-quality-publication.md) supersedes the v1
selection and the earlier publisher-only candidate. The full 25,893-original scan
qualifies **5,832 performances** and retains **20,061 originals in the archive**.
The manifest includes source evidence, structural inference, reason codes and
input hashes for each file; 129 earlier exclusions qualify under the new evidence.
Read the evidence summary and deployment record before modifying the library.

The release adds sostenuto-aware quality facts, independent arrangement evidence,
reversible publication/recovery, a read-only qualification panel and backup of the
v2 allowlist/evidence database. It preserves the other developer's saved playlists,
queue editing, modes, seek, sleep, restart persistence and Cloudflare protection.
Do not re-run the older v1 publisher or remove the admission manifest to import.
New acquisitions require assessment before catalog admission. Normal application
backups cover the active library; preserve the separate full archive as well.

## Historical playback-readiness release

The [playback-readiness release](library-playback-readiness.md) adds policy-aware
What will play previews, all-library part facts, faster filters/repeat preparation,
and unknown-meta timing repair. Its wheel is installed with **91 matching runtime
files**. It supersedes the prior wheel identities below. The seven affected
analysis blocks were repaired without changing descriptive metadata or MIDI bytes;
the final 20,549-file audit has zero count/peak/duration mismatches. Validation:
676 tests, contracts, Ruff, browser checks, installed-wheel smoke, and the short
loaded live check retained in the release evidence. The existing two-hour result
belongs to its earlier build. The prepared song was restored using AUTO at the
owner's discretion; volume 33 and stopped state were verified.

## Published integration baseline

Start from **`main`**. [PR #85](https://github.com/kurthamm/openorchestrion/pull/85) merged the Pi reliability fixes, library admission curation, listening-room redesign, and benchmark repair as `cff40bf5693078133dc7ed5453d00978a5baaaa5`. Main's independent acquisition tools and future orchestration plan were preserved. The primary Pi checkout was fast-forwarded to this shared baseline; the earlier branches remain available.

The UI relies on the browse, facets, performance-details and atomic queue-clear endpoints. Do not copy just the HTML/CSS onto an older backend. See the [single-keyboard release record](single-keyboard-release-2026-09.md) for exact wheel identity, CI, timing evidence and limitations.

- [Listening room design, API additions and release verification](web-listening-room.md)
- [Library curation and admission policy](library-curation.md)
- [Earlier implementation review and fixes](implementation-review.md)
- [Current project status](../PROJECT_STATUS.md)

The deployed runtime source was committed on the Pi as `c02a050a061bfefb99e3668ca6c54685f522ae84`. The equivalent published GitHub commit is `bdf4ace22a1ca5325ab3c83a218eb70ded6d5075`. Their commit IDs differ because their parent histories differ; both have the exact tree `59426a5e6799e5b99fef418b0f5b632d9e6f489f`. Those are historical redesign identities. PR #85 additionally fixes the separate benchmark CLI; all playback-server and browser modules remain byte-identical to that deployed redesign. That earlier wheel is recorded in the single-keyboard release document.

## Deployment and data boundaries

The Pi checkout is `/home/kurt/openorchestrion`; production runs the installed wheel under `/opt/openorchestrion/venv`, not an editable checkout. A Git commit alone does not deploy changes. Both application and discovery services were verified active after release. The current wheel hash is recorded in the quality publication evidence; the listening-room document retains the earlier release and rollback history.

The v2 library has **5,832 performances**. The **20,061 other originals remain archived**, not deleted. Admission is enforced during full rebuild and individual reindex. Do not bypass `listening-admission.json`, reimport archived copies into the active catalog, or regenerate descriptive metadata as a side effect of UI development. Favorites belong in the sidecars, and the catalog remains rebuildable.

AI is deferred in the current interface. The existing provider/intent/station APIs remain compatible, but there is no assistant panel and the new browser does not call the Concierge. Automatic voicing is deterministic playback behavior, not an AI feature. Any future assistant must remain optional and use ordinary reviewable queue proposals.

## Reproduce the deployment check

From the Pi repository, compare every source runtime file with the installed package without importing or executing application code:

```sh
python3 scripts/verify-deployed-source.py \
  --installed /opt/openorchestrion/venv/lib/python3.13/site-packages/openorchestrion
```

The earlier endurance release had **88 matching runtime files**; the readiness release has **91**, with no missing or differing source files. The script exits nonzero for an empty source directory, missing files or mismatched bytes. Documentation and this verification script are not runtime package files and do not require a service restart.

Run the repository's Python tests, Ruff correctness checks, `.github/scripts/validate_repo.py`, and `.github/scripts/test-web.mjs` for relevant implementation changes. The deployed redesign passed **660 Python tests**, repository contracts and an installed-wheel smoke test. Browser evidence covers search/filter/page flows, favorites, MIDI details, virtual playback and phone/tablet/desktop layouts. These are recorded results, not claims that future commits automatically pass.

Use a separate copied library and history database with injected `VirtualMidiOutput` for mutation tests. Do not test play, clear, favorites or reindex against production merely to verify a UI change. Before deploying, check for active playback, a prepared queue and library writers; preserve any active work. Keep a rollback wheel and verify both services after installation.

## Remaining evidence and known limits

- At redesign deployment no keyboard was connected; it has since returned as a ready CASIO USB-MIDI output. Issue #1 reports the WK-220 checklist passed on September 6 on an earlier build. See [the corrected next-work review](next-steps.md) for that evidence. The current headless WK-220 loaded 120-minute software timing run passed all targets on September 7; raw evidence and limitations are in the release record. Local Chromium kiosk load, CT-X700 validation and two-engine acoustic synchronization remain outstanding.
- Arrangement, creator and source labels still reflect imperfect upstream metadata. The detail view deliberately distinguishes catalog labels from encoded MIDI evidence; the UI does not certify musical completeness.
- Full-library facet counts are not counts for the current filtered subset.
- Legacy UI modules and historical UX documents remain for compatibility/context. The listening-room document describes the current browser experience; old prompt-first and automatic setup-redirect descriptions are superseded.

Update this handoff and project status when the deployment, shared development baseline, data policy, AI scope or hardware evidence changes. Record tests actually run and distinguish deployed code from planned or branch-only work.
