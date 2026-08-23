# Raspberry Pi timing benchmark protocol

Issue #6 is not complete when a scheduler benchmark merely prints small numbers once.
The reference result must be reproducible, tied to a specific appliance build, and run
under the workload OpenOrchestrion actually creates on a Raspberry Pi.

This protocol freezes the conditions and evidence for that measurement.

## What this benchmark measures

`openorchestrion-benchmark` exercises the real `SystemClock` playback scheduler in
real wall time with in-memory virtual MIDI outputs. It measures **software scheduling**:

- interval jitter at p95, p99, and maximum;
- accumulated relative timing error;
- end-to-end long-run scheduler drift after the first send;
- software A/B send skew for simultaneous events routed to two outputs.

It deliberately removes arbitrary startup latency by treating the first send as `t=0`.
It therefore does **not** measure:

- USB/MIDI transport latency;
- a keyboard's MIDI-to-audio latency;
- acoustic propagation through the room;
- queue/API command latency.

Those hardware measurements use `sync-click.mid` and recorded audio separately. Do not
interpret the virtual-output A/B skew as proof that two physical keyboards sound at the
same instant.

## Provisional software targets

The benchmark currently enforces these provisional targets:

| Metric | Target |
| --- | ---: |
| p95 absolute interval jitter | <= 2 ms |
| p99 absolute interval jitter | <= 5 ms |
| maximum absolute interval jitter | <= 10 ms |
| absolute long-run drift | <= 5 ms |
| p95 virtual two-output skew | <= 1 ms |
| maximum virtual two-output skew | <= 3 ms |

These are software-scheduler targets, not promises about audible physical latency. If the
reference Pi repeatedly misses them under realistic load, investigate ALSA timestamped
sequencing or a dedicated playback helper before relaxing the targets.

## Reference software installation

Run the benchmark against the same wheel/appliance path used for hardware validation, not
an editable checkout. Follow [Raspberry Pi appliance installation](appliance-install.md),
then confirm:

```bash
systemctl status openorchestrion.service
/opt/openorchestrion/venv/bin/openorchestrion-smoke
```

The installed wheel exposes:

```bash
/opt/openorchestrion/venv/bin/openorchestrion-benchmark
```

The benchmark itself is a separate process so its scheduler experiences the CPU, I/O, and
kernel contention created by the running appliance without disturbing the server-owned
queue or taking control of physical MIDI ports.

## Record the environment first

Create a directory for the run and capture enough information to explain a result later:

```bash
RUN=~/openorchestrion-timing/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$RUN"

{
  echo "timestamp_utc=$(date -u --iso-8601=seconds)"
  echo "git_commit=$(git -C /path/to/openorchestrion rev-parse HEAD 2>/dev/null || echo wheel-install)"
  echo "hostname=$(hostname)"
  uname -a
  python3 --version
  /opt/openorchestrion/venv/bin/python --version
  /opt/openorchestrion/venv/bin/pip show openorchestrion
  systemctl --no-pager status openorchestrion.service || true
  echo "--- cpu ---"
  lscpu
  echo "--- usb ---"
  lsusb -t 2>/dev/null || true
  echo "--- chromium ---"
  chromium --version 2>/dev/null || chromium-browser --version 2>/dev/null || true
  echo "--- governor ---"
  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || true
  echo "--- raspberry-pi throttling ---"
  vcgencmd get_throttled 2>/dev/null || true
  vcgencmd measure_temp 2>/dev/null || true
} > "$RUN/environment.txt" 2>&1
```

If the installation came only from a wheel, record the release/wheel hash in
`environment.txt` instead of inventing a Git commit.

Also record manually in the same file:

- Raspberry Pi model and RAM size;
- power supply used;
- storage medium (microSD/NVMe/USB SSD);
- Raspberry Pi OS release and desktop/headless image;
- connected MIDI devices and direct/hub topology;
- whether Wi-Fi or Ethernet was active;
- display model/resolution for kiosk runs.

Do not overclock for the reference result unless the project explicitly adopts that as the
reference configuration. Record any non-default CPU governor or kernel tuning.

## Warm-up

After boot:

1. wait at least five minutes for service/desktop startup work to settle;
2. run `openorchestrion-smoke`;
3. open the kiosk or a LAN browser and browse/search the library once so normal caches are
   populated;
4. confirm `vcgencmd get_throttled` does not report a current undervoltage/thermal condition;
5. close unrelated desktop applications.

Do not disable the OpenOrchestrion service, WebSockets, networking, or Chromium merely to
obtain a prettier number. The loaded result is the point of the exercise.

## Load profiles

Record results under named profiles. Do not mix profile names between runs.

### A. `headless-idle`

- `openorchestrion.service` running;
- no Chromium kiosk;
- normal network stack;
- catalog/history available if present;
- no deliberate foreground playback.

This is a diagnostic baseline, not the acceptance profile.

### B. `kiosk-idle`

- service running;
- Chromium kiosk running the local UI;
- WebSocket connected;
- library Browse/Listen surfaces exercised;
- no deliberate foreground playback.

This quantifies the cost of the appliance UI.

### C. `kiosk-active-one-output`

- everything in `kiosk-idle`;
- one physical MIDI sound engine connected and active through the normal server playback
  path;
- Now Playing/progress visible;
- ordinary library/history traffic continues.

Mute or reduce the keyboard's speaker/amplifier if a two-hour audible test is impractical;
the MIDI engine should still be receiving/processing events.

### D. `kiosk-active-two-output`

- everything in `kiosk-active-one-output`;
- two physical MIDI destinations active from the single server-owned master timeline;
- use a true two-part/two-piano fixture or validated repertoire so both destinations receive
  ongoing work.

This is the final software-load profile for the two-engine reference build. Physical
MIDI-to-audio synchronization is measured separately.

If hardware is not yet available, profiles A/B are useful engineering data but do **not**
close the one/two-output requirement in Issue #6.

## Short synchronization run

Run the two-output software sync case at least three times for each profile being reported:

```bash
for N in 1 2 3; do
  /opt/openorchestrion/venv/bin/openorchestrion-benchmark \
    --sync-only \
    --json "$RUN/kiosk-idle-sync-$N.json" \
    --enforce
  sleep 5
done
```

Change the filename prefix to the actual profile. Keep failed JSON reports; a failure is
evidence, not a file to rerun until it disappears.

The short run is primarily a repeatability check for jitter and virtual A/B scheduler skew.

## 120-minute endurance run

The acceptance endurance run is:

```bash
/opt/openorchestrion/venv/bin/openorchestrion-benchmark \
  --long-run-minutes 120 \
  --json "$RUN/kiosk-active-one-output-120m.json" \
  --enforce
```

For the completed two-engine build, repeat under `kiosk-active-two-output`:

```bash
/opt/openorchestrion/venv/bin/openorchestrion-benchmark \
  --long-run-minutes 120 \
  --json "$RUN/kiosk-active-two-output-120m.json" \
  --enforce
```

The command runs a short two-output `sync-click` software case plus the one-output long-run
scheduler case. The profile name describes the **background appliance load**, not the
benchmark's in-memory output count.

Do not suspend Chromium or the service during the benchmark. Normal phone/tablet clients may
remain connected; record anything unusual in a run note.

## During and after the run

Capture basic system evidence without adding heavy profiling overhead:

```bash
{
  echo "--- after benchmark ---"
  date -u --iso-8601=seconds
  vcgencmd get_throttled 2>/dev/null || true
  vcgencmd measure_temp 2>/dev/null || true
  systemctl --no-pager status openorchestrion.service || true
} >> "$RUN/environment.txt" 2>&1
```

A run affected by current undervoltage, thermal throttling, service restart, or obvious
background maintenance should be retained but marked **invalid/environmental** rather than
silently substituted with a better run.

## Acceptance and interpretation

For the reference configuration:

- every reported `--enforce` acceptance run must exit 0;
- all individual cases in the JSON must have `passed: true`;
- no service crash/restart may occur during the run;
- no current undervoltage/thermal-throttling condition may be present;
- the 120-minute wall duration should be consistent with the logical duration rather than
  showing a scheduler stall;
- profile and environment evidence must accompany the JSON.

A single extreme maximum-jitter outlier is still a target miss under the current policy.
Do not hide it behind a good p95. If the same failure reproduces on a healthy reference Pi,
open a scheduler investigation with the raw JSON/environment evidence.

## Physical MIDI-to-audio latency is a separate measurement

After software timing passes, use generated `sync-click.mid` against real devices to measure
the time from a common scheduled event to audible/electronic output. For two keyboards,
measure the **relative** onset difference repeatedly and store the stable correction as the
device/route latency offset.

Room geometry also matters: sound travels roughly 1.1 ft/ms, so speaker/listener placement can
produce more audible offset than the USB scheduler. Record the microphone/listening geometry
when publishing acoustic measurements.

Issue #11 owns the complementary Yamaha validation and comparison; Issue #6 should retain the
software timing JSON plus any hardware timing evidence used to decide whether the Python/Mido
scheduler remains acceptable.

## Evidence to attach to Issue #6

For each reference run, attach or commit as appropriate:

- benchmark JSON file(s);
- `environment.txt`;
- profile name;
- pass/fail summary;
- any invalid-run note and reason;
- physical latency measurement method/results when available.

Do not commit a giant generated MIDI fixture directory. The benchmark generates its own
copyright-clean fixtures deterministically.
