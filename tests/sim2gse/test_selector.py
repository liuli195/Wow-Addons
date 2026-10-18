"""真实选择器在共同结果中心的选择、恢复和顺序反馈契约。"""
import copy

import pytest

MODEL_HEADER_COLUMNS = [
    'model_key', 'version', 'state_version', 'feature_version', 'reward_version',
    'coba_version', 'numpy_version', 'dimension', 'alpha', 'features', 'seed']


def _intent(task='one', decision=1):
    return dict(task_run_id=task, decision_id=decision, parent_identity='parent', pool_digest='pool',
                context=[0.0] * 50, actions=[dict(operation_id=name, features=[0.0] * 21)
                                           for name in ('first', 'second')])


def test_selector_reserves_once_and_settles_shared_latest_model():
    import selector

    first = selector.reserve(_intent())
    assert first == selector.reserve(_intent())
    other = selector.reserve(_intent('two'))
    assert other['model_version'] > first['model_version']
    learned = selector.settle(first, .25, 1)
    assert learned['status'] == 'learned'
    assert selector.settle(first, .25, 1)['status'] == 'already_settled'
    with pytest.raises(selector.AlreadySettled):
        selector.reserve(_intent())
    assert selector.settle(other, None, 0, reason='no_common_batch')['status'] == 'no_learn'
    next_choice = selector.reserve(_intent(decision=2))
    assert next_choice['model_version'] > learned['model_version']
    changed = copy.deepcopy(_intent(decision=2))
    changed['parent_identity'] = 'foreign'
    with pytest.raises(ValueError, match='身份'):
        selector.reserve(changed)


def test_selector_reuses_successful_shared_version_without_rereading_model(monkeypatch):
    import result_store
    import selector

    native_read = result_store._SKILL_API['read_key']
    reads = []

    def read(root, table, key, **kwargs):
        if table == 'search_learners':
            reads.append(kwargs.get('columns'))
        return native_read(root, table, key, **kwargs)

    monkeypatch.setitem(result_store._SKILL_API, 'read_key', read)
    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    reads.clear()

    second = selector.reserve(_intent(decision=2))
    assert selector.reserve(_intent(decision=2)) == second
    assert selector.settle(second, -.5, 1)['status'] == 'learned'
    assert selector.settle(second, -.5, 1)['status'] == 'already_settled'
    with pytest.raises(selector.AlreadySettled):
        selector.reserve(_intent(decision=2))
    assert len(reads) == 5
    assert all(columns == MODEL_HEADER_COLUMNS for columns in reads)


def test_selector_reloads_when_an_independent_instance_updates_the_shared_version(monkeypatch):
    import runpy
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    # A separate instance has its own cache and publishes through the real shared center.
    other = runpy.run_path(selector.__file__)
    other_receipt = other['reserve'](_intent('two'))
    other_feedback = other['settle'](other_receipt, .5, 1)
    native_read = result_store._SKILL_API['read_key']
    reads = []

    def read(root, table, key, **kwargs):
        if table == 'search_learners':
            reads.append(kwargs.get('columns'))
        return native_read(root, table, key, **kwargs)

    monkeypatch.setitem(result_store._SKILL_API, 'read_key', read)
    second = selector.reserve(_intent(decision=2))
    assert second['model_version'] == other_feedback['model_version'] + 1
    feedback = selector.settle(second, -.5, 1)
    assert feedback['model_version'] == 6
    assert reads == [MODEL_HEADER_COLUMNS, None, MODEL_HEADER_COLUMNS]
    record = result_store.read_search_learner(selector.MODEL_KEY)
    assert record['settled'] == {'one': 2, 'two': 1}
    assert record['theta'][0] == pytest.approx(.0625)
    assert record['a_inv'][0][0] == pytest.approx(.25)


@pytest.mark.parametrize('operation', ['reserve', 'settle'])
def test_selector_reloads_after_authoritative_version_read_failure(monkeypatch, operation):
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    second = selector.reserve(_intent(decision=2))
    native_read = result_store._SKILL_API['read_key']
    reads = []

    def read(root, table, key, **kwargs):
        if table == 'search_learners':
            reads.append(kwargs.get('columns'))
            if len(reads) == 1:
                raise OSError('constructed temporary version read failure')
        return native_read(root, table, key, **kwargs)

    monkeypatch.setitem(result_store._SKILL_API, 'read_key', read)

    def act():
        return (selector.reserve(_intent(decision=3)) if operation == 'reserve'
                else selector.settle(second, -.5, 1))

    with pytest.raises(result_store.DataReadError, match='temporary version read failure'):
        act()
    recovered = act()
    assert recovered.get('model_version') == 4
    assert reads == [MODEL_HEADER_COLUMNS, None]


@pytest.mark.parametrize('operation', ['reserve', 'settle'])
def test_selector_does_not_reset_after_its_authoritative_record_disappears(operation):
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    path = result_store.DATA_ROOT / 'search_learners' / (selector.MODEL_KEY + '.parquet')
    path.unlink()
    for _ in range(2):
        with pytest.raises(result_store.DataReadError):
            if operation == 'reserve':
                selector.reserve(_intent('two'))
            else:
                selector.settle(first, .25, 1)
        assert not path.exists()


@pytest.mark.parametrize('operation', ['reserve', 'settle'])
def test_selector_rejects_authoritative_version_rollback_without_losing_its_watermark(operation):
    import result_store
    import selector

    first = selector.reserve(_intent())
    earlier = result_store.read_search_learner(selector.MODEL_KEY)
    selector.settle(first, .25, 1)
    with result_store.search_learner_lock():
        result_store.write_search_learner(earlier)
    for _ in range(2):
        with pytest.raises(result_store.DataReadError):
            if operation == 'reserve':
                selector.reserve(_intent('two'))
            else:
                selector.settle(first, .25, 1)
        assert result_store.read_search_learner(selector.MODEL_KEY) == earlier


@pytest.mark.parametrize('operation,field,value', [
    ('reserve', 'feature_version', 'future-feature-version'),
    ('settle', 'features', ['future-interactions']),
])
def test_selector_rejects_changed_compatibility_at_the_cached_version(operation, field, value):
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    incompatible = result_store.read_search_learner(selector.MODEL_KEY)
    incompatible[field] = value
    with result_store.search_learner_lock():
        result_store.write_search_learner(incompatible)
    for _ in range(2):
        with pytest.raises(ValueError, match='不兼容'):
            if operation == 'reserve':
                selector.reserve(_intent('two'))
            else:
                selector.settle(first, .25, 1)
        assert result_store.read_search_learner(selector.MODEL_KEY) == incompatible


def test_selector_can_start_in_a_different_empty_center(tmp_path, monkeypatch):
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'different-empty-center')
    other = selector.reserve(_intent('two'))
    assert other['model_version'] == 1
    assert selector.settle(other, .25, 1)['model_version'] == 2


def test_shared_thread_lock_wait_obeys_feedback_deadline():
    import threading
    import time
    import result_store
    import selector
    from runtime import BudgetExceeded, TaskRuntime

    held = threading.Event()
    def hold_lock():
        with result_store._PUBLICATION_LOCK:
            held.set()
            time.sleep(.4)
    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert held.wait(1)
    started = time.monotonic()
    try:
        with pytest.raises(BudgetExceeded):
            selector.reserve(_intent(), TaskRuntime(.05))
        assert time.monotonic() - started < .2
    finally:
        holder.join()


def test_features_use_all_findings_and_real_input_resource_window_denominators():
    import selector

    window = dict(sample_id=1, effect_id=7, instance_id=8, start=0, end=100)
    diagnostic = dict(rules=[
        dict(name='one', state='a', template='短期增益利用', status='diagnosed', findings=[
            dict(kind='missed_short_window', certainty='hypothesis', input_index=0, window=window)]),
        dict(name='two', state='a', template='资源近满与溢出处理', status='unknown', findings=[
            dict(kind='near_full_opportunity', certainty='hypothesis', input_index=0)])])
    payload = dict(scope=dict(sample_id=1, complete=True), inputs=[
        dict(sample_id=1, input_index=0, time=25), dict(sample_id=1, input_index=1, time=75)],
        resource_events=[dict(object='energy', sample_id=1, input_index=0, current=50, maximum=100),
                         dict(object='energy', sample_id=1, input_index=1, current=90)],
        action_observations=[dict(object='hit', sample_id=1, input_index=0, attempt=True, success=False),
                             dict(object='hit', sample_id=1, input_index=1, attempt=True, success=True)])
    context = selector.context_features(diagnostic, payload, {'energy': dict(kind='resource', native_identity='energy')})
    assert len(context) == 50
    assert context[selector.FINDING_KINDS.index('missed_short_window')] == .5
    assert context[23:30] == [1, 0, 1, 0, 1, .5, 1]
    assert context[30:38] == [1, 1, .25, 1, .25, 1, .25, 1]
    assert context[38:46] == [.5, 1, .5, 1, .5, 1, .5, 1]
    assert context[46:50] == [.5, 1, .5, 1]
    program = [['start'], dict(kind='Loop', count=2, blocks=[['one'], ['two']])]
    operations = [dict(operation='move', source_path=[1, 0], destination_path=[1, 2], count=1,
                       contributors=[dict(rule='one', state='a')]),
                  dict(operation='insert', source_path=None, destination_path=[1, 0], count=1,
                       block=['new'], contributors=[])]
    actions = selector.action_features(diagnostic, program, operations)
    assert len(actions) == 2 and actions[0] is not actions[1]
    assert len(actions[0]) == 21
    assert actions[0][13:] == pytest.approx([.4, 1, .6, 1, .2, 1, 0, 1])
    assert actions[1][19:] == pytest.approx([.4, 1])


@pytest.mark.parametrize('after_replace', [False, True])
def test_selector_recovers_atomic_write_errors_without_duplicate_prediction_or_learning(monkeypatch, after_replace):
    import result_store
    import selector

    native_write = result_store._SKILL_API['write']

    def fail_once():
        calls = []

        def write(*args, **kwargs):
            if not calls:
                calls.append(True)
                if after_replace:
                    native_write(*args, **kwargs)
                raise OSError('constructed storage failure around atomic replacement')
            return native_write(*args, **kwargs)

        monkeypatch.setitem(result_store._SKILL_API, 'write', write)

    fail_once()
    first = selector.reserve(_intent())
    assert first == selector.reserve(_intent())
    # With this native seed, the first equal-valued action is selected with probability 1/2.
    assert first['operation_id'] == 'first' and first['probability'] == .5
    fail_once()
    feedback = selector.settle(first, .25, 1)
    assert feedback['status'] == 'learned'
    record = result_store.read_search_learner(selector.MODEL_KEY)
    assert record['version'] == 2 and record['reservations'] == [] and record['settled'] == {'one': 1}
    assert record['theta'][0] == .125
    assert record['a_inv'][0][0] == .5
    assert selector.settle(first, .25, 1)['status'] == 'already_settled'
    assert result_store.read_search_learner(selector.MODEL_KEY) == record


def test_selector_roundtrip_restores_next_choice_and_next_native_learning(tmp_path, monkeypatch):
    import result_store
    import selector

    initial_root = result_store.DATA_ROOT
    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    snapshot = result_store.read_search_learner(selector.MODEL_KEY)
    next_intent = _intent(decision=2)
    next_intent['actions'].append(dict(operation_id='third', features=[0.0] * 21))
    expected = selector.reserve(next_intent)
    selector.settle(expected, -.5, 1)
    expected_state = result_store.read_search_learner(selector.MODEL_KEY)
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'restored-center')
    with result_store.search_learner_lock():
        result_store.write_search_learner(snapshot)
    actual = selector.reserve(next_intent)
    assert actual == expected
    selector.settle(actual, -.5, 1)
    assert result_store.read_search_learner(selector.MODEL_KEY) == expected_state
    monkeypatch.setattr(result_store, 'DATA_ROOT', initial_root)


def test_missing_window_association_or_resource_observation_does_not_invent_a_denominator():
    import selector

    diagnostic = dict(rules=[dict(status='unknown', findings=[
        dict(kind='unknown', certainty='unknown', window=dict(effect_id=1, instance_id=1))])])
    payload = dict(scope=dict(sample_id=1, complete=True),
                   inputs=[dict(sample_id=1, input_index=0, time=10)])
    objects = {'energy': dict(kind='resource', native_identity='energy')}
    features = selector.context_features(diagnostic, payload, objects)
    assert features[30:46] == [0.0] * 16


def test_resource_aliases_share_one_actual_observation_and_detect_contradictions():
    import selector

    diagnostic = dict(rules=[])
    payload = dict(scope=dict(sample_id=1, complete=True),
        inputs=[dict(sample_id=1, input_index=0, time=10)], resource_events=[
            dict(object='first_alias', sample_id=1, input_index=0, current=50, maximum=100)])
    objects = {name: dict(kind='resource', native_identity='energy') for name in ('first_alias', 'second_alias')}
    assert selector.context_features(diagnostic, payload, objects)[38:46] == [1, 1, .5, 1, .5, 1, .5, 1]
    payload['resource_events'].append(dict(object='second_alias', sample_id=1, input_index=0, current=75, maximum=100))
    assert selector.context_features(diagnostic, payload, objects)[38:46] == [0, 1, 0, 0, 0, 0, 0, 0]
