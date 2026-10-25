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
