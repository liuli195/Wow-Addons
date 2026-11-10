"""内存任务的真实恢复边界；公开训练和页面整链路另作专项验收。"""
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'projects/sim2gse'))
from search import TaskStore, digest


@pytest.mark.real
def test_recovery_save_streams_history_without_accumulating_all_serialized_rows(tmp_path):
    import tracemalloc
    store = TaskStore(tmp_path, memory_execution=True)
    archive = []
    for index in range(5000):
        request = dict(condition='frozen', purpose='search', behavior_identity=str(index),
                       program=[index], times=list(range(30)), seed=42)
        key = digest(request)
        batch = dict(status='success', data_key=key, request=request, dps=42., samples=31, variance=0.)
        archive.append(dict(key=str(index), program=[['outbreak']], score=42., batches=[batch]))
        store.put_batch(key, batch, verified=True)
    store.state.update(run_id='bounded-save', archive=archive, training_failures={'failed-before-pause': 1})
    tracemalloc.start()
    try:
        store.checkpoint(boundary='pause')
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        store.close()
    assert peak < 3 * 1024 * 1024, f'保存仍积攒整批临时副本：{peak}字节'
    tracemalloc.start()
    try:
        resumed = TaskStore(tmp_path, memory_execution=True)
        _, restored_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    try:
        assert resumed.state['archive'] == archive
        assert resumed.state['training_failures'] == {'failed-before-pause': 1}
        assert restored_peak < 16 * 1024 * 1024, f'恢复仍重复解码整批历史：{restored_peak}字节'
    finally:
        resumed.close()


@pytest.mark.real
@pytest.mark.parametrize('targets', [1, 5])
@pytest.mark.parametrize('missing_seal', [False, True])
def test_public_formal_resume_uses_one_verified_memory_store(tmp_path, monkeypatch, installed_result_center, targets, missing_seal):
    import engine, search, task
    from runtime import TaskCancelled
    from test_character_export import sample_profile
    from test_search import _fast_identity
    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    folder = tmp_path / 'formal'
    opened = []
    actual = search.TaskStore
    def open_store(destination, **kwargs):
        store = actual(destination, **kwargs)
        opened.append(store)
        return store
    open_store.load_state = actual.load_state
    monkeypatch.setattr(search, 'TaskStore', open_store)
    monkeypatch.setattr(engine, 'identity', _fast_identity)
    def cancelled(*args, **kwargs): raise TaskCancelled('pause before native reference')
    monkeypatch.setattr(engine, 'reference', cancelled)
    scene = dict(target_count=targets, scene='single_target' if targets == 1 else 'aoe')
    first = task.run_task(profile, folder, simulation_config=scene,
        search_config=dict(memory_execution=True, diagnostic_logging=False, search_timeline=False))
    assert first['status'] == 'cancelled'
    opened.clear()
    if missing_seal:
        path = folder / 'task.sqlite3'
        with sqlite3.connect(path) as database:
            database.execute("DELETE FROM state_fields WHERE key='memory_checkpoint'")
        previous = path.read_bytes()
        with pytest.raises(ValueError, match='校验|恢复点|检查点'):
            task.resume_task(folder)
        assert path.read_bytes() == previous
        return
    resumed = task.resume_task(folder)
    assert resumed['status'] == 'cancelled'
    assert len(opened) == 1 and opened[0].memory_execution


@pytest.mark.real
@pytest.mark.parametrize('damaged', [False, True])
def test_version_one_recovery_keeps_old_digest_and_original_file(tmp_path, damaged):
    import json
    request = dict(purpose='search', program=['旧'], times=[0, 300])
    key = digest(request)
    batch = dict(status='success', data_key=key, request=request, dps=42., samples=31, variance=0.)
    encoded = json.dumps(batch, ensure_ascii=False)
    state = dict(run_id='旧恢复', archive=[dict(key='original', batches=[batch])], training_failures={'attempt': 1})
    receipt = dict(version=1, digest=digest(dict(state=state, batches=[(key, encoded)])))
    path = tmp_path / 'task.sqlite3'
    with sqlite3.connect(path) as database:
        database.executescript('CREATE TABLE state(id INTEGER PRIMARY KEY,value TEXT);'
            'CREATE TABLE state_fields(key TEXT PRIMARY KEY,value TEXT);'
            'CREATE TABLE state_archive(key TEXT PRIMARY KEY,ordinal INTEGER,value TEXT);'
            'CREATE TABLE batches(key TEXT PRIMARY KEY,value TEXT);')
        database.execute('INSERT INTO state VALUES(1,?)', (json.dumps(dict(storage_format=2)),))
        database.executemany('INSERT INTO state_fields VALUES(?,?)', [
            (name, json.dumps(value, ensure_ascii=False)) for name, value in dict(state, memory_checkpoint=receipt).items()
            if name != 'archive'])
        database.execute('INSERT INTO state_archive VALUES(?,?,?)', ('original', 0, json.dumps(state['archive'][0], ensure_ascii=False)))
        database.execute('INSERT INTO batches VALUES(?,?)', (key, encoded.replace('42.0', '43.0') if damaged else encoded))
    before = path.read_bytes()
    if damaged:
        with pytest.raises(ValueError, match='恢复点核验失败'):
            TaskStore(tmp_path, memory_execution=True)
    else:
        resumed = TaskStore(tmp_path, memory_execution=True)
        try:
            assert resumed.state['archive'] == state['archive'] and resumed.batch(key) == batch
        finally:
            resumed.close()
    assert path.read_bytes() == before


@pytest.mark.real
def test_recovery_replace_failure_keeps_previous_verified_file(tmp_path, monkeypatch):
    import search
    store = TaskStore(tmp_path, memory_execution=True)
    try:
        store.state.update(run_id='retain-previous', archive=[], counter=1)
        store.checkpoint(boundary='initial')
        previous = (tmp_path / 'task.sqlite3').read_bytes()
        paths = set(tmp_path.iterdir())
        store.state['counter'] = 2
        def fail(*args): raise OSError('替换失败')
        monkeypatch.setattr(search, 'replace_file', fail)
        with pytest.raises(OSError, match='替换失败'):
            store.checkpoint(boundary='pause')
        assert (tmp_path / 'task.sqlite3').read_bytes() == previous
        assert set(tmp_path.iterdir()) == paths
    finally:
        store.close()


@pytest.mark.real
@pytest.mark.parametrize('lost_reply', [False, True])
def test_final_publication_releases_verified_groups_before_starting_later_groups(
        tmp_path, monkeypatch, installed_result_center, lost_reply):
    import gc
    import json
    import threading
    import weakref
    import result_store
    from task import parse_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    class Report(dict):
        pass
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    store = TaskStore(tmp_path / 'publication', memory_execution=True)
    character = parse_character(sample_profile())
    store.character, store.simulation_config = character, dict(target_count=1)
    store.state.update(run_id='release-published', archive=[], completed_batches=0)
    references = []
    for index in range(129):
        request = dict(condition='frozen', program=[], behavior_identity='candidate', purpose='nominal',
            seed=index, input_seed=index+500000, iterations=32, times=[0], stats='paired-bootstrap-v1',
            trace=False, reset_events=[])
        key = digest(request)
        row = dict(status='success', request=request, data_key=key, dps=42., samples=31, variance=0.)
        report = Report(_fast_report(character, 42., 31))
        references.append(weakref.ref(report))
        stored = dict(batch_key=key, run_id=store.state['run_id'], condition_key='frozen', candidate_key='candidate',
            program_identity=json.dumps([]), purpose='nominal', seed=index, input_seed=index+500000,
            iterations=32, times=[0], stats_version='paired-bootstrap-v1', trace=False,
            batch_index=0, scenario='nominal', report=report, dps=42., samples=31, variance=0.)
        store.stage_report(key, row, stored, report_bytes=1)
    del report, stored
    write = result_store.write
    writes, guard = [], threading.Lock()
    def observed_write(table, group, rows, **kwargs):
        with guard:
            writes.append(group)
            ordinal = len(writes)
            if len(writes) == 3:
                gc.collect()
                assert sum(ref() is None for ref in references) >= 64, '已验真的整组报告仍被计划或完成结果持有'
        result = write(table, group, rows, **kwargs)
        if lost_reply and ordinal == 1:
            raise RuntimeError('完整保存后响应丢失')
        return result
    monkeypatch.setattr(result_store, 'write', observed_write)
    try:
        assert store.flush_reports(final=True)
        assert len(writes) == 3 and not store.memory_reports
        assert len(store.state['evidence_storage']['report_groups']) == 129
        assert all(ref() is None for ref in references)
    finally:
        store.close()


@pytest.mark.real
def test_recovery_archive_reuses_one_copy_of_each_scoring_receipt(tmp_path):
    import json
    store = TaskStore(tmp_path, memory_execution=True)
    request = dict(condition='frozen', purpose='search', times=list(range(0, 180000, 200)))
    key = digest(request)
    batch = dict(status='success', data_key=key, request=request, dps=42., samples=31, variance=0.)
    record = dict(key='candidate', program=[['outbreak']], score=42., batches=[dict(batch, cached=True)])
    store.state.update(run_id='compact-recovery', archive=[record])
    store.put_batch(key, batch, verified=True)
    try:
        store.checkpoint(boundary='pause')
        with sqlite3.connect((tmp_path / 'task.sqlite3').as_uri() + '?mode=ro&immutable=1', uri=True) as db:
            raw = json.loads(db.execute('SELECT value FROM state_archive').fetchone()[0])
        assert raw['batches'][0]['checkpoint_batch_key'] == key
        assert 'request' not in raw['batches'][0]
        saved = json.loads(db.execute('SELECT value FROM batches WHERE key=?', (key,)).fetchone()[0])
        assert 'checkpoint_request_key' in saved['request']
        assert 'times' not in saved['request']
    finally:
        store.close()
        db.close()
    resumed = TaskStore(tmp_path, memory_execution=True)
    try:
        assert resumed.state['archive'] == [record]
        assert resumed.batch(key) == batch
    finally:
        resumed.close()


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
        assert 'ga' not in resumed.state  # 初始化尚未建立搜索状态，恢复不能制造空状态。
    finally:
        resumed.close()


@pytest.mark.real
def test_interrupted_retest_replays_without_losing_coarse_or_failure_budget(tmp_path):
    store = TaskStore(tmp_path, memory_execution=True)
    request = dict(condition='frozen', purpose='search', program=[], seed=11)
    key = digest(request)
    store.state.update(run_id='retest', archive=[], status='running', completed_batches=0,
        ga=dict(phase='qualified', finals={'unfinished': {'nominal': {'0': 'not-published'}}}),
        training_failures={'original-request': 2})
    store.put_batch(key, dict(status='success', request=request, data_key=key, dps=42., samples=31,
                              variance=3.), verified=True)
    store.stage_report('transient-final', dict(status='success', request=dict(purpose='nominal'), dps=42.),
                       dict(batch_index=0, scenario='nominal', report={}))
    store.discard_unsaved_reports()
    assert store.state['run_id'] == 'retest' and store.state['training_failures'] == {'original-request': 2}
    assert store.batch(key)['dps'] == 42.
    assert store.batch('transient-final') is None and not store.memory_reports
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
def test_search_summary_rejects_corruption_without_rewriting_evidence(tmp_path, installed_result_center, monkeypatch):
    import result_store
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    many = result_store.read_many
    def no_bulk_history(table, keys, **kwargs):
        assert table != 'search_records', '完整历史核验不能整组装入'
        return many(table, keys, **kwargs)
    monkeypatch.setattr(result_store, 'read_many', no_bulk_history)
    state = dict(run_id='summary-proof', condition='frozen')
    request = dict(condition='frozen', purpose='search', behavior_identity='candidate', program=[])
    row = dict(status='success', request=request, data_key=digest(request), dps=42., samples=31, variance=0.)
    state['archive'] = [dict(key='candidate', program=[['outbreak']], score=42., batches=[row],
                             candidate=dict(source='search', text='exported sequence'))]
    result_store.publish_search_records(state)
    storage = state['evidence_storage']
    state['archive'][0].pop('candidate')  # 恢复副本会省略历史编译对象，业务凭据没有变化。
    result_store.publish_search_records(state)
    assert state['evidence_storage'] == storage
    records = result_store.read_search_records(storage, state['run_id'], condition='frozen')
    assert len(records) == 1
    assert result_store.read_search_records(storage, state['run_id'], columns=['candidate_key', 'program']) == [
        dict(candidate_key='candidate', program=[['outbreak']])]
    records[0]['score'] = 999.
    schema = dict(run_id='VARCHAR', candidate_key='VARCHAR', search_order='UBIGINT', program='JSON',
        program_digest='VARCHAR', score='DOUBLE', batches='JSON', candidate='JSON')
    result_store.write('search_records', storage['archive_group'], records, schema=schema)
    with pytest.raises(result_store.InvalidRecordError, match='总摘要'):
        result_store.read_search_records(storage, state['run_id'])
    with pytest.raises(result_store.InvalidRecordError, match='总摘要'):
        result_store.read_search_records(storage, state['run_id'], columns=['candidate_key', 'program'])
    with pytest.raises(result_store.InvalidRecordError, match='总摘要'):
        result_store.publish_search_records(state)


@pytest.mark.real
def test_compact_history_read_sorts_rows_and_checks_omitted_score_fields(tmp_path, installed_result_center):
    import result_store
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(2):
        identity = 'candidate-' + str(index)
        program = [['outbreak']]
        request = dict(condition='frozen', purpose='search', behavior_identity=identity, program=[])
        batch = dict(status='success', data_key=digest(request), request=request, dps=42., samples=31)
        records.append(dict(run_id='ordered-history', candidate_key=identity, search_order=index,
            program=program, program_digest=digest(program), score=42., batches=[batch], candidate=None))
    storage = dict(version=3, archive_group='reversed', archive_count=2, archive_digest=digest(records))
    schema = dict(run_id='VARCHAR', candidate_key='VARCHAR', search_order='UBIGINT', program='JSON',
        program_digest='VARCHAR', score='DOUBLE', batches='JSON', candidate='JSON')
    result_store.write('search_records', 'reversed', records[::-1], schema=schema)
    read = result_store.read_search_records(storage, 'ordered-history', condition='frozen',
                                             columns=['candidate_key', 'program'])
    assert read == [dict(candidate_key='candidate-0', program=[['outbreak']]),
                    dict(candidate_key='candidate-1', program=[['outbreak']])]
    records[0]['batches'][0]['dps'] = 999.
    result_store.write('search_records', 'reversed', records[::-1], schema=schema)
    with pytest.raises(result_store.InvalidRecordError, match='总摘要'):
        result_store.read_search_records(storage, 'ordered-history', columns=['candidate_key', 'program'])


@pytest.mark.real
@pytest.mark.parametrize('fail', [False, True])
@pytest.mark.parametrize('active_peers', [0, 3])
def test_final_groups_obey_wire_budget_write_in_parallel_and_join_on_failure(
        tmp_path, installed_result_center, monkeypatch, fail, active_peers):
    import copy
    import json
    import threading
    import result_store
    from task import parse_character
    from test_character_export import sample_profile
    from test_search import _fast_report
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    store = TaskStore(tmp_path / 'task', memory_execution=True)
    peers = [TaskStore(tmp_path / f'peer-{index}', memory_execution=True) for index in range(active_peers)]
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
            store.stage_report(key, row, copy.deepcopy(stored),
                               report_bytes=(17 if active_peers else 33) * 1024 * 1024)
        if fail:
            with pytest.raises(OSError, match='injected'):
                store.flush_reports(final=True)
            assert 'evidence_storage' not in store.state
            assert len(store.memory_reports) == 1
            assert len(store.published_report_receipts) == 2
            assert len(calls) == 3
            store.flush_reports(final=True)
            assert not store.memory_reports
            assert len(set(store.state['evidence_storage']['report_groups'].values())) == 3
        else:
            store.flush_reports(final=True)
            assert len(set(store.state['evidence_storage']['report_groups'].values())) == 3
        assert len(calls) == (4 if fail else 3)
        assert len({thread for _, thread in calls[:2]}) == 2
    finally:
        store.close()
        for peer in peers:
            peer.close()
