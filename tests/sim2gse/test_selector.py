"""真实选择器在共同结果中心的选择、恢复和顺序反馈契约。"""
import copy

import pytest

MODEL_HEADER_COLUMNS = [
    'model_key', 'version', 'state_version', 'feature_version', 'reward_version',
    'coba_version', 'numpy_version', 'dimension', 'alpha', 'features', 'seed', 'matrix_format']


def _matrix(record, name):
    import numpy as np
    values = np.frombuffer(record[name + '_bytes'], dtype='<f8')
    return values.reshape(1072, 1072) if name == 'a_inv' else values


def _legacy_record(record, state_version=1):
    legacy = {name: value for name, value in record.items()
              if name not in ('theta_bytes', 'a_inv_bytes', 'matrix_format')}
    legacy.update(state_version=state_version,
        theta=_matrix(record, 'theta').tolist() if record['theta_bytes'] is not None else None,
        a_inv=_matrix(record, 'a_inv').tolist() if record['a_inv_bytes'] is not None else None)
    return legacy


def _write_legacy(record):
    import result_store
    schema = {name: kind for name, kind in result_store.SEARCH_LEARNER_SCHEMA.items()
              if name not in ('theta_bytes', 'a_inv_bytes', 'matrix_format')}
    result_store.write('search_learners', record['model_key'], [record], schema=schema)


def _intent(task='one', decision=1):
    return dict(task_run_id=task, decision_id=decision, parent_identity='parent', pool_digest='pool',
                context=[0.0] * 50, actions=[dict(operation_id=name, features=[0.0] * 21)
                                           for name in ('first', 'second')])


def test_selector_reserves_once_and_settles_shared_latest_model():
    import result_store
    import selector

    first = selector.reserve(_intent())
    initialized = result_store.read_search_learner(selector.MODEL_KEY)
    assert initialized['theta_bytes'] is not None and _matrix(initialized, 'a_inv')[0][0] == 1
    assert first == selector.reserve(_intent())
    other = selector.reserve(_intent('two'))
    assert other['model_version'] > first['model_version']
    assert result_store.read_search_learner(selector.MODEL_KEY) == initialized
    learned = selector.settle(first, 0, 1)
    assert learned['status'] == 'learned'
    trained = result_store.read_search_learner(selector.MODEL_KEY)
    assert _matrix(trained, 'a_inv')[0][0] == .5
    assert trained['settled'] == {'one': 1}
    assert trained['reservations'] == [other]
    assert selector.settle(first, 0, 1)['status'] == 'already_settled'
    with pytest.raises(selector.AlreadySettled):
        selector.reserve(_intent())
    assert selector.settle(other, None, 0, reason='no_common_batch')['status'] == 'no_learn'
    assert result_store.read_search_learner(selector.MODEL_KEY) == trained
    control = result_store.read_search_learner_control(selector.MODEL_KEY)
    assert control['settled'] == {'one': 1, 'two': 1}
    assert control['reservations'] == []
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
    assert _matrix(record, 'theta')[0] == pytest.approx(.0625)
    assert _matrix(record, 'a_inv')[0][0] == pytest.approx(.25)


def test_selector_reloads_after_authoritative_version_read_failure(monkeypatch):
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
        return (selector.settle(second, -.5, 1))

    with pytest.raises(result_store.DataReadError, match='temporary version read failure'):
        act()
    recovered = act()
    assert recovered.get('model_version') == 4
    assert reads == [MODEL_HEADER_COLUMNS, None]


def test_selector_does_not_reset_after_its_authoritative_record_disappears():
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    path = result_store.DATA_ROOT / 'search_learners' / (selector.MODEL_KEY + '.parquet')
    path.unlink()
    for _ in range(2):
        with pytest.raises(result_store.DataReadError):
            selector.reserve(_intent('two'))
        assert not path.exists()


def test_selector_rejects_authoritative_version_rollback_without_losing_its_watermark():
    import result_store
    import selector

    first = selector.reserve(_intent())
    earlier = result_store.read_search_learner(selector.MODEL_KEY)
    selector.settle(first, .25, 1)
    with result_store.search_learner_lock():
        result_store.write_search_learner(earlier)
    for _ in range(2):
        with pytest.raises(result_store.DataReadError):
            selector.settle(first, .25, 1)
        assert result_store.read_search_learner(selector.MODEL_KEY) == earlier


def test_selector_rejects_changed_compatibility_at_the_cached_version():
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    incompatible = result_store.read_search_learner(selector.MODEL_KEY)
    incompatible['feature_version'] = 'future-feature-version'
    with result_store.search_learner_lock():
        result_store.write_search_learner(incompatible)
    for _ in range(2):
        with pytest.raises(ValueError, match='不兼容'):
            selector.reserve(_intent('two'))
        assert result_store.read_search_learner(selector.MODEL_KEY) == incompatible


def test_shared_thread_lock_wait_obeys_feedback_deadline():
    import threading
    import time
    import result_store
    import selector
    from runtime import BudgetExceeded, TaskRuntime

    held, release = threading.Event(), threading.Event()
    def hold_lock():
        with result_store._PUBLICATION_LOCK:
            held.set()
            release.wait()
    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert held.wait(1)
        started = time.monotonic()
        with pytest.raises(BudgetExceeded):
            selector.reserve(_intent(), TaskRuntime(.05))
        assert time.monotonic() - started < .2
    finally:
        release.set()
        holder.join(1)
        assert not holder.is_alive()


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
    if not after_replace:
        from coba.learners import LinUCBLearner
        from unittest.mock import Mock
        learn = LinUCBLearner.learn
        def invalid_learning(learner, *args, **kwargs):
            learn(learner, *args, **kwargs)
            learner._theta[0] = float('nan')
            learner._A_inv[0, 0] = float('inf')
        paths = [result_store.DATA_ROOT / table / (selector.MODEL_KEY + '.parquet')
                 for table in ('search_learners', 'search_learner_controls')]
        original_bytes = [path.read_bytes() for path in paths]
        pending = result_store.read_search_learner(selector.MODEL_KEY)
        writes = Mock(wraps=result_store._SKILL_API['write'])
        with monkeypatch.context() as scoped:
            scoped.setattr(LinUCBLearner, 'learn', invalid_learning)
            scoped.setitem(result_store._SKILL_API, 'write', writes)
            with pytest.raises(ValueError, match='有限'):
                selector.settle(first, .25, 1)
        writes.assert_not_called()
        assert [path.read_bytes() for path in paths] == original_bytes
        assert result_store.read_search_learner(selector.MODEL_KEY) == pending
        assert selector.reserve(_intent()) == first
    fail_once()
    feedback = selector.settle(first, .25, 1)
    assert feedback['status'] == 'learned'
    record = result_store.read_search_learner(selector.MODEL_KEY)
    assert record['version'] == 2 and record['reservations'] == [] and record['settled'] == {'one': 1}
    assert _matrix(record, 'theta')[0] == .125
    assert _matrix(record, 'a_inv')[0][0] == .5
    assert selector.settle(first, .25, 1)['status'] == 'already_settled'
    assert result_store.read_search_learner(selector.MODEL_KEY) == record


def test_selector_roundtrip_restores_next_choice_and_next_native_learning(tmp_path, monkeypatch):
    import result_store
    import selector

    first = selector.reserve(_intent())
    selector.settle(first, .25, 1)
    snapshot = result_store.read_search_learner(selector.MODEL_KEY)
    control = result_store.read_search_learner_control(selector.MODEL_KEY)
    assert snapshot['state_version'] == 3
    assert snapshot['matrix_format'] == 'f64-le-v1'
    assert snapshot['dimension'] == 1072
    assert isinstance(snapshot['theta_bytes'], bytes) and len(snapshot['theta_bytes']) == 8576
    assert isinstance(snapshot['a_inv_bytes'], bytes) and len(snapshot['a_inv_bytes']) == 9193472
    assert snapshot['theta'] is None and snapshot['a_inv'] is None
    assert not {'theta', 'a_inv', 'theta_bytes', 'a_inv_bytes', 'matrix_format'} & control.keys()
    next_intent = _intent(decision=2)
    next_intent['actions'].append(dict(operation_id='third', features=[0.0] * 21))
    expected = selector.reserve(next_intent)
    pending_control = result_store.read_search_learner_control(selector.MODEL_KEY)
    selector.settle(expected, -.5, 1)
    expected_state = result_store.read_search_learner(selector.MODEL_KEY)
    future_intent = _intent(decision=3)
    future = selector.reserve(future_intent)
    selector.settle(future, .125, 1)
    future_state = result_store.read_search_learner(selector.MODEL_KEY)
    # Preserve a real v2 matrix checkpoint m and its newer pending control c.
    import numpy as np
    legacy = {name: value for name, value in snapshot.items()
              if name not in ('theta_bytes', 'a_inv_bytes', 'matrix_format')}
    legacy.update(state_version=2,
        theta=np.frombuffer(snapshot['theta_bytes'], dtype='<f8').tolist(),
        a_inv=np.frombuffer(snapshot['a_inv_bytes'], dtype='<f8').reshape(1072, 1072).tolist())
    pending_control = dict(pending_control, state_version=2)
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'legacy-v2-center')
    old_schema = {name: kind for name, kind in result_store.SEARCH_LEARNER_SCHEMA.items()
                  if name not in ('theta_bytes', 'a_inv_bytes', 'matrix_format')}
    result_store.write('search_learners', selector.MODEL_KEY, [legacy], schema=old_schema)
    # An untouched historical key keeps its original typed arrays in the same table.
    result_store.write('search_learners', 'untouched-history',
                       [dict(legacy, model_key='untouched-history')], schema=old_schema)
    result_store.write('search_learner_controls', selector.MODEL_KEY, [pending_control],
                       schema=result_store.SEARCH_LEARNER_CONTROL_SCHEMA)
    native_write = result_store._SKILL_API['write']
    publications = []
    def observe_write(root, table, key, rows, **kwargs):
        publications.append((table, rows[0]['version'], rows[0].get('phase'), kwargs.get('binary')))
        return native_write(root, table, key, rows, **kwargs)
    with monkeypatch.context() as scoped:
        scoped.setitem(result_store._SKILL_API, 'write', observe_write)
        capabilities = result_store._SKILL_API['DATA_STORE_CAPABILITIES']
        scoped.setitem(result_store._SKILL_API, 'DATA_STORE_CAPABILITIES', ())
        with pytest.raises(result_store.DataReadError, match='binary-write-v1'):
            selector.reserve(next_intent)
        assert publications == []
        scoped.setitem(result_store._SKILL_API, 'DATA_STORE_CAPABILITIES', capabilities)
        assert selector.reserve(next_intent) == expected
    assert publications == [
        ('search_learner_controls', pending_control['version'], 'migrating', None),
        ('search_learners', snapshot['version'], None, True),
        ('search_learner_controls', pending_control['version'], 'active', None)]
    migrated = result_store.read_search_learner(selector.MODEL_KEY)
    migrated_control = result_store.read_search_learner_control(selector.MODEL_KEY)
    assert migrated['version'] == snapshot['version']
    assert migrated_control == dict(pending_control, state_version=3)
    assert migrated['theta_bytes'] == snapshot['theta_bytes']
    assert migrated['a_inv_bytes'] == snapshot['a_inv_bytes']
    assert sorted(result_store.iter_rows(
        'SELECT model_key,state_version FROM search_learners', tables=['search_learners']),
        key=lambda row: row['model_key']) == sorted([
            dict(model_key=selector.MODEL_KEY, state_version=3),
            dict(model_key='untouched-history', state_version=2)], key=lambda row: row['model_key'])
    selector.settle(expected, -.5, 1)
    assert result_store.read_search_learner(selector.MODEL_KEY) == expected_state
    assert selector.reserve(future_intent) == future
    selector.settle(future, .125, 1)
    assert result_store.read_search_learner(selector.MODEL_KEY) == future_state
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'restored-center')
    with result_store.search_learner_lock():
        result_store.write_search_learner_control(dict(control, state_version=2))
        _write_legacy(legacy)
    actual = selector.reserve(next_intent)
    assert actual == expected
    selector.settle(actual, -.5, 1)
    assert result_store.read_search_learner(selector.MODEL_KEY) == expected_state
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'different-empty-center')
    other = selector.reserve(_intent('two'))
    assert other['model_version'] == 1
    assert selector.settle(other, .25, 1)['model_version'] == 2


@pytest.mark.parametrize('phase', ['bootstrap', 'migrating'])
@pytest.mark.parametrize('boundary', ['prepare', 'model'])
def test_selector_restarts_each_format_publication_step_without_repredicting(
        tmp_path, monkeypatch, phase, boundary):
    import runpy
    import result_store
    import selector

    previous = None
    if phase == 'migrating':
        previous = selector.reserve(_intent())
        legacy = _legacy_record(result_store.read_search_learner(selector.MODEL_KEY))
        if boundary == 'prepare':
            selector.reserve(_intent('two'))
            legacy['state_version'] = 2
            legacy_control = dict(result_store.read_search_learner_control(selector.MODEL_KEY), state_version=2)
        monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'legacy-center')
        _write_legacy(legacy)
        if boundary == 'prepare':
            result_store.write_search_learner_control(legacy_control)
        else:
            prepared = {name: value for name, value in legacy.items() if name not in ('theta', 'a_inv')}
            prepared.update(state_version=2, base_version=legacy['version'], phase='migrating')
            result_store.write_search_learner_control(prepared)
    elif boundary == 'prepare':
        result_store.write_search_learner_control(dict(
            model_key=selector.MODEL_KEY, version=0, state_version=2,
            feature_version=selector.FEATURE_VERSION, reward_version=selector.REWARD_VERSION,
            coba_version=selector.COBA_VERSION, numpy_version=selector.NUMPY_VERSION,
            dimension=1072, alpha=1, features=selector.FEATURES, seed=1, rng_state=1,
            reservations=[], settled={}, base_version=0, phase='bootstrap'))
    native_write = result_store._SKILL_API['write']
    expected_version = 0 if phase == 'bootstrap' else 1

    def crash(root, table, key, rows, **kwargs):
        record = rows[0]
        targeted = (table == 'search_learners' and record.get('state_version') == 3
                    and record.get('version') == expected_version) if boundary == 'model' else (
            table == 'search_learner_controls' and record.get('phase') == phase
            and record.get('version') == (2 if phase == 'migrating' else expected_version))
        if targeted:
            # 下一次写入前与本次替换后具有相同持久状态，只保留这两个不同恢复点。
            native_write(root, table, key, rows, **kwargs)
            raise SystemExit('constructed process exit at format publication')
        return native_write(root, table, key, rows, **kwargs)

    monkeypatch.setitem(result_store._SKILL_API, 'write', crash)
    instance = runpy.run_path(selector.__file__)
    with pytest.raises(SystemExit, match='format publication'):
        instance['reserve'](_intent('two' if previous else 'one'))
    monkeypatch.setitem(result_store._SKILL_API, 'write', native_write)
    restarted = runpy.run_path(selector.__file__)
    first = restarted['reserve'](_intent())
    assert first['model_version'] == 1 and first['operation_id'] == 'first'
    assert first['probability'] == .5
    if previous:
        assert first == previous
    other = restarted['reserve'](_intent('two'))
    assert other['model_version'] == 2 and other['operation_id'] == 'second'
    assert restarted['reserve'](_intent('two')) == other
    assert restarted['settle'](first, .25, 1)['status'] == 'learned'
    assert restarted['settle'](first, .25, 1)['status'] == 'already_settled'
    record = result_store.read_search_learner(selector.MODEL_KEY)
    assert record['state_version'] == 3 and record['version'] == 3
    assert _matrix(record, 'theta')[0] == .125 and _matrix(record, 'a_inv')[0][0] == .5


@pytest.mark.parametrize('damage', ['missing', 'wrong_base'])
def test_selector_never_falls_back_to_full_when_active_control_is_invalid(monkeypatch, damage):
    import runpy
    import result_store
    import selector

    selector.reserve(_intent())
    earlier_control = result_store.read_search_learner_control(selector.MODEL_KEY)
    selector.reserve(_intent('two'))
    full = result_store.read_search_learner(selector.MODEL_KEY)
    path = result_store.DATA_ROOT / 'search_learner_controls' / (selector.MODEL_KEY + '.parquet')
    if damage == 'missing':
        path.unlink()
    else:
        control = (result_store.read_search_learner_control(selector.MODEL_KEY))
        control['base_version'] = 2
        with result_store.search_learner_lock():
            result_store.write_search_learner_control(control)
    before = path.read_bytes() if path.exists() else None
    instance = runpy.run_path(selector.__file__)['reserve']
    with pytest.raises(result_store.DataReadError):
        instance(_intent('three'))
    assert result_store.read_search_learner(selector.MODEL_KEY) == full
    assert (path.read_bytes() if path.exists() else None) == before
    if damage == 'wrong_base':
        from unittest.mock import Mock
        result_store.write_search_learner_control(dict(earlier_control, phase='migrating'))
        before = path.read_bytes()
        writes = Mock(wraps=result_store._SKILL_API['write'])
        with monkeypatch.context() as scoped:
            scoped.setitem(result_store._SKILL_API, 'write', writes)
            with pytest.raises(result_store.DataReadError):
                runpy.run_path(selector.__file__)['reserve'](_intent('three'))
        writes.assert_not_called()
        assert path.read_bytes() == before
        assert result_store.read_search_learner(selector.MODEL_KEY) == full


def test_selector_refuses_a_legacy_writer_update_during_prepared_migration(tmp_path, monkeypatch):
    import runpy
    import result_store
    import selector

    selector.reserve(_intent())
    legacy = _legacy_record(result_store.read_search_learner(selector.MODEL_KEY))
    prepared = {name: value for name, value in legacy.items() if name not in ('theta', 'a_inv')}
    prepared.update(state_version=3, base_version=1, phase='migrating')
    monkeypatch.setattr(result_store, 'DATA_ROOT', tmp_path / 'interrupted-migration')
    # While v1 is still visible, an old writer can settle the receipt without learning.
    legacy.update(version=2, reservations=[], settled={'one': 1})
    with result_store.search_learner_lock():
        result_store.write_search_learner_control(prepared)
        _write_legacy(legacy)
    restarted = runpy.run_path(selector.__file__)
    with pytest.raises(result_store.DataReadError, match='迁移控制记录冲突'):
        restarted['reserve'](_intent('two'))
    assert result_store.read_search_learner(selector.MODEL_KEY) == legacy
    assert result_store.read_search_learner_control(selector.MODEL_KEY) == prepared


def test_selector_does_not_reinitialize_missing_matrices_as_new_experience(monkeypatch):
    import runpy
    import result_store
    import selector

    first = selector.reserve(_intent())
    initialized = result_store.read_search_learner(selector.MODEL_KEY)
    selector.settle(first, .25, 1)
    broken = result_store.read_search_learner(selector.MODEL_KEY)
    broken.update(theta_bytes=None, a_inv_bytes=None)

    with result_store.search_learner_lock():
        result_store.write_search_learner(broken)
    control = result_store.read_search_learner_control(selector.MODEL_KEY)
    restarted = runpy.run_path(selector.__file__)
    with pytest.raises((ValueError, result_store.DataReadError)):
        restarted['reserve'](_intent('three'))
    assert result_store.read_search_learner(selector.MODEL_KEY) == broken
    assert result_store.read_search_learner_control(selector.MODEL_KEY) == control
    from unittest.mock import Mock
    legacy = {name: value for name, value in broken.items()
              if name not in ('theta_bytes', 'a_inv_bytes', 'matrix_format')}
    legacy.update(state_version=2, version=0, rng_state=1, reservations=[], settled={})
    advanced = {name: value for name, value in initialized.items()
                if name not in ('theta', 'a_inv', 'theta_bytes', 'a_inv_bytes', 'matrix_format')}
    advanced.update(state_version=2, base_version=0, phase='active')
    _write_legacy(legacy)
    result_store.write_search_learner_control(advanced)
    paths = [result_store.DATA_ROOT / table / (selector.MODEL_KEY + '.parquet')
             for table in ('search_learners', 'search_learner_controls')]
    before = [path.read_bytes() for path in paths]
    writes = Mock(wraps=result_store._SKILL_API['write'])
    with monkeypatch.context() as scoped:
        scoped.setitem(result_store._SKILL_API, 'write', writes)
        with pytest.raises(result_store.DataReadError):
            runpy.run_path(selector.__file__)['reserve'](_intent('three'))
    writes.assert_not_called()
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize('operation,after_replace', [('reserve', True), ('no_learn', False)])
def test_active_control_write_errors_preserve_receipts_rng_and_unlearned_matrices(
        monkeypatch, operation, after_replace):
    import runpy
    import result_store
    import selector

    first = selector.reserve(_intent())
    full = result_store.read_search_learner(selector.MODEL_KEY)
    other = selector.reserve(_intent('two')) if operation == 'no_learn' else None
    native_write = result_store._SKILL_API['write']
    failed = []

    def fail_once(root, table, key, rows, **kwargs):
        if table == 'search_learner_controls' and not failed:
            failed.append(True)
            if after_replace:
                native_write(root, table, key, rows, **kwargs)
            raise OSError('constructed active control publication failure')
        return native_write(root, table, key, rows, **kwargs)

    monkeypatch.setitem(result_store._SKILL_API, 'write', fail_once)
    if operation == 'reserve':
        other = selector.reserve(_intent('two'))
    else:
        assert selector.settle(first, None, 0)['status'] == 'no_learn'
    assert failed == [True]
    monkeypatch.setitem(result_store._SKILL_API, 'write', native_write)
    restarted = runpy.run_path(selector.__file__)
    assert restarted['reserve'](_intent('two')) == other
    assert other['model_version'] == 2 and other['operation_id'] == 'second'
    if operation == 'no_learn':
        assert restarted['settle'](first, None, 0)['status'] == 'already_settled'
        with pytest.raises(selector.AlreadySettled):
            selector.reserve(_intent())
    else:
        assert restarted['reserve'](_intent()) == first
    control = result_store.read_search_learner_control(selector.MODEL_KEY)
    assert control['version'] == (3 if operation == 'no_learn' else 2)
    assert control['rng_state'] == 856855263  # Second native Coba draw with the pinned seed.
    assert result_store.read_search_learner(selector.MODEL_KEY) == full
