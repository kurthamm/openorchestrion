# Developer handoff — 7 September 2026

## Start from the published implementation

The integration branch is **`codex/listening-room-redesign`**. It contains the earlier Pi reliability fixes and listening-library curation work, followed by the deployed redesign. It has been published to GitHub; publication does **not** mean it has been merged into `main`.

Fetch that branch before extending the deployed interface. Preserve its ancestry when integrating: the UI relies on the new browse, facets, performance-details and atomic queue-clear endpoints. Do not copy just the HTML/CSS onto an older backend.

- [Listening room design, API additions and release verification](web-listening-room.md)
- [Library curation and admission policy](library-curation.md)
- [Earlier implementation review and fixes](implementation-review.md)
- [Current project status](../PROJECT_STATUS.md)

The deployed runtime source was committed on the Pi as `c02a050a061bfefb99e3668ca6c54685f522ae84`. The equivalent published GitHub commit is `bdf4ace22a1ca5325ab3c83a218eb70ded6d5075`. Their commit IDs differ because their parent histories differ; both have the exact tree `59426a5e6799e5b99fef418b0f5b632d9e6f489f`. Subsequent handoff documentation and verification tooling do not change the deployed runtime.

## Deployment and data boundaries

The Pi checkout is `/home/kurt/openorchestrion`; production runs the installed wheel under `/opt/openorchestrion/venv`, not an editable checkout. A Git commit alone does not deploy changes. Both application and discovery services were verified active after release. The release wheel hash and retained rollback wheel are recorded in the listening-room document.

The admitted library has **20,549 performances**. The **5,344 excluded files remain archived**, not deleted. Admission is enforced during full rebuild and individual reindex. Do not bypass `listening-admission.json`, reimport archived copies into the active catalog, or regenerate descriptive metadata as a side effect of UI development. Favorites belong in the sidecars, and the catalog remains rebuildable.

AI is deferred in the current interface. The existing provider/intent/station APIs remain compatible, but there is no assistant panel and the new browser does not call the Concierge. Automatic voicing is deterministic playback behavior, not an AI feature. Any future assistant must remain optional and use ordinary reviewable queue proposals.

## Reproduce the deployment check

From the Pi repository, compare every source runtime file with the installed package without importing or executing application code:

```sh
python3 scripts/verify-deployed-source.py \
  --installed /opt/openorchestrion/venv/lib/python3.13/site-packages/openorchestrion
```

The September release has **88 matching runtime files**, with no missing or differing source files. The script exits nonzero for an empty source directory, missing files or mismatched bytes. Documentation and this verification script are not runtime package files and do not require a service restart.

Run the repository's Python tests, Ruff correctness checks, `.github/scripts/validate_repo.py`, and `.github/scripts/test-web.mjs` for relevant implementation changes. The deployed redesign passed **660 Python tests**, repository contracts and an installed-wheel smoke test. Browser evidence covers search/filter/page flows, favorites, MIDI details, virtual playback and phone/tablet/desktop layouts. These are recorded results, not claims that future commits automatically pass.

Use a separate copied library and history database with injected `VirtualMidiOutput` for mutation tests. Do not test play, clear, favorites or reindex against production merely to verify a UI change. Before deploying, check for active playback, a prepared queue and library writers; preserve any active work. Keep a rollback wheel and verify both services after installation.

## Remaining evidence and known limits

- No keyboard is connected. Physical sound, device bank/drum behavior, timing under hardware load and acoustic synchronization remain unverified.
- Arrangement, creator and source labels still reflect imperfect upstream metadata. The detail view deliberately distinguishes catalog labels from encoded MIDI evidence; the UI does not certify musical completeness.
- Full-library facet counts are not counts for the current filtered subset.
- Legacy UI modules and historical UX documents remain for compatibility/context. The listening-room document describes the current browser experience; old prompt-first and automatic setup-redirect descriptions are superseded.

Update this handoff and project status when the deployment, integration branch, data policy, AI scope or hardware evidence changes. Record tests actually run and distinguish deployed code from planned or branch-only work.
