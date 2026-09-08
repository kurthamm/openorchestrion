"""A bounded, server-owned discovery job for the household Add music screen."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import time

from . import acquisition
from .acquisition_publish import _write, process_identity
from .acquisition_sources import SOURCES


def read_job(root: Path) -> dict:
    path = root / 'web-acquisition.json'
    if not path.exists():
        return {'status': 'idle'}
    report = json.loads(path.read_bytes())
    if report['status'] == 'running':
        try:
            alive = list(process_identity(report['pid'])) == report['identity']
        except (OSError, KeyError):
            alive = False
        if not alive:
            return report | {'status': 'interrupted', 'error': 'The server restarted before this check finished. Retry to continue safely.'}
        progress = acquisition.status(root)
        if progress.get('started_at', 0) >= report['started_at']:
            report = report | {'progress': progress}
    return report


class AcquisitionJobs:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.task = None
        self.process = None
        self.guard = None

    async def start(self, sources: list[str]) -> dict:
        import fcntl

        allowed = {s.key for s in SOURCES if not s.disabled}
        if not sources or len(sources) > 5 or len(set(sources)) != len(sources) or not set(sources) <= allowed:
            raise ValueError('Choose one to five available sources.')
        if self.task and not self.task.done():
            return read_job(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        guard = (self.root / '.web-acquisition.lock').open('a')
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            guard.close()
            raise RuntimeError('A music check is already starting or running. Refresh its progress.')
        try:
            # No user-controlled URL, path, command or download budget reaches the worker.
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, '-m', __name__, str(self.root), *sources,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True, pass_fds=(guard.fileno(),),
            )
            self.guard = guard
            self.task = asyncio.create_task(self._watch())
            # The child publishes its durable status before doing network work.
            for _ in range(100):
                report = read_job(self.root)
                if report.get('pid') == self.process.pid:
                    return report
                if self.process.returncode is not None:
                    break
                await asyncio.sleep(.02)
            return {'status': 'running', 'sources': sources}
        except BaseException:
            guard.close()
            raise

    async def _watch(self):
        try:
            await asyncio.wait_for(self.process.wait(), timeout=1800)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                os.killpg(self.process.pid, signal.SIGKILL)
                await self.process.wait()
            report = read_job(self.root)
            _write(self.root / 'web-acquisition.json', json.dumps(report | {
                'status': 'interrupted', 'finished_at': time.time(),
                'error': 'The check stopped at the server time limit or during shutdown. Retry to continue; admitted music is retained.',
            }).encode())
        finally:
            self.guard.close()

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await self.task


def main():
    root = Path(sys.argv[1]).resolve()
    os.nice(15)
    report = {'status': 'running', 'started_at': time.time(), 'sources': sys.argv[2:],
              'pid': os.getpid(), 'identity': list(process_identity(os.getpid()))}
    path = root / 'web-acquisition.json'
    _write(path, json.dumps(report).encode())
    try:
        if not (root / 'listening-admission.json').exists():
            acquisition.initialize_empty(root)
        result = acquisition.run(root, root.parent / 'acquisition', limit=5, page_limit=4, only=sys.argv[2:])
        report.update(status='complete', progress=result)
    except BlockingIOError:
        report.update(status='failed', error='Another music scan is already running. Wait for it to finish, then retry.')
    except Exception as exc:
        report.update(status='failed', error=str(exc)[:1000])
    report['finished_at'] = time.time()
    _write(path, json.dumps(report).encode())


if __name__ == '__main__':
    main()
