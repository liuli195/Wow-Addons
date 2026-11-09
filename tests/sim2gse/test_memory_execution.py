"""内存任务的真实恢复边界；公开训练和页面整链路另作专项验收。"""
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'projects/sim2gse'))
from search import TaskStore, digest


@pytest.mark.real
def test_memory_task_only_writes_explicit_recovery_boundary(tmp_path):
    folder = tmp_path / 'task'
    folder.mkdir()
    store = TaskStore(folder, memory_execution=True)
    try:
        store.state.update(run_id='memory-recovery', archive=[], status='running', counter=1)
        store.save()
        store.publish()
        store.checkpoint()
        assert list(folder.iterdir()) == []
        store.checkpoint(boundary='initial')
        paths = set(folder.iterdir())
        assert paths == {folder / 'task.sqlite3'}
        saved = (folder / 'task.sqlite3').read_bytes()
        store.state['counter'] = 2
        store.save()
        store.publish()
        store.checkpoint(boundary='generation')
        assert (folder / 'task.sqlite3').read_bytes() == saved
        assert set(folder.iterdir()) == paths
    finally:
        store.close()
    resumed = TaskStore(folder, memory_execution=True)
    try:
        assert resumed.state['counter'] == 1
    finally:
        resumed.close()


@pytest.mark.real
def test_interrupted_retest_replays_without_losing_coarse_or_failure_budget(tmp_path):
    store = TaskStore(tmp_path, memory_execution=True)
    request = dict(condition='frozen', purpose='search', program=[], seed=11)
    key = digest(request)
    store.state.update(run_id='retest', archive=[], status='running',
        ga=dict(phase='qualified', finals={'unfinished': {'nominal': {'0': 'not-published'}}}),
        training_failures={'original-request': 2})
    store.put_batch(key, dict(status='success', request=request, data_key=key, dps=42., samples=31,
                              variance=3.), verified=True)
    store.put_batch('transient-final', dict(status='success', request=dict(purpose='nominal'), dps=42.))
    store.checkpoint(boundary='pause')
    assert store.state['ga']['phase'] == 'qualified'
    assert store.state['ga']['finals']
    store.close()
    resumed = TaskStore(tmp_path, memory_execution=True)
    try:
        assert resumed.state['ga'] == dict(phase='retest', finals={})
        assert resumed.state['training_failures']['original-request'] == 2
        assert resumed.batch(key)['dps'] == 42.
        assert resumed.verified_batches[key]['samples'] == 31
        assert resumed.batch('transient-final') is None
    finally:
        resumed.close()


@pytest.mark.real
def test_corrupt_snapshot_is_rejected_without_repair_or_new_files(tmp_path):
    store = TaskStore(tmp_path, memory_execution=True)
    store.state.update(run_id='corrupt', archive=[], counter=1)
    store.checkpoint(boundary='initial')
    store.close()
    with sqlite3.connect(tmp_path / 'task.sqlite3') as database:
        database.execute("UPDATE state_fields SET value='999' WHERE key='counter'")
    before = (tmp_path / 'task.sqlite3').read_bytes()
    with pytest.raises(ValueError, match='恢复点核验失败'):
        TaskStore(tmp_path, memory_execution=True)
    assert (tmp_path / 'task.sqlite3').read_bytes() == before


@pytest.mark.real
def test_recovery_rejects_score_receipt_with_wrong_request_identity(tmp_path):
    store = TaskStore(tmp_path, memory_execution=True)
    try:
        store.state.update(run_id='mismatch', archive=[])
        store.put_batch('wrong-key', dict(status='success', data_key='wrong-key',
            request=dict(purpose='search'), dps=10., samples=31, variance=1.), verified=True)
        with pytest.raises(ValueError, match='成绩.*身份'):
            store.checkpoint(boundary='initial')
        assert not (tmp_path / 'task.sqlite3').exists()
    finally:
        store.close()


@pytest.mark.real
def test_public_task_reads_live_memory_progress_without_progress_file(tmp_path):
    from task import read_task
    store = TaskStore(tmp_path, memory_execution=True)
    try:
        store.state.update(status='running', phase='search', completed_batches=7, archive=[])
        progress = read_task(tmp_path)
        assert progress['completed_batches'] == 7
        assert progress['status'] == 'running'
        assert not (tmp_path / 'progress.json').exists()
    finally:
        store.close()
