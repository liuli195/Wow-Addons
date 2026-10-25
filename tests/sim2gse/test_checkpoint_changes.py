"""公开任务与恢复接缝保护局部检查点的完整状态。"""
import copy
import json
from pathlib import Path
import sqlite3

import pytest




def _new_checkpoint(tmp_path=None):
    from search import TaskStore

    if tmp_path is None:
        store = TaskStore('/memory/checkpoint', connection=sqlite3.connect(':memory:'),
                          reusable_database=':memory:', report_locations={})
    else:
        destination = tmp_path / 'task'
        destination.mkdir()
        store = TaskStore(destination)
    store.state.update(run_id='checkpoint', config={'diagnostic_logging': False}, status='running',
        elapsed_seconds=0, inflight={}, pending=[dict(receipt={'feedback': {'reward': None}})],
        archive=[dict(key='first', evidence={'samples': [1]}),
                 dict(key='second', evidence={'samples': [2]})])
    store.save()
    return store


def _reopen_checkpoint(store):
    from search import TaskStore

    destination = store.destination
    in_memory = destination == Path('/memory/checkpoint')
    if in_memory:
        # Exercise the original SQL and a fresh Store, not file/WAL durability.
        database = sqlite3.connect(':memory:')
        store.db.backup(database)
        store.diagnostic_logging_override = False
    store.close()
    reopened = (TaskStore(destination, connection=database, reusable_database=':memory:',
                          report_locations={}) if in_memory else TaskStore(destination))
    try:
        return copy.deepcopy(reopened.state)
    finally:
        if in_memory:
            reopened.diagnostic_logging_override = False
        reopened.close()


@pytest.mark.parametrize('change', ['reorder', 'delete', 'append', 'new_field', 'whole_archive'])
def test_checkpoint_structural_changes_fall_back_without_losing_unmarked_nested_state(change):
    store = _new_checkpoint()
    store.state['pending'][0]['receipt']['feedback']['reward'] = .5
    if change == 'reorder':
        store.state['archive'].reverse()
    elif change == 'delete':
        store.state['archive'].pop(0)
    elif change == 'append':
        store.state['archive'].append(dict(key='third', evidence={'samples': [3]}))
    elif change == 'new_field':
        store.state['new_field'] = {'nested': ['retained']}
    else:
        store.state['archive'][0]['evidence']['samples'].append(4)
    # Known structure changes must retain the original complete-save fallback,
    # including changes outside the caller's limited field list.
    store.save(fields=('archive',) if change == 'whole_archive' else ())
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected


def test_scoped_checkpoint_deletes_an_explicit_field():
    store = _new_checkpoint()
    del store.state['pending']
    store.save(fields=('pending',))
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected
    assert 'pending' not in expected


def test_scoped_checkpoint_failure_rolls_back_and_retry_persists_all_changes():
    import sqlite3
    from search import TaskStore

    store = _new_checkpoint()
    before = copy.deepcopy(store.state)
    store.state['pending'][0]['receipt']['feedback']['reward'] = .75
    store.state['archive'][1]['evidence']['samples'].append(4)
    expected = copy.deepcopy(store.state)
    # Fail the final progress insert, after both state updates have executed.
    store.db.execute("""CREATE TEMP TRIGGER fail_checkpoint BEFORE INSERT ON runtime_progress
        BEGIN SELECT RAISE(ABORT, 'injected checkpoint failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='injected checkpoint failure'):
        store.save(fields=('pending',), archive_keys=('second',))
    assert TaskStore.load_state(store.db) == before
    store.db.execute('DROP TRIGGER fail_checkpoint')
    # Retry on the same object: stale successful-value caches would skip the SQL.
    store.save(fields=('pending',), archive_keys=('second',))
    assert _reopen_checkpoint(store) == expected
    assert expected['pending'][0]['receipt']['feedback']['reward'] == .75
    assert expected['archive'][1]['evidence']['samples'] == [2, 4]


def _stage_checkpoint_reports(store, count=1):
    import result_store
    from task import parse_character
    from test_character_export import sample_profile
    from test_search import _fast_report

    result_store.DATA_ROOT.mkdir(exist_ok=True)
    store.character = parse_character(sample_profile())
    store.simulation_config = None
    store.state.setdefault('completed_batches', 0)
    store.defer_persistence = True
    rows = []
    for index in range(count):
        key = f'batch-{index}'
        request = dict(condition='condition', program=[['outbreak']], purpose='search',
            behavior_identity='candidate', seed=100 + index, input_seed=200 + index,
            iterations=3, times=[0, 300], stats='paired-bootstrap-v1', trace=False,
            reset_events=[])
        row = dict(status='success', request=request, dps=100.0 + index, samples=2,
                   variance=0, requested_iterations=3, data_key=key, feedback=None)
        stored = dict(batch_key=key, run_id='checkpoint', condition_key='condition',
            candidate_key='candidate', program_identity='[["outbreak"]]', purpose='search',
            batch_index=index, scenario='nominal', stats_version='paired-bootstrap-v1',
            seed=100 + index, input_seed=200 + index, iterations=3, times=[0, 300],
            trace=False, dps=100.0 + index, samples=2, variance=0, requested_iterations=3,
            report=_fast_report(store.character, 100.0 + index, 2))
        path = store.destination / 'batches' / key / 'native.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(stored['report']), encoding='utf-8')
        store.stage_report(key, row, stored, report_path=path)
        rows.append(row)
    # The caller owns these original summaries, not the copies used in SQLite.
    store.state['archive'][0]['batches'] = rows
    store.state['ga'] = dict(receipts=rows)
    return rows


@pytest.mark.real
def test_resume_after_partial_group_commit_uses_unused_group_number(tmp_path, monkeypatch):
    import shutil
    import result_store
    from search import TaskStore

    store = _new_checkpoint(tmp_path)
    before = copy.deepcopy(store.state)
    rows = _stage_checkpoint_reports(store, count=13)
    # Keep the original 11 + legacy twelfth + tail publication layout, not a
    # smaller group. Only the redundant HTTP/GA/native preparation is retired.
    pending = list(store.report_buffer)
    # The original interruption occurs before the tail reaches its first flush.
    store.report_buffer[:] = pending[:12]
    legacy_key, _, legacy = pending[11]
    result_store.write_batch(legacy_key, dict(
        {name: value for name, value in legacy.items() if not name.startswith('_')},
        report=json.loads(legacy['_report_path'].read_text(encoding='utf-8'))))
    # These are input counters from the thirteen already-produced reports.
    store.state.update(batch_requests=13, native_batch_starts=13)
    snapshot = tmp_path / 'partial-commit.sqlite3'
    commit = store._commit_report_group
    interrupted = []

    def interrupt_after_commit(group, number, metadata, **options):
        commit(group, number, metadata, **options)
        if not options.get('checkpoint', True):
            interrupted.append(group)
            with sqlite3.connect(snapshot) as target:
                store.db.backup(target)
            target.close()
            raise OSError('stop after partial group commit')

    with monkeypatch.context() as fault:
        fault.setattr(store, '_commit_report_group', interrupt_after_commit)
        with pytest.raises(OSError, match='stop after partial group commit'):
            store.checkpoint()
    assert interrupted == ['checkpoint_g0']
    assert store.persisted_batches == 11
    assert TaskStore.load_state(store.db) == before
    character, destination = store.character, store.destination
    store.close()
    # Resume the exact durable image at the interruption, not live staged state.
    shutil.copyfile(snapshot, destination / 'task.sqlite3')
    store = TaskStore(destination)
    try:
        store.recover_reports(character, None)
        assert store.state['archive'] == before['archive']
        assert store.state['completed_batches'] == store.persisted_batches == 11
        assert store.state['next_report_group'] == 1
        store.character, store.simulation_config = character, None
        store.defer_persistence = True
        for key, row, metadata in pending:
            saved = store.batch(key)
            if saved is not None:
                row.update(saved)
            else:
                store.stage_report(key, row, metadata, report_path=metadata['_report_path'])
        store.state['archive'][0]['batches'] = rows
        store.state['ga'] = dict(receipts=rows)
        store.checkpoint()
        assert store.state['completed_batches'] == store.persisted_batches == 13
        assert store.state['batch_requests'] == store.state['native_batch_starts'] == 13
        assert store.state['next_report_group'] == 2
        assert not store.db.execute('SELECT key FROM report_intents').fetchall()
        assert not store.report_buffer
        with result_store.query(
                "SELECT batch_key, report.sim.statistics.raid_dps.mean "
                "FROM batches WHERE purpose='search'", tables=['batches']) as cursor:
            reports = cursor.fetchall()
        assert {key for key, _ in reports} == {row['data_key'] for row in rows}
        assert len(reports) == len({key for key, _ in reports}) == 13
        expected_groups = {'checkpoint_g0': {row['data_key'] for row in rows[:11]},
                           legacy_key: {legacy_key}, 'checkpoint_g1': {rows[12]['data_key']}}
        for group, keys in expected_groups.items():
            assert {row['batch_key'] for row in result_store.read_records('batches', group)} == keys
            assert all(store.batch(key)['storage_group_key'] == group for key in keys)
        assert {key: score for key, score in reports} == {
            row['data_key']: row['dps'] for row in rows}
        assert all(all(store.batch(row['data_key'])[field] == row[field]
                       for field in ('request', 'dps', 'samples', 'variance')) for row in rows)
        assert not list((destination / 'batches').glob('*/native.json'))
        expected = copy.deepcopy(store.state)
    finally:
        store.close()
    reopened = TaskStore(destination)
    try:
        assert reopened.state == expected
    finally:
        reopened.close()


@pytest.mark.real
def test_report_checkpoint_persists_original_locations_with_one_complete_comparison(tmp_path):
    store = _new_checkpoint(tmp_path)
    store.state['config']['diagnostic_logging'] = True
    rows = _stage_checkpoint_reports(store, count=12)
    before = store.state_write_count
    store.checkpoint()
    comparisons = store.state_write_count - before
    assert len({row['storage_group_key'] for row in rows}) == 1
    assert rows[0]['storage_group_key'] == 'checkpoint_g0'
    assert store.state['completed_batches'] == store.persisted_batches == 12
    assert not store.report_buffer
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected
    assert comparisons == 1


def test_mixed_summary_encoding_and_shared_filtering_use_real_memory_sql(monkeypatch):
    store = _new_checkpoint()
    store.state['config']['diagnostic_logging'] = True
    store.defer_persistence = True
    report = dict(status='success', request=dict(purpose='search'), data_key='batch-0',
        dps=100., samples=2, variance=0, storage_group_key='checkpoint_g0', batch_index=0, scenario='nominal')
    summaries = {
        'cached': dict(status='success', request=dict(purpose='search'), data_key='cached',
                       dps=101, samples=2, variance=0),
        'final': dict(status='success', request=dict(purpose='final'), data_key='final',
                      dps=102, samples=2, variance=0),
        'failed': dict(status='failed', data_key='failed', error='constructed failure'),
    }
    for key, row in summaries.items():
        store.put_batch(key, row)
    encodings = {}
    dumps = json.dumps

    def counted_dumps(value, *args, **kwargs):
        if isinstance(value, dict) and value.get('data_key') and value.get('status'):
            key = value['data_key']
            encodings[key] = encodings.get(key, 0) + 1
        return dumps(value, *args, **kwargs)

    monkeypatch.setattr(json, 'dumps', counted_dumps)
    try:
        # 直接测SQL提交规则；不冒充flush的物理发布或原引用位置回填。
        store._commit_report_group('checkpoint_g0', 0, [('batch-0', report)])
        store.checkpoint()  # 空report_buffer使真实flush自然返回，不替换其返回值。
        assert store.state_write_count == 2
        store.defer_persistence = False
        immediate = dict(summaries['cached'], data_key='immediate')
        store.put_batch('immediate', immediate)
        assert store.state['completed_batches'] == store.persisted_batches == 4
        assert store.batch('batch-0') == report
        assert all(store.batch(key) == row for key, row in summaries.items())
        assert store.batch('immediate') == immediate
        assert store.db.execute('SELECT key FROM shared.reusable ORDER BY key').fetchall() == [
            ('batch-0',), ('cached',), ('immediate',)]
        assert encodings == {'batch-0': 1, 'cached': 1, 'final': 1, 'failed': 1, 'immediate': 1}
    finally:
        store.diagnostic_logging_override = False
        store.close()


@pytest.mark.real
def test_mixed_checkpoint_and_immediate_batch_encode_each_summary_once(tmp_path, monkeypatch):
    from search import TaskStore

    store = _new_checkpoint(tmp_path)
    store.state['config']['diagnostic_logging'] = True
    _stage_checkpoint_reports(store)
    summaries = {
        'cached': dict(status='success', request=dict(purpose='search'), data_key='cached',
                       dps=101, samples=2, variance=0),
        'final': dict(status='success', request=dict(purpose='final'), data_key='final',
                      dps=102, samples=2, variance=0),
        'failed': dict(status='failed', data_key='failed', error='constructed failure'),
    }
    for key, row in summaries.items():
        store.put_batch(key, row)
    encodings = {}
    dumps = json.dumps

    def counted_dumps(value, *args, **kwargs):
        if isinstance(value, dict) and value.get('data_key') and value.get('status'):
            key = value['data_key']
            encodings[key] = encodings.get(key, 0) + 1
        return dumps(value, *args, **kwargs)

    # Observe the real JSON boundary without replacing storage or publication.
    monkeypatch.setattr(json, 'dumps', counted_dumps)
    store.checkpoint()
    assert store.state_write_count == 2  # Mixed summaries still require the final save.
    store.defer_persistence = False
    immediate = dict(summaries['cached'], data_key='immediate')
    store.put_batch('immediate', immediate)
    # 本对象摘要计数/逐值规则在内存SQL节点；此处保真实跨Store共享隔离。
    other = store.destination.parent / 'other-task'
    other.mkdir()
    shared = TaskStore(other)
    try:
        assert shared.batch('batch-0')['storage_group_key'] == 'checkpoint_g0'
        assert shared.batch('cached') == summaries['cached']
        assert shared.batch('immediate') == immediate
        assert shared.batch('final') is None
        assert shared.batch('failed') is None
    finally:
        shared.close()
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected
    # 保留flush→commit真实接线的编码交叉证明，不能由直接_commit冒充。
    assert encodings == {'batch-0': 1, 'cached': 1, 'final': 1, 'failed': 1, 'immediate': 1}


@pytest.mark.parametrize('with_summary', [False, True])
def test_empty_report_checkpoint_still_saves_nested_state_and_summary_count(with_summary):
    store = _new_checkpoint()
    store.state['config']['diagnostic_logging'] = True
    store.defer_persistence = True
    store.state['pending'][0]['receipt']['feedback']['reward'] = .25
    if with_summary:
        store.put_batch('cached', dict(status='success', request=dict(purpose='search'),
            data_key='cached', dps=100, samples=2, variance=0))
    store.checkpoint()
    assert store.state_write_count == 1
    assert store.state.get('completed_batches', 0) == store.persisted_batches == int(with_summary)
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected


@pytest.mark.parametrize('resume', ['same_object', 'reopen'])
@pytest.mark.real
def test_last_report_group_failure_keeps_reliable_reports_for_retry_or_recovery(tmp_path, resume):
    import sqlite3
    from search import TaskStore

    store = _new_checkpoint(tmp_path)
    before = copy.deepcopy(store.state)
    rows = _stage_checkpoint_reports(store, count=13)
    store.db.execute("""CREATE TEMP TRIGGER fail_last_group BEFORE INSERT ON runtime_progress
        WHEN (SELECT count(*) FROM batches)=13
        BEGIN SELECT RAISE(ABORT, 'injected last group failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='injected last group failure'):
        store.checkpoint()
    assert TaskStore.load_state(store.db) == before
    assert store.persisted_batches == 12
    assert len(store.report_buffer) == 13
    assert store.db.execute('SELECT count(*) FROM report_intents').fetchone()[0] == 2
    store.db.execute('DROP TRIGGER fail_last_group')
    if resume == 'same_object':
        store.checkpoint()
    else:
        destination, character = store.destination, store.character
        store.close()
        store = TaskStore(destination)
        store.recover_reports(character, None)
        # Recovery retains the last complete search state, not uncommitted GA changes.
        assert store.state['archive'] == before['archive']
    assert store.state['completed_batches'] == store.persisted_batches == 13
    assert store.state['next_report_group'] == 2
    assert not store.db.execute('SELECT key FROM report_intents').fetchall()
    assert all(store.batch(row['data_key'])['status'] == 'success' for row in rows)
    assert not list((store.destination / 'batches').glob('*/native.json'))
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected
