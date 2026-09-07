# Next work — issue and implementation review, 7 September 2026

Reviewed the seven open GitHub issues, the roadmap, current deployed source, and issue comments. The roadmap is a capability plan, not a completion checklist: many capabilities in it already exist.

## Corrected hardware baseline

[Issue #1's final WK-220 report](https://github.com/kurthamm/openorchestrion/issues/1#issuecomment-5564036325) records completion of its hardware checklist on September 6, on software `817e978`: audible playback, velocity, sustain, program/bank changes, multichannel/percussion, polyphony stress, expressive piano, sustained playback and reconnect. This is previously reported evidence, not a new test of the redesigned release. The CT-X700 named in issue #1 still needs its own validation. The current API reports one ready `CASIO USB-MIDI` output; that generic endpoint name alone does not establish the model.

## Recommended order

1. **Integration completed.** [PR #85](https://github.com/kurthamm/openorchestrion/pull/85) merged the reliability, library-admission and listening-room changes into `main`, preserving independent acquisition tools and `docs/two-engine-orchestration.md`. CI passed on Python 3.11–3.13, and the primary Pi checkout now follows main. See the [release record](single-keyboard-release-2026-09.md).
2. **Current headless timing milestone completed — [#6](https://github.com/kurthamm/openorchestrion/issues/6).** Three corrected idle checks, three loaded checks and a full 120-minute WK-220 loaded run passed all software targets on September 7. The release record retains raw reports, invalid earlier attempts, environment evidence and Auto Power Off setup. Kiosk, physical two-output and acoustic measurements remain separate pending evidence; this does not close all of #6.
3. **Consolidate the current single-keyboard experience.** Address reproducible defects and documentation gaps in the existing WK-220 setup; preserve the curated library and current playback behavior.

## Deferred until the new keyboard is available

The owner confirmed on September 7 that the CT-X700 is not available and this work is for later. **Do not start #84 orchestration implementation, a MIDI Orchestra UI, CT-X700 validation under #1, or physical two-engine tests now.** Keep the [two-engine plan](https://github.com/kurthamm/openorchestrion/blob/main/docs/two-engine-orchestration.md) as future design context. Virtual destinations may still be used by existing regression tests, but they do not advance this deferred feature into the current work queue.

For #6, run only load profiles supported by the current Pi/WK-220 setup. Record any unavailable kiosk or physical two-output profile as pending; do not claim completion of the full hardware benchmark from a software-only result.

When this deferred work resumes, the orchestration UI should extend the new performance detail/settings surfaces with a visible parts-to-engines plan and estimated load, using existing queue/player controls. It is deterministic and does not require enabling AI. Actual timbre-affinity ratings should follow listening evidence; initial configured scores remain provisional.

## Remaining open lanes

| Issue | Status and priority |
| --- | --- |
| [#64 — starter chamber/orchestral repertoire](https://github.com/kurthamm/openorchestrion/issues/64) | Expand the verified-open starter collection with complete arrangements and per-file provenance. This is separate from the private 20,549-performance listening library; it is not a mandate for another bulk import. |
| [#10 — white paper and project site](https://github.com/kurthamm/openorchestrion/issues/10) | Publication work, separate from the Pi control website just redesigned. Update software claims now; add hardware media/results only with evidence. |
| [#8 — enclosure and BOM](https://github.com/kurthamm/openorchestrion/issues/8) | Follow a stable physical arrangement and power/cabling/cooling requirements. |
| [#11 — complementary Yamaha engine](https://github.com/kurthamm/openorchestrion/issues/11) | Later expansion. The newer #84 reference plan prioritizes the two Casios; reconcile the older Yamaha lane rather than purchasing or implementing against it automatically. |

AI remains deferred at the owner's request. Integration and current-keyboard timing work were subsequently authorized and are recorded in the release document. No provider or new-keyboard feature was activated; the broader hardware issues are not closed by these software/headless results.
