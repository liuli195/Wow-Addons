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


@pytest.mark.real
def test_final_publication_still_works_after_static_recovery_save(tmp_path, installed_result_center, monkeypatch):
    import json
    from task import parse_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    import result_store
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    folder = tmp_path / 'task'
    store = TaskStore(folder, memory_execution=True)
    character = parse_character(sample_profile())
    store.character, store.simulation_config = character, dict(target_count=1)
    store.state.update(run_id='final-after-recovery', archive=[], completed_batches=0)
    request = dict(condition='frozen', program=[], behavior_identity='candidate', purpose='nominal',
        seed=11, input_seed=22, iterations=32, times=[0], stats='paired-bootstrap-v1', trace=False, reset_events=[])
    key = digest(request)
    row = dict(status='success', request=request, data_key=key, dps=42., samples=31, variance=0.)
    stored = dict(batch_key=key, run_id=store.state['run_id'], condition_key='frozen',
        candidate_key='candidate', program_identity=json.dumps([], separators=(',', ':')),
        purpose='nominal', seed=11, input_seed=22, iterations=32, times=[0], stats_version='paired-bootstrap-v1',
        trace=False, batch_index=0, scenario='nominal', report=_fast_report(character, 42., 31),
        dps=42., samples=31, variance=0.)
    try:
        store.checkpoint(boundary='initial')
        store.stage_report(key, row, stored)
        monkeypatch.setattr(store.report_locations, 'locked',
            lambda: (_ for _ in ()).throw(AssertionError('新版最终保存不应等待公共报告锁')))
        store.flush_reports(final=True)
        receipt = store.batch(key)
        saved = result_store.one('batches', 'batch_key', key, group_key=receipt['storage_group_key'])
        assert saved['dps'] == 42.
        assert receipt['storage_version'] == 3
        store.checkpoint(boundary='final')
    finally:
        store.close()


@pytest.mark.real
def test_seed_snapshot_rejects_stale_writer_and_retries_identical_result(tmp_path, installed_result_center):
    import result_store
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    schema = dict(candidate_id='VARCHAR', score='DOUBLE')
    original = result_store.seed_selected_revision('scope')
    first = [dict(candidate_id='first', score=10.)]
    result_store.publish_seed_selected('scope', first, original, schema=schema)
    result_store.publish_seed_selected('scope', first, original, schema=schema)
    with pytest.raises(ValueError, match='已经变化'):
        result_store.publish_seed_selected('scope', [dict(candidate_id='stale', score=20.)], original, schema=schema)
    assert result_store.read_records('seed_selected', 'scope') == first


@pytest.mark.real
def test_search_summary_rejects_corruption_without_rewriting_evidence(tmp_path, installed_result_center):
    import result_store
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    state = dict(run_id='summary-proof', condition='frozen')
    request = dict(condition='frozen', purpose='search', behavior_identity='candidate', program=[])
    row = dict(status='success', request=request, data_key=digest(request), dps=42., samples=31, variance=0.)
    state['archive'] = [dict(key='candidate', program=[['outbreak']], score=42., batches=[row])]
    result_store.publish_search_records(state)
    storage = state['evidence_storage']
    records = result_store.read_search_records(storage, state['run_id'], condition='frozen')
    assert len(records) == 1
    records[0]['score'] = 999.
    schema = dict(run_id='VARCHAR', candidate_key='VARCHAR', search_order='UBIGINT', program='JSON',
        program_digest='VARCHAR', score='DOUBLE', batches='JSON', candidate='JSON')
    result_store.write('search_records', storage['archive_group'], records, schema=schema)
    with pytest.raises(result_store.InvalidRecordError, match='总摘要'):
        result_store.read_search_records(storage, state['run_id'])
    with pytest.raises(result_store.InvalidRecordError, match='总摘要'):
        result_store.publish_search_records(state)


@pytest.mark.real
@pytest.mark.parametrize('fail', [False, True])
def test_final_groups_obey_wire_budget_write_in_parallel_and_join_on_failure(
        tmp_path, installed_result_center, monkeypatch, fail):
    import copy
    import json
    import threading
    import result_store
    from task import parse_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    store = TaskStore(tmp_path / 'task', memory_execution=True)
    character = parse_character(sample_profile())
    store.character, store.simulation_config = character, dict(target_count=1)
    store.state.update(run_id='parallel-finals', archive=[], completed_batches=0)
    gate = threading.Barrier(2)
    lock, calls = threading.Lock(), []
    write = result_store.write
    def observed_write(table, key, rows, **kwargs):
        with lock:
            number = len(calls)
            calls.append((key, threading.get_ident()))
        if number < 2:
            gate.wait(timeout=3)
        if fail and number == 1:
            raise OSError('injected final save failure')
        return write(table, key, rows, **kwargs)
    monkeypatch.setattr(result_store, 'write', observed_write)
    try:
        for index in range(3):
            request = dict(condition='frozen', program=[], behavior_identity='candidate', purpose='nominal',
                seed=index + 11, input_seed=22, iterations=32, times=[0], stats='paired-bootstrap-v1', trace=False, reset_events=[])
            key = digest(request)
            row = dict(status='success', request=request, data_key=key, dps=42., samples=31, variance=0.)
            stored = dict(batch_key=key, run_id=store.state['run_id'], condition_key='frozen',
                candidate_key='candidate', program_identity=json.dumps([]), purpose='nominal', seed=index + 11,
                input_seed=22, iterations=32, times=[0], stats_version='paired-bootstrap-v1', trace=False,
                batch_index=index, scenario='nominal', report=_fast_report(character, 42., 31),
                dps=42., samples=31, variance=0.)
            # 构造输入声明的原始报告体量；验证分组和并发，不冒称大报告性能实测。
            store.stage_report(key, row, copy.deepcopy(stored), report_bytes=9 * 1024 * 1024)
        if fail:
            with pytest.raises(OSError, match='injected'):
                store.flush_reports(final=True)
            assert 'evidence_storage' not in store.state
            assert len(store.memory_reports) == 3
        else:
            store.flush_reports(final=True)
            assert len(set(store.state['evidence_storage']['report_groups'].values())) == 3
        assert len(calls) == 3
        assert len({thread for _, thread in calls[:2]}) == 2
    finally:
        store.close()
