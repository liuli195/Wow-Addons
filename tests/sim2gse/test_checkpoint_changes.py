"""公开任务与恢复接缝保护局部检查点的完整状态。"""
import copy
import json

import pytest


@pytest.mark.parametrize('diagnostic_logging', [False, True])
def test_public_task_scoped_checkpoints_restore_every_nested_change(tmp_path, monkeypatch, diagnostic_logging):
    import search
    from task import read_task, run_task
    from test_character_export import sample_profile
    from test_search import _guided_search_boundary

    scoped = []
    original = search.TaskStore

    class CheckedStore(original):
        def save(self, **changes):
            with self.lock:
                super().save(**changes)
                if changes.get('fields') is not None and not self.report_buffer:
                    # Compare the entire recoverable state, including nested observations
                    # and coupled receipts, rather than trusting the supplied field list.
                    assert self.load_state(self.db) == json.loads(json.dumps(self.state))
                    scoped.append(changes)

    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    monkeypatch.setattr(search, 'TaskStore', CheckedStore)
    with _guided_search_boundary(tmp_path, [[['outbreak'], ['death_coil']]]):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=2, round_candidate_limit=1, batch_targets=(2,), iterations=2,
            validation_batches=1, max_processes=1, input_interval_ms=200,
            diagnostic_logging=diagnostic_logging,
            search_observability='full' if diagnostic_logging else 'off'))
        saved = read_task(tmp_path / 'task', include_search_records=True)

    assert result['status'] == saved['status'] == 'completed'
    assert saved['selected_candidate_key'] == result['selected_candidate_key']
    assert scoped, 'The public search must use scoped checkpoints, not rescan every archive.'
    saved_fields = set().union(*(row['fields'] for row in scoped))
    assert {'selection_feedback_intents', 'selection_feedback_incomplete',
            'pending', 'rule_steps', 'selection_generation'} <= saved_fields


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


def test_scoped_checkpoint_preserves_nested_receipts_and_selected_archive(tmp_path):
    store = _new_checkpoint(tmp_path)
    store.state['pending'][0]['receipt']['feedback']['reward'] = .25
    store.state['archive'][1]['evidence']['samples'].append(3)
    store.save(fields=('pending',), archive_keys=('second',))
    expected = copy.deepcopy(store.state)
    assert _reopen_checkpoint(store) == expected
    assert expected['pending'][0]['receipt']['feedback']['reward'] == .25
    assert expected['archive'][1]['evidence']['samples'] == [2, 3]


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


def _new_feedback_checkpoint(tmp_path):
    from selector import reserve

    store = _new_checkpoint(tmp_path)
    receipt = reserve(dict(task_run_id='checkpoint', decision_id=1, parent_identity='first',
        pool_digest='pool', context=[0.0] * 50,
        actions=[dict(operation_id=name, features=[0.0] * 21) for name in ('first', 'second')]))
    step = dict(selection=receipt, parent_candidate_key='first')
    before = dict(data_key='before', request=dict(seed=1, program='parent'), dps=100., samples=2)
    after = dict(data_key='after', request=dict(seed=1, program='child'), dps=125., samples=2)
    store.state['archive'][0]['batches'] = [before]
    store.state['archive'][1]['rule_step'] = copy.deepcopy(step)
    store.state.update(pending=[dict(rule_step=copy.deepcopy(step), score_batches=[after])],
        rule_steps={'operation': copy.deepcopy(step)}, selection_feedback_intents={},
        selection_feedback_incomplete=False, errors=[dict(error='previous candidate failed')])
    store.save()
    return store, store.state['pending'][0]


def test_feedback_finalization_retries_complete_checkpoint_after_database_failure(tmp_path):
    import sqlite3
    from search import freeze_selection_feedback, reconcile_selection_feedback
    from selector import settle

    store, work = _new_feedback_checkpoint(tmp_path)
    freeze_selection_feedback(store, work, work['score_batches'])
    receipt = copy.deepcopy(work['rule_step']['selection'])
    failures = [True]
    store.db.create_function('fail_feedback_checkpoint_once', 0,
        lambda: failures.pop() if failures else False)
    # Both receipt updates and intent deletion execute before the final SQL fails.
    # The next transaction, in finalization, is allowed to commit normally.
    store.db.execute("""CREATE TEMP TRIGGER fail_feedback_checkpoint BEFORE INSERT ON runtime_progress
        WHEN fail_feedback_checkpoint_once()
        BEGIN SELECT RAISE(ABORT, 'injected feedback checkpoint failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='injected feedback checkpoint failure'):
        reconcile_selection_feedback(store)
    expected = copy.deepcopy(store.state)
    restored = _reopen_checkpoint(store)

    assert not failures
    assert restored == expected
    assert restored['selection_feedback_intents'] == {}
    assert restored['selection_feedback_incomplete'] is False
    feedback = restored['pending'][0]['rule_step']['selection']['feedback']
    assert feedback['status'] == 'learned'
    assert feedback['reward'] == .25
    assert feedback == restored['rule_steps']['operation']['selection']['feedback']
    assert feedback == restored['archive'][1]['rule_step']['selection']['feedback']
    # Replaying the durable receipt must not learn the same observation twice.
    assert settle(receipt, .25, 1)['status'] == 'already_settled'


def test_freezing_failed_candidate_keeps_an_additional_error_before_recovery(tmp_path):
    from search import freeze_selection_feedback

    store, work = _new_feedback_checkpoint(tmp_path)
    store.state['errors'].append(dict(error='next candidate failed'))
    freeze_selection_feedback(store, work, [], reason='candidate_failed')
    restored = _reopen_checkpoint(store)

    assert restored['errors'] == [dict(error='previous candidate failed'),
                                  dict(error='next candidate failed')]
    assert restored['selection_feedback_incomplete'] is True
    assert restored['selection_feedback_intents']['1']['reason'] == 'candidate_failed'
