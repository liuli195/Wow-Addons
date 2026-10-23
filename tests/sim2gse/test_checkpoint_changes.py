"""公开任务与恢复接缝保护局部检查点的完整状态。"""
import copy
import json

import pytest




def _new_checkpoint(tmp_path):
    from search import TaskStore

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
    store.close()
    reopened = TaskStore(destination)
    try:
        return copy.deepcopy(reopened.state)
    finally:
        reopened.close()


@pytest.mark.parametrize('change', ['reorder', 'delete', 'append', 'new_field', 'whole_archive'])
def test_checkpoint_structural_changes_fall_back_without_losing_unmarked_nested_state(tmp_path, change):
    store = _new_checkpoint(tmp_path)
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


def test_scoped_checkpoint_deletes_an_explicit_field(tmp_path):
    store = _new_checkpoint(tmp_path)
    del store.state['pending']
    store.save(fields=('pending',))
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected
    assert 'pending' not in expected


def test_scoped_checkpoint_failure_rolls_back_and_retry_persists_all_changes(tmp_path):
    import sqlite3
    from search import TaskStore

    store = _new_checkpoint(tmp_path)
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
