# Raspberry Pi implementation review and reliability fixes

Review started September 6, 2026; fixes prepared September 7. Baseline:
`049bb45` on `feature/catalog-facets`, Raspberry Pi 5 / ARM64 / Python 3.13.

The running package matched the checkout. Its original 636-test suite, Ruff checks,
repository contracts, and service-account smoke check passed. The review still
reproduced the defects below. Passing unit tests did not establish physical timing
or complete the hardware acceptance criteria.

## Corrected behavior

| Finding | Fix | Regression coverage |
|---|---|---|
| Station preview/queue selection blocked the MIDI event loop | One spawned worker process performs selection and queue preparation; blocking catalog reads use threads. MIDI ownership remains in the main process. A failed worker is replaced for the next request. | Slow selection leaves health responsive across preview, concierge, and queue endpoints; separate-process identity; worker failure recovery |
| No discovery after a boot without MIDI hardware | Polling continues with an empty initial inventory, adds new outputs, and recognizes re-enumerated known devices. Active dispatches are not reassigned. | Empty boot, first/second attachment, reconnect without duplication, retry after transition failure |
| Saved favorites required extra clicks and displayed stale state | Toggle from server-backed state, explicitly represent optimistic false, merge successful responses, and roll back only the failing asset. Repeated clicks are disabled while saving. | Executable JavaScript tests for reload, removal, duplicate clicks, request failure, and legacy fallback |
| Restore rename failure left the original appliance stopped | Restart and health-check the preserved original even when no replacement was published. | Fault injection before and between the two publication renames |
| Smoke command produced a permissions traceback | Report inaccessible directories and explain service-account access. | Inaccessible-path diagnostic test |

The HTTP error envelope survives the selection process boundary. Workers receive
settings, intents, and queue-request data; they do not own MIDI ports or playback.
The worker is shut down with the application. There is still one Uvicorn worker and
one authoritative playback timeline.

### Timing evidence

An isolated call to the original station-preview function on the Pi's then-indexed
6,306-asset catalog blocked a 5 ms asyncio ticker for 693 ms. Thread offloading
reduced a later sample to 59 ms but still allowed Python computation to interfere.
The final process-isolated implementation produced maximum ticker gaps of 7 ms
and 6 ms in two subsequent samples. The library batch and machine load were changing,
so these are observations, not a controlled throughput comparison. The measurement
did not send MIDI or claim audible output latency. Run the
[loaded Pi timing protocol](pi-timing-benchmark.md) for physical acceptance.

## Documentation and CI changes

- CI covers Python 3.11, 3.12, and the deployed 3.13 runtime.
- Dependency-free JavaScript behavior tests use Node in development/CI. No frontend
  build, npm packages, or Node runtime on the appliance are required.
- Installation/timing smoke commands use the service account.
- Setup describes background discovery and deferred catalog rebuilds accurately.
- Rendering documentation distinguishes browser AUTO, explicit ORIGINAL, and the
  low-level renderer's default.
- Failure documentation distinguishes physical-link pause/reconnect from dispatch
  failure/stop. Neither silently reroutes an active performance.
- Catalog, ingestion, and history pages describe their implemented integrations.
- Requirements distinguish implemented, partial, deferred, and superseded scope.

## Library batch observed during review

The initial catalog exposed 6,306 assets / 5,930 compositions while the library
contained 25,893 MIDI/sidecar pairs. This was an active import/curation batch, not
a catalog defect: `openorchestrion-tag --from-csv --no-reindex` was running under
`/tmp/oo-bitmidi.sh`, whose next step explicitly rebuilds the catalog.

The review did not interrupt or duplicate the batch. SHA-256 checks on 25,893 MIDI
objects and matching sidecar file identities found no issues; both databases passed
SQLite quick/foreign-key checks. Those checks did not certify musical metadata,
rights evidence, or every sidecar field. Counts were a moving snapshot, not a final
batch-completion assertion.

Before integration, the batch processes had exited and the live API reported
25,893 indexed assets / 24,661 compositions, confirming the expected catalog update.

## Validation commands

```bash
pytest -q
ruff check --select E4,E7,E9,F .
python .github/scripts/validate_repo.py
node .github/scripts/test-web.mjs
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-smoke
```

The software fixes are tested with isolated fixtures and mocked hardware/service
operations. The full suite and installed-wheel check must pass before deployment.
The review's operational read-only checks did not change playback, favorites,
configuration, or library contents.

Final pre-integration checks passed on the Pi: **647 Python tests**, Ruff with the
CI rule set, all repository contracts, and the JavaScript behavior tests (run with
Node on the development PC). A non-editable wheel installed outside the checkout
passed isolated virtual-server startup, spawned-process selection, queue creation,
new JavaScript asset serving, smoke checks, and graceful shutdown. The Python suite
reported two upstream dependency deprecation warnings; it had no failures or skips.

## Deployment verification

The fixes were integrated into the Pi checkout and installed from the tested wheel
on September 7, 2026. A baseline rollback wheel was prepared first. Only the
application package was replaced, with dependency installation disabled. The library
batch had exited and playback was inactive before the service was stopped.

After restart, the production service passed health and service-account smoke checks,
served the new favorites module, and built a three-item preview through its spawned
selection worker. Installed application files matched the repository. The backend
and discovery service were active. The catalog contained 25,893 assets; no library
rebuild or metadata edit was performed by this deployment. No keyboard was present,
so `no_midi_output` remained an expected degraded state with discovery running.

## Explicit remaining limits

These are deployment/product scope or physical evidence gaps, not claims that the
software fixes above have validated unavailable hardware:

- Production endpoints are generic. The planner accepts device profiles, but the
  example devices YAML is not loaded; a production binding/calibration path remains
  future work. No latency offsets or hardware capabilities were invented.
- Dedicated era/source browsing and full browser administration remain deferred.
  Sensitive operations deliberately use local administrator commands. History
  currently displays shortened asset IDs rather than musical titles.
- The Casio was disconnected during inspection. Audible conformance, loaded MIDI
  timing, two-device acoustic synchronization, and kiosk touch behavior need hardware.
- A verified off-device backup and blank-storage restore drill were not established.
  Application-data backups exclude provider secrets and system configuration by design.

See [requirements status](requirements.md#implementation-status-september-2026),
[routing deployment limits](routing-engine.md#device-profiles-and-physical-ports),
and [backup/recovery](backup-recovery.md) for these boundaries.
