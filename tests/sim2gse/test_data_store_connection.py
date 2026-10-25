"""Real consumer entry in an isolated connected project, without a user link."""
import json
import os
import pytest
from pathlib import Path
import shutil
import subprocess
import sys

pytestmark = pytest.mark.real

REPOSITORY = Path(__file__).resolve().parents[2]


def test_connected_consumer_reads_writes_without_old_user_installation(tmp_path, installed_data_store):
    source = installed_data_store
    installed = tmp_path / "installed"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    project = tmp_path / "project"
    adapter = project / "projects/sim2gse/result_store.py"
    adapter.parent.mkdir(parents=True)
    shutil.copy2(REPOSITORY / "projects/sim2gse/result_store.py", adapter)
    connected = subprocess.run(
        [sys.executable, str(installed / "scripts/project_binding.py"), "connect", "--project", str(project)],
        text=True, capture_output=True,
    )
    assert connected.returncode == 0, connected.stderr
    env = dict(os.environ, USERPROFILE=str(tmp_path / "empty-home"), HOME=str(tmp_path / "empty-home"))
    program = """import json,runpy,sys
m=runpy.run_path(sys.argv[1]);m['ensure_available']()
assert m['write']('measurements','one',[{'score':7,'parts':[{'value':4}]}])==1
assert m['read_records']('measurements','one',columns=['score'],filters={'score':7})==[{'score':7}]
assert m['read_records']('measurements','one',columns=['score'],filters={'score':8})==[]
assert m['write']('binary_measurements','one',[{'score':8,'payload':bytes([0,255])}],schema={'score':'INTEGER','payload':'BLOB'},binary=True)==1
assert m['read_records']('binary_measurements','one',columns=['payload'],filters={'score':8})==[{'payload':bytes([0,255])}]
from unittest.mock import Mock,patch
blocked_write=Mock()
with patch.dict(m['_api'](),{'DATA_STORE_CAPABILITIES':(), 'write':blocked_write}):
    try:
        m['write']('binary_measurements','blocked',[{'payload':bytes([0,255])}],schema={'payload':'BLOB'},binary=True)
    except m['DataReadError'] as error:
        assert 'binary-write-v1' in str(error) and '更新技能' in str(error) and '重启' in str(error)
    else:
        raise AssertionError('missing capability must fail before writing')
blocked_write.assert_not_called()
print(json.dumps(list(m['iter_rows']('SELECT score,parts[1].value AS part FROM measurements',tables=['measurements']))))
"""
    result = subprocess.run([sys.executable, "-c", program, str(adapter)], env=env,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [{"score": 7, "part": 4}]


def test_unconnected_consumer_fails_before_writing_data(tmp_path):
    adapter = tmp_path / "projects/sim2gse/result_store.py"
    adapter.parent.mkdir(parents=True)
    shutil.copy2(REPOSITORY / "projects/sim2gse/result_store.py", adapter)
    env = dict(os.environ, USERPROFILE=str(tmp_path / "empty-home"), HOME=str(tmp_path / "empty-home"))
    result = subprocess.run(
        [sys.executable, "-c", "import runpy,sys;m=runpy.run_path(sys.argv[1]);m['ensure_available']()", str(adapter)],
        env=env, text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert "接入" in result.stderr
    assert not (tmp_path / "data").exists()





def test_page_classifies_wrapped_storage_failure_from_the_real_target(tmp_path):
    import threading
    from urllib.request import urlopen
    import interface
    import result_store

    run_id, task_id = 'a' * 32, 'b' * 32
    result_store.write('runs', run_id, [{'run_id': run_id}])
    (result_store.DATA_ROOT / 'runs' / (run_id + '.parquet')).write_bytes(b'broken target')
    server = interface.create_server(tmp_path / 'page', port=0)
    _, destination = server.task_paths(task_id)
    destination.mkdir()
    (destination / 'result.json').write_text(json.dumps({'run_id': run_id}), encoding='utf-8')
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/tasks/{task_id}') as response:
            state = json.loads(response.read())
        assert state['phase'] == 'storage_unavailable'
        assert state['storage_unavailable'] and state['recoverable']
        assert '共享存储' in state['error']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_known_batch_groups_and_legacy_single_do_not_fallback_on_missing_keys(tmp_path):
    import result_store

    result_store.write('batches', 'legacy', [{'batch_key': 'legacy', 'dps': 5., 'samples': 2}])
    result_store.write('batches', 'group', [
        {'batch_key': 'wanted', 'dps': 7., 'samples': 3},
        {'batch_key': 'extra', 'dps': 9., 'samples': 4},
    ])
    (result_store.DATA_ROOT / 'batches' / 'foreign.parquet').write_bytes(b'broken unrelated shard')
    assert result_store.one('batches', 'batch_key', 'missing') is None
    assert result_store.one('batches', 'batch_key', 'wanted', group_key='group',
                            columns=['batch_key', 'dps']) == {'batch_key': 'wanted', 'dps': 7.}
    assert result_store.one('batches', 'batch_key', 'legacy')['samples'] == 2
    assert result_store.read_many('batches', ['group', 'legacy'], columns=['batch_key'],
                                  filters={'batch_key': 'wanted'}) == [{'batch_key': 'wanted'}]


@pytest.mark.parametrize('blocked_file', ['.report-publish.lock', '.report-locations.jsonl'])
def test_page_classifies_report_locator_permission_error_as_storage_failure(tmp_path, monkeypatch, blocked_file):
    import threading
    from urllib.request import urlopen
    import interface
    import result_store
    import task

    run_id, task_id = 'c' * 32, 'd' * 32
    saved = dict.fromkeys(result_store.RUN_SCHEMA)
    saved.update(run_id=run_id, status='offline_ready', phase='done', config={},
                 profile={}, identity={}, simulation_config={}, controlled_data_key='controlled')
    result_store.write('runs', run_id, [saved], schema=result_store.RUN_SCHEMA)
    with result_store.ReportLocations(result_store.DATA_ROOT).locked() as locations:
        locations.reserve('controlled_g0', ['controlled'])
        result_store.write('batches', 'controlled_g0',
                           [{'batch_key': 'controlled', 'dps': 7., 'samples': 2}])
    if blocked_file == '.report-publish.lock':
        destination = tmp_path / 'task'
    else:
        server = interface.create_server(tmp_path / 'page', port=0)
        _, destination = server.task_paths(task_id)
    destination.mkdir()
    (destination / 'result.json').write_text(json.dumps({'run_id': run_id}), encoding='utf-8')
    assert task.read_task(destination)['controlled_simulation']['summary'] == {'dps': 7., 'samples': 2}
    open_file = Path.open

    def denied(path, *args, **kwargs):
        if path == result_store.DATA_ROOT / blocked_file:
            raise PermissionError('fixture: locator access denied')
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', denied)
    if blocked_file == '.report-publish.lock':
        with pytest.raises(task.TaskError) as error:
            task.read_task(destination)
        assert isinstance(error.value.__cause__, result_store.DataReadError)
        assert isinstance(error.value.__cause__.__cause__, PermissionError)
        return
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/tasks/{task_id}') as response:
            state = json.loads(response.read())
        assert state['phase'] == 'storage_unavailable'
        assert state['storage_unavailable'] and state['recoverable']
        assert '共享存储' in state['error']
        with pytest.raises(task.TaskError) as error:
            task.read_task(destination)
        assert isinstance(error.value.__cause__, result_store.DataReadError)
        assert isinstance(error.value.__cause__.__cause__, PermissionError)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize('mode,fault', [('dual', 'api-version'), ('optimize', 'api-version'),
                                      ('dual', 'definition-file')])
def test_page_reports_storage_startup_failure_before_native_compute(tmp_path, installed_data_store,
                                                                   monkeypatch, mode, fault):
    import threading
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    import interface
    import result_store
    from test_character_export import sample_profile

    installed = tmp_path / 'startup-installed'
    shutil.copytree(installed_data_store, installed, ignore=shutil.ignore_patterns('__pycache__'))
    if fault == 'api-version':
        with (installed / 'scripts/data_store.py').open('a', encoding='utf-8') as output:
            output.write('\nDATA_STORE_API_VERSION = 1\n')
    project = tmp_path / 'project'
    project.mkdir()
    connected = subprocess.run([sys.executable, str(installed / 'scripts/project_binding.py'),
                                'connect', '--project', str(project)], text=True, capture_output=True)
    assert connected.returncode == 0, connected.stderr
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', project)
    monkeypatch.setattr(result_store, '_SKILL_API', None)
    monkeypatch.setattr(result_store, 'DATA_ROOT', project / 'data')
    if fault == 'api-version':
        assert not result_store.DATA_ROOT.exists()
    if fault == 'definition-file':
        result_store.write('burst_definitions', 'broken', [{'spec_id': 252}])
        (result_store.DATA_ROOT / 'burst_definitions/broken.parquet').write_bytes(b'broken definition file')
    native_starts = []

    def forbidden_process(*args, **kwargs):
        native_starts.append(args)
        raise AssertionError('storage startup failure must precede native compute')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    server = interface.create_server(project / 'page', port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        request = Request(base + '/api/tasks', data=json.dumps({'mode': mode, 'profile': sample_profile()}).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        with response:
            status, state = response.code, json.loads(response.read())
        if mode == 'optimize':
            assert status == 202
            handle = server.tasks[state['task_id']][1]
            handle.join(2)
            assert handle.done
            with urlopen(base + '/api/tasks/' + state['task_id']) as response:
                state = json.loads(response.read())
            assert state['phase'] == 'storage_unavailable' and state['recoverable']
        else:
            assert status == 500
        if fault == 'api-version':
            assert '同步' in state['error'] and '版本 2' in state['error']
            assert not result_store.DATA_ROOT.exists()
        else:
            assert '共享存储' in state['error']
        assert native_starts == []
    finally:
        for _, handle in server.tasks.values():
            handle.join(2)
        server.shutdown()
        server.server_close()
        thread.join(2)
