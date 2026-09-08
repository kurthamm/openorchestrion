import asyncio
from contextlib import closing
import json
import os
import sys
import time

from fastapi.testclient import TestClient
import pytest

from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.library import acquisition as acq
from openorchestrion.library import acquisition_job as jobs

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux acquisition appliance')


@pytest.fixture
def client(tmp_path):
    root = tmp_path / 'library'
    settings = Settings(root, root / 'catalog.db', tmp_path / 'history.db',
                        player_state_db=tmp_path / 'player.db', virtual_midi=True)
    with TestClient(create_app(settings=settings)) as client:
        yield client


def test_sources_visible_without_initializing_or_downloading(client):
    response = client.get('/api/library/acquisition/job').json()
    assert response['job']['status'] == 'idle'
    assert len([s for s in response['sources'] if not s['disabled']]) == 5
    assert not (client.app.state.settings.library_root / 'listening-admission.json').exists()


@pytest.mark.parametrize('sources', [[], ['bitmidi'], ['https://example.com/song.mid'], ['smd', 'smd']])
def test_invalid_or_disabled_sources_do_not_launch(client, sources):
    assert client.post('/api/library/acquisition/job', json={'sources': sources}).status_code == 422
    assert client.app.state.acquisition_jobs.process is None


def test_cross_origin_request_rejected(client):
    assert client.post('/api/library/acquisition/job', json={'sources': ['smd']},
                       headers={'Origin': 'https://unrelated.example'}).status_code == 403


def test_existing_unseeded_library_is_preserved_real_child(client):
    root = client.app.state.settings.library_root
    (root / 'assets').mkdir(parents=True)
    marker = root / 'assets' / 'keep.mid'
    marker.write_bytes(b'original')
    response = client.post('/api/library/acquisition/job', json={'sources': ['smd']})
    assert response.status_code == 202
    for _ in range(100):
        report = client.get('/api/library/acquisition/job').json()['job']
        if report['status'] == 'failed':
            break
        time.sleep(.05)
    assert report['status'] == 'failed'
    assert 'existing collection' in report['error']
    assert marker.read_bytes() == b'original'
    assert client.get('/api/health').status_code == 200


def test_shared_library_lock_prevents_different_state_roots(tmp_path):
    import fcntl
    root = tmp_path / 'library'
    acq.initialize_empty(root)
    with (root / '.acquisition-run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            acq.run(root, tmp_path / 'different-state', only=['smd'])


def test_success_progress_and_duplicate_retry_use_real_quality_gate(tmp_path, monkeypatch):
    from test_acquisition import midi_bytes
    root = tmp_path / 'library'
    acq.initialize_empty(root)
    source = next(s for s in acq.SOURCES if s.key == 'smd')
    item = {'url': source.seeds[0] + '/test.mid', 'reference': source.seeds[0],
            'kind': 'midi', 'title': 'Complete test arrangement'}
    with closing(acq.connect(root)) as conn:
        acq.enqueue(conn, source, [item])
    class Client:
        def __init__(self, source):
            pass
        def get(self, url, **kwargs):
            return midi_bytes()
    monkeypatch.setattr(acq, 'Client', Client)
    seen = []
    original = acq.save_status
    def save(conn, report):
        seen.append(json.loads(json.dumps(report)))
        original(conn, report)
    monkeypatch.setattr(acq, 'save_status', save)
    monkeypatch.setattr(os, 'nice', lambda value: None)
    monkeypatch.setattr(sys, 'argv', ['job', str(root), 'smd'])
    original_run = acq.run
    monkeypatch.setattr(acq, 'run', lambda root, state, **kw: original_run(root, state, limit=1, page_limit=1, only=['smd']))
    jobs.main()
    report = jobs.read_job(root)
    assert report['status'] == 'complete'
    assert report['progress']['counts']['admitted'] == 1
    assert any(r.get('sources') and r['sources'][-1]['status'] == 'running' for r in seen)
    before = {p.name: p.read_bytes() for p in (root / 'assets').glob('*') if p.suffix in ('.json', '.mid')}
    with closing(acq.connect(root)) as conn, conn:
        conn.execute('UPDATE frontier SET due=0 WHERE url=?', (item['url'],))
    jobs.main()
    assert jobs.read_job(root)['progress']['counts']['duplicate_bytes'] == 1
    assert before == {p.name: p.read_bytes() for p in (root / 'assets').glob('*') if p.suffix in ('.json', '.mid')}


def test_shutdown_kills_job_and_marks_interrupted(tmp_path, monkeypatch):
    root = tmp_path / 'library'
    real = asyncio.create_subprocess_exec
    async def launch(*args, **kwargs):
        return await real(sys.executable, '-c', 'import time; time.sleep(60)', **kwargs)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', launch)
    async def exercise():
        manager = jobs.AcquisitionJobs(root)
        await manager.start(['smd'])
        pid = manager.process.pid
        await manager.start(['midkar'])
        assert manager.process.pid == pid
        await manager.close()
        assert manager.process.returncode is not None
        assert jobs.read_job(root)['status'] == 'interrupted'
    asyncio.run(exercise())
