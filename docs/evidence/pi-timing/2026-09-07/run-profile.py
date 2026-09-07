"""Current-appliance validation runner; never replaces the prepared queue."""
import asyncio
import datetime
import hashlib
import json
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import websockets

BASE = Path('/var/tmp/openorchestrion-release-20260907')
ROOT = BASE / 'post-auto-power-off'
ROOT.mkdir(exist_ok=True)
BENCH = Path('/opt/openorchestrion/venv/bin/openorchestrion-benchmark')
PROFILE = 'headless-active-one-output'
state = {'phase': 'starting', 'results': [], 'replays': 0, 'requests': 0,
         'ws_messages': 0, 'started_at': datetime.datetime.now(datetime.UTC).isoformat()}
original = None
playback = None
queue = None
commands = set()
active = False
interrupted = False


def record(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + '\n')


def log(kind, **values):
    with (ROOT / 'observations.jsonl').open('a') as f:
        f.write(json.dumps({'at': datetime.datetime.now(datetime.UTC).isoformat(),
                            'kind': kind, **values}) + '\n')


def request(path, body=None):
    start = time.monotonic()
    req = urllib.request.Request('http://127.0.0.1:8000/api/' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        value = json.load(response)
    elapsed = time.monotonic() - start
    state['requests'] += 1
    log('http', path=path, elapsed_seconds=elapsed)
    return value


def environment():
    def run(*args):
        return subprocess.check_output(args, text=True).strip()
    return {'throttled': run('vcgencmd', 'get_throttled'),
            'temperature': run('vcgencmd', 'measure_temp'),
            'service': run('systemctl', 'show', 'openorchestrion.service',
                '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveState'),
            'load': Path('/proc/loadavg').read_text().strip()}


async def play():
    global active
    command = str(uuid.uuid4())
    commands.add(command)
    await asyncio.to_thread(request, 'transport/play', {'command_id': command})
    active = True
    state['replays'] += 1
    log('play', command_id=command)


async def receive(ws):
    global playback, queue, interrupted
    async for raw in ws:
        message = json.loads(raw)
        state['ws_messages'] += 1
        kind, payload = message['type'], message['payload']
        if kind == 'state.snapshot':
            playback, queue = payload['playback'], payload['queue']
        elif kind == 'state.playback':
            previous = playback
            playback = payload
            volume_only = (previous is not None and payload['state'] == previous['state']
                           and payload['volume'] != previous['volume'])
            log('playback_event', state=payload['state'], volume=payload['volume'],
                command_id=payload.get('command_id'), volume_only=volume_only)
            if (active and payload.get('command_id') not in commands | {None}
                    and payload['state'] != 'playing' and not volume_only):
                interrupted = True
                raise RuntimeError('External transport command; relinquishing playback')
        elif kind == 'state.queue':
            queue = payload
        elif kind == 'error':
            raise RuntimeError('Appliance error: ' + json.dumps(payload))
        if original and queue['items'] != original['queue']['items']:
            interrupted = True
            raise RuntimeError('Prepared queue changed; relinquishing playback')


async def monitor(ws, initial):
    tick = 0
    paths = ['library/browse?limit=40', 'library/browse?text=Beethoven&limit=40',
             'library/browse/facets', 'history/recent?limit=25', 'library/facets']
    while True:
        await ws.send(json.dumps({'type': 'state.request_snapshot'}))
        await asyncio.sleep(3)
        if active:
            if playback['state'] == 'stopped':
                position = playback.get('position') or {}
                if position.get('position_ms', 0) < position.get('duration_ms', 1) - 100:
                    raise RuntimeError('Playback stopped before track completion')
                await play()
            elif playback['state'] != 'playing':
                raise RuntimeError('Playback unexpectedly paused or idle')
            if tick % 4 == 0:
                await asyncio.to_thread(request, paths[(tick // 4) % len(paths)])
        if tick % 10 == 0:
            current = await asyncio.to_thread(environment)
            log('environment', **current)
            if current['service'] != initial['service']:
                raise RuntimeError('Service changed or restarted')
            if int(current['throttled'].split('=')[1], 16) & 0xF:
                raise RuntimeError('Current throttling/undervoltage: ' + current['throttled'])
            status = await asyncio.to_thread(request, 'status')
            if not status['outputs']['ready']:
                raise RuntimeError('Physical MIDI output unavailable')
        state['playback'] = playback
        record('progress.json', state)
        tick += 1


async def benchmark(name, long=False):
    state['phase'] = name
    record('progress.json', state)
    args = [str(BENCH), '--enforce', '--json', str(ROOT / (name + '.json'))]
    args += ['--long-run-minutes', '120'] if long else ['--sync-only']
    with (ROOT / (name + '.log')).open('w') as f:
        process = await asyncio.create_subprocess_exec(*args, stdout=f, stderr=f)
        try:
            code = await process.wait()
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()
    state['results'].append({'name': name, 'exit_code': code})
    record('progress.json', state)
    if code:
        raise RuntimeError('Benchmark target miss: ' + name)


async def suite():
    await play()
    for n in range(1, 4):
        await benchmark(f'{PROFILE}-sync-{n}')
        await asyncio.sleep(5)
    await benchmark(f'{PROFILE}-120m', long=True)


async def main():
    global original
    initial = await asyncio.to_thread(environment)
    assert not (int(initial['throttled'].split('=')[1], 16) & 0xF), initial
    async with websockets.connect('ws://127.0.0.1:8000/api/ws') as ws:
        first = json.loads(await ws.recv())
        assert first['type'] == 'state.snapshot'
        original = first['payload']
        assert original['playback']['state'] in {'idle', 'stopped', 'paused', 'playing'}, original['playback']
        assert len(original['queue']['items']) == 1, original['queue']
        record('original-state.json', original)
        wheel = BASE / 'wheel/openorchestrion-0.1.0.dev0-py3-none-any.whl'
        record('candidate-environment.json', {'environment': initial,
            'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
            'source_tree': '49c336212733d6f4e82b5be01e9728fd6eae7714',
            'profile': PROFILE, 'client': 'loopback HTTP reads and persistent WebSocket',
            'background': 'existing WK-220 queued track replayed without queue replacement',
            'kiosk': False, 'minutes': 120})
        record('operator-setup.json', {
            'auto_power_off_disabled': 'Owner confirmed TONE + POWER startup on September 7',
            'authorization': 'Owner authorized continued autonomous testing all day',
            'verified_remotely': False,
        })
        receiver = asyncio.create_task(receive(ws))
        await ws.send(json.dumps({'type': 'state.request_snapshot'}))
        while playback is None:
            await asyncio.sleep(0.01)
        watcher = asyncio.create_task(monitor(ws, initial))
        tests = asyncio.create_task(suite())
        try:
            done, _ = await asyncio.wait({receiver, watcher, tests}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            if tests not in done:
                raise RuntimeError('Monitoring ended before benchmark completion')
            state['phase'] = 'complete'
        except Exception as exc:
            state['phase'] = 'failed'
            state['error'] = str(exc)
        finally:
            for task in (tests, watcher, receiver):
                task.cancel()
            await asyncio.gather(tests, watcher, receiver, return_exceptions=True)
            if active and not interrupted and original['playback']['state'] != 'playing':
                action = 'pause' if original['playback']['state'] == 'paused' and playback['state'] == 'playing' else 'stop'
                await asyncio.to_thread(request, 'transport/' + action, {'command_id': str(uuid.uuid4())})
            state['finished_at'] = datetime.datetime.now(datetime.UTC).isoformat()
            state['final_environment'] = await asyncio.to_thread(environment)
            state['queue_preserved'] = (await asyncio.to_thread(request, 'queue'))['items'] == original['queue']['items']
            record('progress.json', state)
            record('result.json', state)


if __name__ == '__main__':
    asyncio.run(main())
