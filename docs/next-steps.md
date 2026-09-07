# Next work — issue and implementation review, 7 September 2026

Reviewed the seven open GitHub issues, the roadmap, current deployed source, and issue comments. The roadmap is a capability plan, not a completion checklist: many capabilities in it already exist.

## Corrected hardware baseline

[Issue #1's final WK-220 report](https://github.com/kurthamm/openorchestrion/issues/1#issuecomment-5564036325) records completion of its hardware checklist on September 6, on software `817e978`: audible playback, velocity, sustain, program/bank changes, multichannel/percussion, polyphony stress, expressive piano, sustained playback and reconnect. This is previously reported evidence, not a new test of the redesigned release. The CT-X700 named in issue #1 still needs its own validation. The current API reports one ready `CASIO USB-MIDI` output; that generic endpoint name alone does not establish the model.

## Recommended order

1. **Integrate the already-deployed work.** The reliability, library-admission and listening-room changes are published on `codex/listening-room-redesign`, but not merged into `main`. Reconcile against current main, retain independent planning work such as `docs/two-engine-orchestration.md`, run CI on the integration result, then establish one shared development baseline. This review does not merge branches or close issues.
2. **Complete the loaded Pi timing evidence — [#6](https://github.com/kurthamm/openorchestrion/issues/6).** The 14 synthetic fixtures and benchmark harness are implemented. Follow `pi-timing-benchmark.md`: named load profiles, short repeatability passes, 120-minute endurance runs, temperature/undervoltage evidence and retained JSON results. Software scheduler jitter is distinct from physical MIDI-to-audio latency.
3. **Implement deterministic two-engine orchestration — [#84](https://github.com/kurthamm/openorchestrion/issues/84).** The [current plan](https://github.com/kurthamm/openorchestrion/blob/main/docs/two-engine-orchestration.md) targets CT-X700 foreground and WK-220 support. Start with configurable profiles and reliable physical-device binding, per-engine planning limits, whole-performance solo-piano routing, support-engine drums, explainable part assignments, manual overrides and single-engine fallback. Build/test policy with virtual destinations; validate dual-device behavior when both keyboards are available. Existing routing and one shared scheduler are the foundation, not work to replace.
4. **Validate the CT-X700 — [#1](https://github.com/kurthamm/openorchestrion/issues/1).** Repeat the device-specific checklist when it arrives and measure relative timing before claiming two-engine acoustic synchronization. Do not repeat the WK-220 investigation from zero or transfer its sound evidence to a different model.

The orchestration UI should extend the new performance detail/settings surfaces with a visible parts-to-engines plan and estimated load, using existing queue/player controls. It is deterministic and does not require enabling AI. Actual timbre-affinity ratings should follow listening evidence; initial configured scores remain provisional.

## Remaining open lanes

| Issue | Status and priority |
| --- | --- |
| [#64 — starter chamber/orchestral repertoire](https://github.com/kurthamm/openorchestrion/issues/64) | Expand the verified-open starter collection with complete arrangements and per-file provenance. This is separate from the private 20,549-performance listening library; it is not a mandate for another bulk import. |
| [#10 — white paper and project site](https://github.com/kurthamm/openorchestrion/issues/10) | Publication work, separate from the Pi control website just redesigned. Update software claims now; add hardware media/results only with evidence. |
| [#8 — enclosure and BOM](https://github.com/kurthamm/openorchestrion/issues/8) | Follow a stable physical arrangement and power/cabling/cooling requirements. |
| [#11 — complementary Yamaha engine](https://github.com/kurthamm/openorchestrion/issues/11) | Later expansion. The newer #84 reference plan prioritizes the two Casios; reconcile the older Yamaha lane rather than purchasing or implementing against it automatically. |

AI remains deferred at the owner's request. None of this review changes playback, starts an endurance test, activates a provider or claims an issue is complete.
