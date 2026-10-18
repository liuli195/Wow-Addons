"""同次外部引擎证据经公开任务入口交付诊断与合法操作。"""
import copy
import json
from unittest.mock import patch
import pytest

from task import TaskError, read_task, resume_task, run_task
from test_character_export import sample_profile
from test_engine import apl_pool_reference
from test_rule_initialization import _configure_opener, _opener_pack
from test_search import _apl_task_boundary, _fast_evaluate


def _condition_pack():
    from rule_config import DEFAULT_PATH
    template = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['条件触发与CD使用']
    pack = _opener_pack({'first': 'outbreak', 'consumer': 'death_coil',
        'counter': dict(kind='state', native_identity='fixture_counter'),
        'editable': dict(kind='range', segments='ordinary_loop',
            allow_units=['action_block', 'wait_block'], preserve_block_contents=True,
            respect_approved_protection=True)},
        [dict(action='first', source_step=1), dict(action='consumer', source_step=2)])
    # 模板和对象可改名，程序不得依赖模板、职业或技能ID分派。
    pack['general']['templates'] = {'renamed-template': copy.deepcopy(template)}
    arguments = dict(action='consumer', priority_refs=[], edit_range='editable', state='counter',
        compare='eq', value=1, activation_effect=None, activation_expected=True)
    pack['configurations'][0]['states']['only']['priority'] = [
        dict(name='supported opportunity', template='renamed-template', arguments=arguments),
        dict(name='inactive condition', template='renamed-template', arguments=dict(arguments, value=2))]
    return pack


def _observed_evaluate(*args, **kwargs):
    """仅替换已存在的外部引擎边界，不替换解释器或编辑器。"""
    kwargs.pop('rule_observation_request', None)
    result = _fast_evaluate(*args, **kwargs)
    inputs = [dict(input_index=i, time=ms, sample_id=1, event_index=i,
                   source_step=i % 2, input_source='loop')
              for i, ms in enumerate(result['input_times'])]
    result['report']['sim']['players'][0]['sim2gse_rule_observations'] = dict(
        protocol=1, scope=dict(sample_selection='first_scored_complete', sample_id=1,
            start_ms=0, end_ms=180000, complete=True), inputs=inputs,
        action_observations=[dict(row, object='consumer', native_qualified=True,
            input_allowed=True, actual_form='death_coil', base_button='death_coil',
            attempt=False, success=False, earliest_execute=row['time'],
            occupancy_start=row['time'], occupancy_end=row['time'] + 200,
            occupancy_domains=['player_gcd'], target_id=1) for row in inputs],
        state_observations=[dict(row, object='counter', value=1 if row['input_index'] == 0 else 0)
                            for row in inputs], effect_observations=[])
    return result


@pytest.mark.parametrize('diagnostic_logging', [False, True])
def test_public_task_exposes_same_batch_complete_diagnostics_and_legal_pool(tmp_path, monkeypatch, diagnostic_logging):
    import sequence
    pack = _condition_pack()
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1, diagnostic_logging=diagnostic_logging))
        saved = read_task(tmp_path / 'task', include_search_records=True)
        diagnosis = result['search']['records'][0]['rule_diagnostics']
        with pytest.raises(TaskError, match='候选预算'):
            resume_task(tmp_path / 'task', rule_step=dict(parent_identity=diagnosis['parent_identity'],
                operation_id=diagnosis['pool']['operations'][0]['operation_id']))
    assert scoring.call_count == 1
    diagnosis = result['search']['records'][0]['rule_diagnostics']
    assert diagnosis == saved['search']['rule_diagnostics']
    assert diagnosis == saved['search']['records'][0]['rule_diagnostics']
    assert ('costs' in diagnosis) is diagnostic_logging
    assert diagnosis['observation_scope']['sample_selection'] == 'first_scored_complete'
    assert diagnosis['evidence']['batch_key'] == result['search']['records'][0]['batches'][0]['data_key']
    assert [row['name'] for row in diagnosis['rules']] == ['supported opportunity', 'inactive condition']
    assert [row['kind'] for row in diagnosis['rules'][0]['findings']] == ['missed_opportunity']
    assert diagnosis['rules'][1]['status'] == 'not_applicable'
    assert diagnosis['pool']['complete'] is True
    operations = diagnosis['pool']['operations']
    assert [(row['operation'], row['source_path'], row['destination_path']) for row in operations] == [
        ('move', [1], [0]), ('insert', None, [0])]
    assert all(row['operation_id'] and row['contributors'] for row in operations)


def test_public_checkpoint_keeps_one_diagnostic_and_restores_the_complete_result(tmp_path, monkeypatch):
    import sequence, sqlite3
    pack = _condition_pack()
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    destination = tmp_path / 'task'
    config = dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                  iterations=2, validation_batches=1)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate) as scoring:
        result = run_task(source, destination, simulation_config=dict(scene='single_target'), search_config=config)
        before = read_task(destination, include_search_records=True)
        with sqlite3.connect(destination / 'task.sqlite3') as database:
            physical, = [json.loads(row[0]) for row in database.execute('SELECT value FROM state_archive')]
        # The current task's full diagnostic remains in its first scored receipt.
        # The archive's second equivalent copy is a checked, local reference.
        assert 'rule_diagnostics' not in physical
        assert physical['rule_diagnostics_ref']['parent_identity'] == before['search']['rule_diagnostics']['parent_identity']
        canonical = physical['batches'][0]['rule_diagnostics']
        assert canonical == before['search']['rule_diagnostics']
        resumed = resume_task(destination)
        after = read_task(destination, include_search_records=True)
    assert scoring.call_count == 1
    assert resumed['status'] == after['status'] == result['status'] == 'completed'
    assert after['search'] == dict(before['search'], rule_steps={}, selection_feedback_incomplete=False)
    assert after['search']['records'][0]['rule_diagnostics'] == canonical


@pytest.mark.parametrize('representation', ['legacy_equal', 'legacy_distinct', 'bad_parent', 'future_version', 'missing_source'])
def test_public_resume_checks_diagnostic_references_and_keeps_legacy_contents(tmp_path, monkeypatch, representation):
    import sequence, sqlite3
    from search import TaskStore
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    destination = tmp_path / 'task'
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate) as scoring:
        run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        before = read_task(destination, include_search_records=True)
        with sqlite3.connect(destination / 'task.sqlite3') as database:
            key, payload = database.execute('SELECT key,value FROM state_archive').fetchone()
            physical = json.loads(payload)
            canonical = physical['batches'][0]['rule_diagnostics']
            if representation.startswith('legacy'):
                physical.pop('rule_diagnostics_ref')
                physical['rule_diagnostics'] = copy.deepcopy(canonical)
                if representation == 'legacy_distinct':
                    physical['rule_diagnostics']['legacy_annotation'] = 'same identity, distinct content'
            elif representation == 'bad_parent': physical['rule_diagnostics_ref']['parent_identity'] = 'foreign-parent'
            elif representation == 'future_version': physical['rule_diagnostics_ref']['version'] = 2
            else: physical['batches'][0].pop('rule_diagnostics')
            database.execute('UPDATE state_archive SET value=? WHERE key=?', (json.dumps(physical), key))
        if representation.startswith('legacy'):
            resume_task(destination)
            with sqlite3.connect(destination / 'task.sqlite3') as database:
                restored, = TaskStore.load_state(database)['archive']
            if representation == 'legacy_equal':
                assert restored['rule_diagnostics'] == canonical
                assert restored['rule_diagnostics'] is restored['batches'][0]['rule_diagnostics']
            else:
                assert restored['rule_diagnostics'] == physical['rule_diagnostics']
                assert restored['rule_diagnostics'] != restored['batches'][0]['rule_diagnostics']
            assert read_task(destination, include_search_records=True)['search']['rule_diagnostics'] == before['search']['rule_diagnostics']
        else:
            with pytest.raises(ValueError, match='诊断引用'): resume_task(destination)
            with sqlite3.connect(destination / 'task.sqlite3') as database:
                assert json.loads(database.execute('SELECT value FROM state_archive WHERE key=?', (key,)).fetchone()[0]) == physical
    assert scoring.call_count == 1


def test_checkpoint_keeps_replayed_pending_diagnostic_by_the_same_local_reference(tmp_path, monkeypatch):
    import sequence, sqlite3
    from search import TaskStore
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    destination = tmp_path / 'task'
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate) as scoring:
        run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        store = TaskStore(destination)
        try:
            parent, = store.state['archive']
            # Exercise the existing replayed-pending storage shape using a scored receipt.
            store.state['pending'] = [dict(program=parent['program'], score_batches=parent['batches'],
                rule_diagnostics=parent['rule_diagnostics'], diagnostics_replayed=True)]
            store.save()
        finally:
            store.close()
        with sqlite3.connect(destination / 'task.sqlite3') as database:
            physical, = json.loads(database.execute("SELECT value FROM state_fields WHERE key='pending'").fetchone()[0])
            restored, = TaskStore.load_state(database)['pending']
    assert scoring.call_count == 1
    assert 'rule_diagnostics' not in physical
    assert physical['rule_diagnostics_ref']['source'] == 'score_batches'
    assert restored['rule_diagnostics'] is restored['score_batches'][0]['rule_diagnostics']
    assert restored['diagnostics_replayed'] is True


@pytest.mark.parametrize('numeric', [False, True])
def test_public_effect_state_lookup_keeps_duplicates_unknown_without_per_input_rescans(tmp_path, monkeypatch, numeric):
    import sequence
    pack = _condition_pack()
    pack['object_sets']['sample']['switch'] = dict(kind='effect', native_identity='fixture_switch')
    state = pack['configurations'][0]['states'].pop('only')
    pack['configurations'][0]['states'] = {
        'present': dict(state, effect='switch', expected=True),
        'absent': dict(copy.deepcopy(state), effect='switch', expected=False)}
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    class ObservedEffects(list):
        scans = 0
        def __iter__(self):
            self.scans += 1
            return super().__iter__()

    observed = {}
    def native_observations(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        inputs = payload['inputs']
        # 相同键两条即歧义；None、数字0和缺记录都不能变成已证False。
        values = ((3, 0),) if numeric else ((0, True), (0, True), (1, False), (2, None), (3, None), (5, True))
        rows = ObservedEffects([dict(inputs[index], object='switch', active=active) for index, active in values])
        payload['effect_observations'] = rows
        for row in payload['state_observations']: row['value'] = 1
        observed.update(effects=rows, inputs=len(inputs))
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=native_observations):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    rules = saved['search']['rule_diagnostics']['rules']
    present, absent = rules[0], rules[2]
    assert [row['input_index'] for row in present['findings'] if row['kind'] == 'missed_opportunity'] == ([] if numeric else [5])
    assert [row['input_index'] for row in absent['findings'] if row['kind'] == 'missed_opportunity'] == ([] if numeric else [1])
    assert present['state_unknown_inputs'] == absent['state_unknown_inputs'] == [
        index for index in range(observed['inputs']) if numeric or index not in (1, 5)]
    assert observed['effects'].scans < observed['inputs'], '同次效果集合不得为每个输入整表重扫'


@pytest.mark.parametrize('qualification', ['cooldown_blocked', 'resource_blocked', 'requirement_blocked',
                                         'supported', 'missing_fact', 'native_forbidden'])
def test_public_supported_hypothesis_keeps_known_negative_requirements_false(tmp_path, monkeypatch, qualification):
    import sequence
    pack = _condition_pack()
    high = pack['configurations'][0]['states']['only']['priority'][0]
    high['name'] = 'higher opportunity'
    low = copy.deepcopy(high)
    low.update(name='ordinary lower')
    low['arguments'].update(action='first', priority_refs=['higher opportunity'])
    pack['configurations'][0]['states']['only']['priority'] = [high, low]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def partial_qualification(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for row in payload['action_observations']:
            row.update(native_qualified=None, has_cooldown=True, cooldown_remaining=0,
                charges_current=0, resource_costs={}, resource_balances={}, known_native_requirements=[])
            if qualification == 'cooldown_blocked': row['cooldown_remaining'] = 1000
            if qualification == 'resource_blocked':
                row.update(resource_costs={'mana': 2}, resource_balances={'mana': 1})
            if qualification == 'requirement_blocked': row['known_native_requirements'] = [{'value': False}]
            if qualification == 'missing_fact': row.update(cooldown_remaining=None, charges_current=None)
            if qualification == 'native_forbidden': row['native_qualified'] = False
        payload['action_observations'] += [dict(row, object='first', actual_form='outbreak',
            base_button='outbreak', native_qualified=True, cooldown_remaining=0,
            resource_costs={}, resource_balances={}, known_native_requirements=[])
            for row in payload['action_observations']]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=partial_qualification) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    diagnostic = result['search']['rule_diagnostics']
    assert diagnostic == saved['search']['rule_diagnostics']
    higher, lower = diagnostic['rules']
    higher_kinds = {row['kind'] for row in higher['findings']}
    lower_kinds = {row['kind'] for row in lower['findings']}
    contributors = {row['rule'] for operation in diagnostic['pool']['operations'] for row in operation['contributors']}
    assert scoring.call_count == 1
    if qualification == 'supported':
        assert 'missed_opportunity' in higher_kinds and 'yielded' in lower_kinds
        assert contributors == {'higher opportunity'}
    elif qualification == 'missing_fact':
        assert 'unknown' in higher_kinds and 'unknown' in lower_kinds
        assert not contributors
    else:
        assert 'missed_opportunity' not in higher_kinds
        assert 'missed_opportunity' in lower_kinds
        assert contributors == {'ordinary lower'}


def test_public_unmapped_edit_keeps_later_diagnostics_operations_and_priority_evidence(tmp_path, monkeypatch):
    import sequence
    pack = _condition_pack()
    higher, lower = pack['configurations'][0]['states']['only']['priority']
    lower['arguments'].update(action='first', value=1, priority_refs=[higher['name']])
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def unmapped_first_input(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['inputs'][0].update(input_source='precombat')
        for row in payload['state_observations']:
            row['value'] = 1 if row['input_index'] in (0, 2) else 0
        payload['action_observations'] += [dict(row, object='first', actual_form='outbreak',
            base_button='outbreak') for row in payload['action_observations']]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=unmapped_first_input) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    diagnostic = saved['search']['rule_diagnostics']
    assert diagnostic == result['search']['rule_diagnostics']
    higher, lower = diagnostic['rules']
    assert [finding['input_index'] for finding in higher['findings']
            if finding['kind'] == 'missed_opportunity'] == [0, 2]
    assert [finding['input_index'] for finding in lower['findings'] if finding['kind'] == 'yielded'] == [0, 2]
    assert higher['status'] == lower['status'] == 'diagnosed'
    assert {row['operation'] for row in higher['unsupported_edits']} == {'move', 'insert'}
    assert all(row['evidence']['input_index'] == 0 and '来源位置' in row['reason']
               for row in higher['unsupported_edits'])
    assert diagnostic['pool']['complete'] is True
    assert {(row['operation'], tuple(row['destination_path'])) for row in diagnostic['pool']['operations']} == {
        ('move', (0,)), ('insert', (0,))}
    assert {contributor['evidence']['input_index'] for row in diagnostic['pool']['operations']
            for contributor in row['contributors']} == {2}
    assert scoring.call_count == 1


@pytest.mark.parametrize('diagnostic_logging', [False, True])
def test_public_search_selects_real_linucb_operation_and_learns_common_batches(tmp_path, monkeypatch, diagnostic_logging):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
                               batch_targets=(2,), iterations=2, validation_batches=1,
                               final_batches=1, final_iterations=2, scenarios=('nominal',),
                               diagnostic_logging=diagnostic_logging))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    steps = [step for step in saved['search'].get('rule_steps', {}).values() if step.get('selection')]
    assert steps, '普通搜索须从完整规则池经真实LinUCB自动选择，不能仍走随机变异'
    step = steps[0]
    selection = step['selection']
    assert len(selection['context']) == 50 and len(selection['action_features']) == 21
    assert 0 < selection['probability'] <= 1
    assert selection['feedback']['status'] == 'learned'
    parent = next(row for row in saved['search']['records'] if row['key'] == step['parent_candidate_key'])
    child = next(row for row in saved['search']['records'] if row['key'] == step['candidate_key'])
    assert step['request']['parent_identity'] == parent['rule_diagnostics']['parent_identity']
    assert any(row['operation_id'] == step['request']['operation_id']
               for row in parent['rule_diagnostics']['pool']['operations'])
    assert selection['feedback']['reward'] == pytest.approx((child['score'] - parent['score']) / parent['score'])
    assert selection['feedback']['common_batches'] == 1
    assert child['rule_step']['request'] == step['request']


def test_public_two_tasks_share_latest_learner_and_old_resume_does_not_roll_it_back(tmp_path, monkeypatch):
    import sequence
    from result_store import read_search_learner
    from selector import MODEL_KEY
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    saved = []
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate):
        for name in ('first', 'second'):
            run_task(source, tmp_path / name, simulation_config=dict(scene='single_target'),
                search_config=dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
                    batch_targets=(2,), iterations=2, validation_batches=1,
                    final_batches=1, final_iterations=2, scenarios=('nominal',)))
            saved.append(read_task(tmp_path / name, include_search_records=True))
    first = next(step['selection'] for step in saved[0]['search']['rule_steps'].values() if step.get('selection'))
    second = next(step['selection'] for step in saved[1]['search']['rule_steps'].values() if step.get('selection'))
    assert first['model_key'] == second['model_key'] == MODEL_KEY
    assert second['model_version'] > first['feedback']['model_version']
    model = read_search_learner(MODEL_KEY)
    assert model['settled'][first['task_run_id']] >= first['decision_id']
    assert model['settled'][second['task_run_id']] >= second['decision_id']
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=AssertionError('完成恢复不得重评分')):
        resume_task(tmp_path / 'first')
    assert read_search_learner(MODEL_KEY) == model


def test_public_auto_selection_cancelled_before_score_resumes_the_saved_decision(tmp_path, monkeypatch):
    import sequence
    from runtime import TaskCancelled
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    normal_requests = []

    def cancel_once(*args, **kwargs):
        if kwargs.get('rule_observation_request') is not None:
            normal_requests.append(tuple(tuple(command['simc_action'] for command in block)
                                         for block in args[1]['blocks']))
            if len(normal_requests) == 5:
                raise TaskCancelled('constructed external boundary before selected score')
        return _observed_evaluate(*args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=cancel_once):
        stopped = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
                batch_targets=(2,), iterations=2, validation_batches=1,
                final_batches=1, final_iterations=2, scenarios=('nominal',)))
        before = read_task(tmp_path / 'task', include_search_records=True)
        queued = next(step for step in before['search']['rule_steps'].values() if step['status'] == 'queued')
        assert stopped['status'] == 'cancelled' and 'feedback' not in queued['selection']
        resume_task(tmp_path / 'task')
        after = read_task(tmp_path / 'task', include_search_records=True)
    step = after['search']['rule_steps'][queued['request']['operation_id']]
    assert step['selection']['decision_id'] == queued['selection']['decision_id']
    assert step['selection']['model_version'] == queued['selection']['model_version']
    assert step['selection']['feedback']['status'] == 'learned'
    assert step['status'] == 'scored' and after['search']['candidate_count'] == 5
    assert after['status'] == 'completed' and after['search']['stop_reason'] == 'candidate_limit'
    assert normal_requests[-1] == normal_requests[-2]


def test_public_resume_encodes_replayed_complete_parent_without_another_parent_score(tmp_path, monkeypatch):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    cancelled = False

    def stop_during_first_diagnosis(*args, **kwargs):
        nonlocal cancelled
        result = _observed_evaluate(*args, **kwargs)
        if not cancelled and kwargs.get('rule_observation_request') is not None:
            cancelled = True
            kwargs['runtime'].cancel()
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=stop_during_first_diagnosis):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
                batch_targets=(2,), iterations=2, validation_batches=1,
                final_batches=1, final_iterations=2, scenarios=('nominal',)))
        before = read_task(tmp_path / 'task', include_search_records=True)
        assert before['search']['records'][0]['rule_diagnostics']['pool']['complete'] is False
        resume_task(tmp_path / 'task')
        after = read_task(tmp_path / 'task', include_search_records=True)
    parent = next(row for row in after['search']['records'] if row['key'] == before['search']['records'][0]['key'])
    assert parent['rule_diagnostics']['pool']['complete'] is True
    assert parent['batches'][0]['data_key'] == before['search']['records'][0]['batches'][0]['data_key']
    assert len(parent['rule_diagnostics']['selection_context']['values']) == 50
    assert any(step.get('selection', {}).get('feedback', {}).get('status') == 'learned'
               for step in after['search']['rule_steps'].values())


def test_public_new_task_replays_incomplete_shared_cache_without_repeating_its_score(tmp_path, monkeypatch):
    import result_store
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    normal_scores = []
    cancelled = False
    def observed(*args, **kwargs):
        nonlocal cancelled
        result = _observed_evaluate(*args, **kwargs)
        if kwargs.get('rule_observation_request') is not None:
            normal_scores.append(sequence.behavior_key(args[1]))
            if not cancelled:
                cancelled = True
                kwargs['runtime'].cancel()
        return result
    config = dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
        batch_targets=(2,), iterations=2, validation_batches=1,
        final_batches=1, final_iterations=2, scenarios=('nominal',))
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=observed):
        run_task(source, tmp_path / 'first', simulation_config=dict(scene='single_target'), search_config=config)
        before = read_task(tmp_path / 'first', include_search_records=True)
        original, = before['search']['records']
        batch_key = original['batches'][0]['data_key']
        report_before = result_store.one('batches', 'batch_key', batch_key)['report']
        assert original['rule_diagnostics']['pool']['complete'] is False
        run_task(source, tmp_path / 'second', simulation_config=dict(scene='single_target'), search_config=config)
        after = read_task(tmp_path / 'second', include_search_records=True)
    parent = next(row for row in after['search']['records'] if row['key'] == original['key'])
    assert after['status'] == 'completed'
    assert normal_scores.count(original['key']) == 1
    assert parent['batches'][0]['data_key'] == batch_key
    assert parent['rule_diagnostics']['pool']['complete'] is True
    assert len(parent['rule_diagnostics']['selection_context']['values']) == 50
    assert parent['key'] in after['search']['rule_diagnostic_replays']
    assert result_store.one('batches', 'batch_key', batch_key)['report'] == report_before
    assert read_task(tmp_path / 'first', include_search_records=True)['search']['records'][0][
        'rule_diagnostics']['pool']['complete'] is False


@pytest.mark.parametrize('cleanup_expired', [False, True])
def test_public_budget_end_learns_completed_pending_common_batches_without_more_scores(tmp_path, monkeypatch, installed_data_store_api, cleanup_expired):
    import search
    import result_store
    from selector import MODEL_KEY
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    requests = []

    def finish_at_budget(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        if kwargs.get('rule_observation_request') is not None:
            requests.append(args[1]['blocks'])
            if len(requests) == 6:
                kwargs['runtime'].used_seconds = kwargs['runtime'].budget_seconds
        return result

    real_runtime = search.TaskRuntime
    cleanup_calls = []
    if cleanup_expired:
        def expired_cleanup(total, **kwargs):
            cleanup_calls.append(total)
            return real_runtime(total, used_seconds=total, **kwargs)
        monkeypatch.setattr(search, 'TaskRuntime', expired_cleanup)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=finish_at_budget):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(total_budget_seconds=60, input_interval_ms=200, candidate_limit=6,
                round_candidate_limit=2, max_processes=1, batch_targets=(2,), iterations=2,
                validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',)))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    selections = [step['selection'] for step in saved['search']['rule_steps'].values() if step.get('selection')]
    assert len(selections) == 2 and len(requests) == 6
    if cleanup_expired:
        checkpoint = search.TaskStore(tmp_path / 'task')
        try:
            assert cleanup_calls == [30]
            assert checkpoint.state['selection_feedback_incomplete'] is True
            assert len(checkpoint.state['selection_feedback_intents']) == 2
            assert all(intent['common_batches'] == 1 for intent in checkpoint.state['selection_feedback_intents'].values())
        finally:
            checkpoint.close()
        assert len(result_store.read_search_learner(MODEL_KEY)['reservations']) == 2
        assert saved['search']['selection_feedback_incomplete'] is True
        monkeypatch.setattr(search, 'TaskRuntime', real_runtime)
    else:
        assert all(row.get('feedback', {}).get('status') == 'learned' for row in selections)
        assert all(row['feedback']['common_batches'] == 1 for row in selections)
    published_before = result_store.one('runs', 'run_id', saved['run_id'])
    real_write = installed_data_store_api['write']
    publish_failed = False
    def fail_result_once(root, table, key, rows, **kwargs):
        nonlocal publish_failed
        if cleanup_expired and table == 'runs' and not publish_failed:
            publish_failed = True
            raise PermissionError('constructed completed-result publication failure')
        return real_write(root, table, key, rows, **kwargs)
    monkeypatch.setitem(installed_data_store_api, 'write', fail_result_once)
    real_save = search.TaskStore.save
    def save_complete_flag_with_intents(store):
        result = real_save(store)
        persisted = search.TaskStore.load_state(store.db)
        if not persisted.get('selection_feedback_intents'):
            assert not persisted.get('selection_feedback_incomplete'), '空intent与complete标记必须同次保存'
        return result
    monkeypatch.setattr(search.TaskStore, 'save', save_complete_flag_with_intents)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=AssertionError('预算耗尽不能补评分')):
        if cleanup_expired:
            with pytest.raises(PermissionError, match='completed-result'):
                resume_task(tmp_path / 'task')
            committed = result_store.read_search_learner(MODEL_KEY)
        resume_task(tmp_path / 'task')
    again = read_task(tmp_path / 'task', include_search_records=True)
    if not cleanup_expired:
        assert again['search']['rule_steps'] == saved['search']['rule_steps']
    assert all(step['selection']['feedback']['status'] == 'learned'
               for step in again['search']['rule_steps'].values())
    assert result_store.read_search_learner(MODEL_KEY)['reservations'] == []
    if cleanup_expired:
        assert result_store.read_search_learner(MODEL_KEY) == committed
        assert again['search']['selection_feedback_incomplete'] is False
        published_after = result_store.one('runs', 'run_id', saved['run_id'])
        for name in published_before.keys() - {'search_metrics', 'elapsed_seconds'}:
            assert published_after[name] == published_before[name]


@pytest.mark.parametrize('stage,supplied_runtime', [('prediction', False), ('learning', False), ('learning', True)])
def test_public_selector_recovers_process_exit_after_shared_publish(tmp_path, monkeypatch, installed_data_store_api, stage, supplied_runtime):
    import time
    import result_store
    import sequence
    from runtime import TaskRuntime
    from search import TaskStore
    from selector import MODEL_KEY
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    real_write = installed_data_store_api['write']
    interrupted = False
    normal_requests = []

    def published_then_exit(root, table, key, rows, **kwargs):
        nonlocal interrupted
        result = real_write(root, table, key, rows, **kwargs)
        if table == 'search_learners' and not interrupted and rows[0]['version'] == (1 if stage == 'prediction' else 2):
            interrupted = True
            raise SystemExit('constructed process exit after real shared atomic replacement')
        return result

    def observed(*args, **kwargs):
        if kwargs.get('rule_observation_request') is not None:
            normal_requests.append(args[1]['blocks'])
        return _observed_evaluate(*args, **kwargs)

    monkeypatch.setitem(installed_data_store_api, 'write', published_then_exit)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=observed):
        with pytest.raises(SystemExit, match='after real shared'):
            run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
                    batch_targets=(2,), iterations=2, validation_batches=1,
                    final_batches=1, final_iterations=2, scenarios=('nominal',)))
        before = result_store.read_search_learner(MODEL_KEY)
        requests_before = len(normal_requests)
        checkpoint = TaskStore(tmp_path / 'task')
        try:
            used_before = checkpoint.state['elapsed_seconds']
        finally:
            checkpoint.close()
        external = TaskRuntime(600) if supplied_runtime else None
        external_started = external.started if external else None
        resume_task(tmp_path / 'task', **({'_runtime': external} if external else {}))
        if external:
            assert abs(external.elapsed_seconds - (used_before + time.monotonic()-external_started)) < .02
        saved = read_task(tmp_path / 'task', include_search_records=True)
    step = next(step for step in saved['search']['rule_steps'].values() if step.get('selection'))
    assert step['selection']['feedback']['status'] == 'learned'
    assert result_store.read_search_learner(MODEL_KEY)['version'] == 2
    if stage == 'prediction':
        receipt = before['reservations'][0]
        assert step['selection']['operation_id'] == receipt['operation_id']
        assert step['selection']['probability'] == receipt['probability']
        assert len(normal_requests) == requests_before + 1
    else:
        assert result_store.read_search_learner(MODEL_KEY) == before
        assert len(normal_requests) == requests_before


@pytest.mark.parametrize('cancel_recovery', [False, True])
def test_public_budget_recovery_freezes_remaining_pending_after_partial_freeze_exit(tmp_path, monkeypatch, cancel_recovery):
    import threading
    import search
    import result_store
    import sequence
    from selector import MODEL_KEY
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    requests = []
    def completed_at_budget(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        if kwargs.get('rule_observation_request') is not None:
            requests.append(args[1]['blocks'])
            if len(requests) == 6:
                kwargs['runtime'].used_seconds = kwargs['runtime'].budget_seconds
        return result
    real_freeze = search.freeze_selection_feedback
    exited = False
    def exit_after_first_intent(store, work, rows, **kwargs):
        nonlocal exited
        real_freeze(store, work, rows, **kwargs)
        if not exited and store.state.get('selection_feedback_intents'):
            exited = True
            raise SystemExit('constructed exit halfway through terminal feedback freezing')
    monkeypatch.setattr(search, 'freeze_selection_feedback', exit_after_first_intent)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=completed_at_budget):
        with pytest.raises(SystemExit, match='halfway'):
            run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=dict(total_budget_seconds=60, input_interval_ms=200, candidate_limit=6,
                    round_candidate_limit=2, max_processes=1, batch_targets=(2,), iterations=2,
                    validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',)))
    checkpoint = search.TaskStore(tmp_path / 'task')
    try:
        assert len(checkpoint.state['selection_feedback_intents']) == 1
        assert len(checkpoint.state['pending']) == 2
    finally:
        checkpoint.close()
    monkeypatch.setattr(search, 'freeze_selection_feedback', real_freeze)
    cancellation = threading.Event()
    if cancel_recovery: cancellation.set()
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=AssertionError('预算恢复不能增加评分')):
        resume_task(tmp_path / 'task', cancel_event=cancellation)
        if cancel_recovery:
            assert len(result_store.read_search_learner(MODEL_KEY)['reservations']) == 2
            checkpoint = search.TaskStore(tmp_path / 'task')
            try:
                assert len(checkpoint.state['selection_feedback_intents']) == 2
                assert checkpoint.state['selection_feedback_incomplete'] is True
            finally:
                checkpoint.close()
            cancellation.clear()
            resume_task(tmp_path / 'task', cancel_event=cancellation)
    assert len(requests) == 6
    assert result_store.read_search_learner(MODEL_KEY)['reservations'] == []
    saved = read_task(tmp_path / 'task', include_search_records=True)
    assert len(saved['search']['rule_steps']) == 2
    assert all(step['selection']['feedback']['status'] == 'learned'
               for step in saved['search']['rule_steps'].values())


@pytest.mark.parametrize('saved_running', [False, True])
def test_public_feedback_recovery_time_exhausts_budget_before_any_new_score(tmp_path, monkeypatch, installed_data_store_api, saved_running):
    import time
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    real_write, real_read = installed_data_store_api['write'], installed_data_store_api['read_key']
    active_runtime = None
    interrupted = False
    delayed = False

    def publish_then_exit(root, table, key, rows, **kwargs):
        nonlocal interrupted
        result = real_write(root, table, key, rows, **kwargs)
        if table == 'search_learners' and rows[0]['settled'] and not interrupted:
            interrupted = True
            active_runtime.used_seconds = active_runtime.budget_seconds - (
                time.monotonic()-active_runtime.started) - 1.0
            raise SystemExit('constructed exit with one second of task budget left')
        return result

    def delayed_read(root, table, key, **kwargs):
        nonlocal delayed
        if table == 'search_learners' and interrupted and not delayed:
            delayed = True
            time.sleep(1.2)  # Real external-store latency, charged by the existing task clock.
        return real_read(root, table, key, **kwargs)

    def observed(*args, **kwargs):
        nonlocal active_runtime
        active_runtime = kwargs['runtime']
        return _observed_evaluate(*args, **kwargs)

    monkeypatch.setitem(installed_data_store_api, 'write', publish_then_exit)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=observed):
        with pytest.raises(SystemExit, match='one second'):
            run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=dict(total_budget_seconds=30, input_interval_ms=200, candidate_limit=6,
                    round_candidate_limit=2, max_processes=1, batch_targets=(2,), iterations=2, validation_batches=1,
                    final_batches=1, final_iterations=2, scenarios=('nominal',)))
    from search import TaskStore
    checkpoint = TaskStore(tmp_path / 'task')
    try:
        used_before_recovery = checkpoint.state['elapsed_seconds']
        if saved_running:
            checkpoint.state.update(status='running', inflight={})
            checkpoint.save()  # A process can exit before its running marker is cleared.
    finally:
        checkpoint.close()
    monkeypatch.setitem(installed_data_store_api, 'read_key', delayed_read)
    import search
    original_clock = search.TaskRuntime
    recovery_clocks = []
    def recovery_clock(*args, **kwargs):
        clock = original_clock(*args, **kwargs)
        recovery_clocks.append(clock)
        return clock
    monkeypatch.setattr(search, 'TaskRuntime', recovery_clock)
    original_save = search.TaskStore.save
    acknowledged = []
    def save_acknowledged_elapsed(store):
        result = original_save(store)
        persisted = search.TaskStore.load_state(store.db)
        if not acknowledged and any(step.get('selection', {}).get('feedback')
                                    for step in persisted.get('rule_steps', {}).values()):
            acknowledged.append(True)
            assert persisted['elapsed_seconds'] >= used_before_recovery + 1.2
        return result
    monkeypatch.setattr(search.TaskStore, 'save', save_acknowledged_elapsed)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=AssertionError('补发耗尽预算后不得评分')):
        resume_task(tmp_path / 'task')
    saved = read_task(tmp_path / 'task', include_search_records=True)
    assert delayed and saved['elapsed_seconds'] >= 30
    assert saved['elapsed_seconds'] >= used_before_recovery + 1.2
    assert saved['status'] == 'validation_incomplete'
    assert len(recovery_clocks) == 1 and recovery_clocks[0].budget_seconds == 30
    assert acknowledged
    assert len(saved['search']['rule_steps']) == 2
    assert all(step.get('selection', {}).get('feedback', {}).get('status') == 'learned'
               for step in saved['search']['rule_steps'].values())


@pytest.mark.parametrize('operation_kind', ['move', 'insert'])
def test_public_resume_scores_one_requested_operation_and_keeps_pending_starts(tmp_path, monkeypatch, operation_kind):
    import sequence
    from runtime import TaskCancelled
    calls = []
    selected_score_calls = []

    def interrupted_engine(*args, **kwargs):
        calls.append(tuple(command['simc_action'] for block in args[1]['blocks'] for command in block))
        if len(calls) == 2:
            raise TaskCancelled('constructed external process cancellation after first parent')
        if kwargs.get('rule_observation_request') is not None:
            selected_score_calls.append(calls[-1])
        return _observed_evaluate(*args, **kwargs)

    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=interrupted_engine):
        stopped = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=3, batch_targets=(2,),
                               iterations=2, validation_batches=1, diagnostic_logging=True,
                               search_observability='summary'))
        assert stopped['status'] == 'cancelled'
        diagnosis = read_task(tmp_path / 'task')['search']['rule_diagnostics']
        operation = next(row for row in diagnosis['pool']['operations'] if row['operation'] == operation_kind)
        request = dict(parent_identity=diagnosis['parent_identity'], operation_id=operation['operation_id'])
        with pytest.raises(TaskError, match='父身份'):
            resume_task(tmp_path / 'task', rule_step=dict(request, parent_identity='foreign-parent'))
        resumed = resume_task(tmp_path / 'task', rule_step=request)
        saved = read_task(tmp_path / 'task', include_search_records=True)
        again = resume_task(tmp_path / 'task', rule_step=request)
    changed = next(row for row in resumed['search']['records'] if row.get('rule_step'))
    expected = [['death_coil'], ['outbreak']] + ([['death_coil']] if operation_kind == 'insert' else [])
    assert changed['program'] == expected
    assert changed['rule_step']['request'] == request
    assert changed['rule_step']['parent_score'] > 0
    assert changed['score'] > 0
    if operation_kind == 'insert':
        assert changed['score'] > changed['rule_step']['parent_score']
    assert any(row.get('rule_step') == changed['rule_step'] for row in saved['search']['records'])
    assert selected_score_calls.count(tuple(block[0] for block in expected)) == 1
    assert saved['search']['candidate_count'] == 3
    assert saved['search']['partial_round'] is True
    assert again['search']['candidate_count'] == 3
    observation = saved['search']['observability']['summary']
    assert observation['rule_steps'] == 1
    assert observation['generated_events'] == 4
    assert observation['pending_events'] == 0
    assert again['search']['observability']['summary']['rule_steps'] == 1


def test_public_diagnostics_keep_inactive_state_rules_without_editing_them(tmp_path, monkeypatch):
    import sequence
    pack = _condition_pack()
    pack['object_sets']['sample']['switch'] = dict(kind='effect', native_identity='fixture_switch')
    active = pack['configurations'][0]['states'].pop('only')
    active.update(effect='switch', expected=False)
    inactive = copy.deepcopy(active)
    inactive['expected'] = True
    pack['configurations'][0]['states'] = {'inactive': inactive, 'active': active}
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def switched_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['effect_observations'] = [dict(row, object='switch', active=False) for row in payload['inputs']]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=switched_engine):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert len(diagnosis['rules']) == 4
    assert [(row['state'], row['status']) for row in diagnosis['rules']] == [
        ('inactive', 'not_applicable'), ('inactive', 'not_applicable'),
        ('active', 'diagnosed'), ('active', 'not_applicable')]
    assert all(c['state'] == 'active' for op in diagnosis['pool']['operations'] for c in op['contributors'])


def test_public_cancel_keeps_completed_score_and_marks_rule_pool_incomplete(tmp_path, monkeypatch):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def completed_then_cancelled(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        kwargs['runtime'].cancel()
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=completed_then_cancelled) as scoring:
        stopped = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
        resumed = resume_task(tmp_path / 'task')
    assert scoring.call_count == 1
    assert stopped['status'] == 'cancelled'
    assert stopped['search']['records'][0]['score'] > 0
    diagnosis = saved['search']['rule_diagnostics']
    assert len(diagnosis['rules']) == 2
    assert diagnosis['pool']['complete'] is False
    assert diagnosis['pool']['incomplete_reason'] == 'cancelled'
    assert resumed['search']['rule_diagnostics']['pool']['complete'] is True
    assert len(resumed['search']['rule_diagnostics']['pool']['operations']) == 2


def test_public_cached_batch_keeps_original_evidence_and_rebinds_current_parent(tmp_path, monkeypatch):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    config = dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate) as scoring:
        first = run_task(source, tmp_path / 'task-a', search_config=config,
                         simulation_config=dict(scene='single_target'))
        second = run_task(source, tmp_path / 'task-b', search_config=config,
                          simulation_config=dict(scene='single_target'))
        saved = read_task(tmp_path / 'task-b', include_search_records=True)
    assert scoring.call_count == 1
    before, after = (task['search']['rule_diagnostics'] for task in (first, second))
    assert before['evidence']['batch_key'] == after['evidence']['batch_key']
    assert before['evidence']['task_run_id'] != after['evidence']['task_run_id']
    assert after['evidence']['source_task_run_id'] == before['evidence']['task_run_id']
    assert before['parent_identity'] != after['parent_identity']
    assert {op['operation_id'] for op in before['pool']['operations']}.isdisjoint(
        op['operation_id'] for op in after['pool']['operations'])
    assert saved['search']['records'][0]['rule_diagnostics'] == after


def test_public_unknown_execution_is_not_reported_as_inactive_or_failed(tmp_path, monkeypatch):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def missing_outcomes(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        for row in result['report']['sim']['players'][0]['sim2gse_rule_observations']['action_observations']:
            row.update(native_qualified=None, success=None, has_cooldown=False,
                       resource_costs={'rune': 0}, resource_balances={'rune': 6}, known_native_requirements=[])
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=missing_outcomes):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert diagnosis['rules'][0]['status'] == 'unknown'
    assert {row['case'] for row in diagnosis['rules'][0]['unknown_conditions']} == {'covered', 'missed_opportunity'}
    assert diagnosis['rules'][0]['findings'] == []
    assert diagnosis['pool']['operations'] == []


def test_public_not_dispatched_fact_supports_hypothesis_without_claiming_native_ready(tmp_path, monkeypatch):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def explicit_outcome(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['execution_events_complete'] = False
        for row in payload['action_observations']:
            row.update(native_qualified=None, success=None, has_cooldown=False,
                resource_costs={'rune': 0}, resource_balances={'rune': 6}, known_native_requirements=[],
                timing_precision='current_state_estimate')
        payload['action_events'] = [dict(object='consumer', sample_id=1, input_index=0, event_index=9999,
            time=0, source_step=0, input_source='loop', kind='outcome', outcome='not_attempted',
            attempt=False, success=False, failure_reason=None)]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=explicit_outcome):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    finding, = diagnosis['rules'][0]['findings']
    assert finding['kind'] == 'missed_opportunity'
    assert finding['certainty'] == 'hypothesis'
    assert finding['target_position'] == [0]
    assert len(diagnosis['pool']['operations']) == 2
    assert diagnosis['facts']['qualification_events_promoted_to_input_state'] is False


@pytest.mark.parametrize('iterations,sample_id,supported', [(2, 0, False), (1, 0, False), (1, 1, True), (2, 1, True)])
def test_public_diagnostics_use_actual_scored_sample_not_warmup(tmp_path, monkeypatch, iterations, sample_id, supported):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def selected_sample(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['sample_id'] = sample_id
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in payload[name]: row['sample_id'] = sample_id
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=selected_sample) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=iterations, validation_batches=1))
    assert scoring.call_count == 1
    diagnosis = result['search']['rule_diagnostics']
    assert bool(diagnosis['pool']['operations']) is supported
    if not supported:
        assert all(row['status'] == 'unknown' for row in diagnosis['rules'])
        assert '计分样本' in diagnosis['rules'][0]['reason']


def test_public_window_template_uses_configured_effect_without_enabling_full_charge_branch(tmp_path, monkeypatch):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'another-name': json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['Buff窗口与充能使用']}
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_window')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='window use', template='another-name',
        arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
                       window_effect='window', allow_full_charge=False))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def window_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['effect_events_complete'] = {'window': True}
        payload['effect_observations'] = [dict(row, object='window', active=row['input_index'] == 0)
                                          for row in payload['inputs']]
        for row in payload['action_observations']: row.update(charges_current=2, charges_maximum=2)
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=window_engine) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    assert [(finding['kind'], finding.get('input_index')) for finding in diagnosis['rules'][0]['findings']] == [('missed_window', 0)]
    assert len(diagnosis['pool']['operations']) == 2


def test_public_pool_respects_configured_edit_unit_range(tmp_path, monkeypatch):
    import sequence
    pack = _condition_pack()
    pack['object_sets']['sample']['editable']['allow_units'] = ['wait_block']
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    assert diagnosis['rules'][0]['findings'][0]['kind'] == 'missed_opportunity'
    assert diagnosis['pool']['complete'] is True
    assert diagnosis['pool']['operations'] == []
    assert diagnosis['pool']['empty_reason'] == 'no_supported_legal_operation'
    assert diagnosis['pool']['rejections']['edit_unit_not_allowed'] == 2


def test_public_resource_template_uses_configured_native_resource_identity(tmp_path, monkeypatch):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'resource-template-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['资源近满与溢出处理']}
    pack['object_sets']['sample']['tank'] = dict(kind='resource', native_identity='runic_power')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='spend before overflow',
        template='resource-template-renamed', arguments=dict(action='consumer', priority_refs=[],
            edit_range='editable', resource='tank', margin_source='native_cost', near_full_margin=None))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def resource_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['resource_events'] = [dict(row, object='tank', current=95 if row['input_index'] == 0 else 0,
            maximum=100, overflow=0) for row in payload['inputs']]
        for row in payload['action_observations']:
            row.update(resource_costs={'runic_power': 10}, resource_balances={'runic_power': 95})
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=resource_engine) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    assert [(row['kind'], row.get('input_index')) for row in diagnosis['rules'][0]['findings']] == [
        ('near_full_opportunity', 0)]
    assert len(diagnosis['pool']['operations']) == 2


def test_public_reservation_template_enumerates_all_later_positions(tmp_path, monkeypatch):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'reserve-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['资源预留']}
    pack['object_sets']['sample'].update(tank=dict(kind='resource', native_identity='runic_power'),
        reserve=dict(kind='effect', native_identity='fixture_reservation'))
    opener = pack['configurations'][0]['opener']
    opener['source_steps'].append('source 3')
    opener['ordinary_steps'].append(dict(opener['ordinary_steps'][0], source_step=3))
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='reserve expense',
        template='reserve-renamed', arguments=dict(action='consumer', reserved_action='first',
            priority_refs=[], edit_range='editable', resource='tank', reservation_effect='reserve',
            reserve_amount_source='explicit', reserve_amount=30))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def reservation_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in payload[name]: row['source_step'] = row['input_index'] % 3
        payload['resource_events'] = [dict(row, object='tank', before=40, after=20,
            actual_delta=-20) for row in payload['inputs']]
        payload['effect_observations'] = [dict(row, object='reserve', active=row['input_index'] == 1)
            for row in payload['inputs']]
        for row in payload['action_observations']: row['success'] = row['input_index'] == 1
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=reservation_engine) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    assert [(row['kind'], row.get('input_index')) for row in diagnosis['rules'][0]['findings']] == [
        ('reservation_crowding_hypothesis', 1)]
    assert [(row['operation'], row['source_path'], row['destination_path'])
        for row in diagnosis['pool']['operations']] == [('move', [1], [3])]


@pytest.mark.parametrize('scope_case', ['known', 'missing_component_key', 'empty', 'unresolved', 'unknown_applicability'])
def test_public_join_keeps_target_components_and_missing_effect_unknown(tmp_path, monkeypatch, scope_case):
    import sequence
    pack = _condition_pack()
    objects = pack['object_sets']['sample']
    objects.update(scope=dict(kind='target_scope', value='all_currently_engaged_required_targets'),
                   effect=dict(kind='effect', components=[dict(native_identity='dot', target_scope='scope')]))
    template = dict(application_phase='post_simulation_diagnosis_and_next_candidate',
        parameters=dict(action=dict(type='action_ref'), scope=dict(type='target_scope_ref'),
                        effect=dict(type='effect_ref')),
        reads=[dict(**{'as': alias, 'from': source}, object=dict(arg=argument), fields=fields,
                    same_run=True, on_declared_null_object='not_applicable_identity_rows')
            for alias, source, argument, fields in [
                ('actions', 'student.action_observations', 'action', ['target_id']),
                ('targets', 'student.target_scope', 'scope', ['target_id', 'required']),
                ('components', 'student.effect_component_scopes', 'effect', ['target_id', 'component_id', 'applicable']),
                ('effects', 'student.effect_observations', 'effect', ['target_id', 'component_id', 'active'])]],
        diagnose=dict(let=[dict(name='components_by_target', value=dict(op='join',
                args=[dict(**{'as': 'target_scope'}, rows=dict(var='targets')),
                      dict(**{'as': 'component_scope'}, rows=dict(var='components'))],
                keys=['run_id', 'sample_id', 'input_index', 'target_id'], preserve_aliases=True)),
            dict(name='effect_by_target', value=dict(op='join',
                args=[dict(**{'as': None}, rows=dict(var='components_by_target')),
                      dict(**{'as': 'effect'}, rows=dict(var='effects'))],
                keys=['run_id', 'sample_id', 'input_index', 'target_id', 'component_id'],
                preserve_aliases=True, join_type='left')),
            dict(name='joined', value=dict(op='join',
                args=[dict(**{'as': 'action'}, rows=dict(var='actions')),
                      dict(**{'as': None}, rows=dict(var='effect_by_target'))],
                keys=['run_id', 'sample_id', 'input_index'], preserve_aliases=True, collision='error'))],
            for_each=dict(var='joined'), **{'as': 'j'}, cases=[dict(kind='joined', when=True,
                certainty='observed_fact', evidence={name: dict(var='j.'+path) for name, path in dict(
                    input_index='input_index', target='target_id', component='component_id',
                    action_target='action.target_id', active='effect.active',
                    applicable='component_scope.applicable').items()})], export_trigger_records=[]), edits=[])
    pack['general']['templates'] = {'join-renamed': template}
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='target join',
        template='join-renamed', arguments=dict(action='consumer', scope='scope', effect='effect'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def component_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['inputs'] = payload['inputs'][:1]
        row = payload['inputs'][0]
        row['target_scopes'] = dict(scope=[dict(target_id=target, required=True) for target in (1, 2)])
        row['target_scope_sources'] = dict(scope='sim.target_non_sleeping_list')
        if scope_case == 'empty': row['target_scopes']['scope'] = []
        elif scope_case == 'unresolved': row['target_scopes']['scope'] = None
        payload['state_observations'] = payload['state_observations'][:1]
        payload['action_observations'] = [dict(payload['action_observations'][0], target_id=999)]
        payload['effect_observations'] = [dict(row, object='effect', target_id=target,
            component_id='dot', applicable=True, active=True if target == 1 else None) for target in (1, 2)]
        if scope_case == 'missing_component_key': payload['effect_observations'][0].pop('target_id')
        if scope_case == 'unknown_applicability':
            payload['effect_observations'][0]['applicable'] = None
            payload['effect_observations'][1]['applicable'] = False
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=component_engine):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    rule, = result['search']['rule_diagnostics']['rules']
    if scope_case in ('missing_component_key', 'unresolved'):
        assert rule['status'] == 'unknown'
        assert '关联键缺失' in rule['reason']
        assert result['search']['rule_diagnostics']['pool']['operations'] == []
        return
    if scope_case == 'empty':
        assert rule['status'] == 'not_applicable'
        assert rule['findings'] == []
        return
    findings = rule['findings']
    assert [row for row in findings if row['input_index'] == 0] == [
        dict(kind='joined', certainty='observed_fact', input_index=0, target=1,
             component='dot', action_target=999, active=True, applicable=None if scope_case == 'unknown_applicability' else True),
        dict(kind='joined', certainty='observed_fact', input_index=0, target=2,
             component='dot', action_target=999, active=None, applicable=False if scope_case == 'unknown_applicability' else True)]


@pytest.mark.parametrize('missing_input_source', [False, True, 'scoped_unknown', 'threshold_false'])
def test_public_preparation_template_uses_last_supported_input_before_frozen_burst(tmp_path, monkeypatch, missing_input_source):
    import burst, result_store, sequence
    from rule_config import DEFAULT_PATH
    from test_burst import reviewed_fixture, character_seed_boundary
    pack = _condition_pack()
    pack['general']['templates'] = {'prepare-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['爆发前准备']}
    pack['object_sets']['sample']['anchor'] = dict(kind='plan', value='frozen_actual_burst_input_start')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='prepare before anchor',
        template='prepare-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            stock='counter', compare='eq', threshold=1, anchor='anchor'))]
    if missing_input_source in ('scoped_unknown', 'threshold_false'):
        pack['general']['templates']['lower-template'] = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['条件触发与CD使用']
        pack['object_sets']['sample']['low_counter'] = dict(kind='state', native_identity='fixture_low_counter')
        pack['configurations'][0]['states']['only']['priority'].append(dict(name='after final anchor',
            template='lower-template', arguments=dict(action='consumer', priority_refs=['prepare before anchor'],
                edit_range='editable', state='low_counter', compare='eq', value=1,
                activation_effect=None, activation_expected=True)))
        if missing_input_source == 'threshold_false':
            pack['object_sets']['sample']['low_action'] = copy.deepcopy(pack['object_sets']['sample']['consumer'])
            high, low = pack['configurations'][0]['states']['only']['priority']
            high['arguments'].update(compare='gte', threshold=2)
            low['arguments']['action'] = 'low_action'
    _configure_opener(tmp_path, monkeypatch, pack)
    result_store.DATA_ROOT.mkdir()
    definition, profile = reviewed_fixture()
    burst.publish(definition)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(profile, encoding='utf-8')

    def preparation_engine(*args, **kwargs):
        sources = kwargs.pop('input_sources')
        kwargs.pop('burst_candidate')
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row, input_source in zip(payload[name], sources, strict=True): row['input_source'] = input_source
        for row in payload['state_observations']: row['value'] = 1
        for row in payload['action_observations']: row['input_allowed'] = row['input_source'] == 'loop'
        if missing_input_source and missing_input_source != 'threshold_false':
            for row in payload['inputs']: row.pop('input_source')
        if missing_input_source == 'scoped_unknown':
            payload['state_observations'] += [dict(row, object='low_counter', value=int(index == len(payload['inputs'])-1))
                                                for index, row in enumerate(payload['inputs'])]
        if missing_input_source == 'threshold_false':
            assert sources[0] == 'loop'
            low_actions = [dict(row, object='low_action') for row in payload['action_observations']]
            for row in payload['state_observations']: row['value'] = 0
            payload['state_observations'] += [dict(row, object='low_counter', value=int(index == 0))
                                                for index, row in enumerate(payload['inputs'])]
            for row in payload['action_observations']:
                row.update(native_qualified=None, resource_costs=None, has_cooldown=False,
                           known_native_requirements=[])
            payload['action_observations'] += low_actions
        return result

    with character_seed_boundary(native_reference=native), patch.object(sequence, 'evaluate', side_effect=preparation_engine) as scoring:
        result = run_task(source, tmp_path / 'task', use_burst=True, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    findings = diagnosis['rules'][0]['findings']
    if missing_input_source in ('scoped_unknown', 'threshold_false'):
        lower = diagnosis['rules'][1]
        assert [(row['input_index'], row['kind']) for row in lower['findings'] if row['kind'] == 'missed_opportunity'] == [
            (0 if missing_input_source == 'threshold_false' else
             len(result['search']['records'][0]['batches'][0]['request']['times'])-1, 'missed_opportunity')]
        return
    if missing_input_source:
        assert {row['kind'] for row in findings} == {'unknown'}
        assert diagnosis['pool']['operations'] == []
        return
    assert [(row['kind'], row.get('anchor')) for row in findings] == [
        ('missed_preparation', 3000), ('missed_preparation', 48000),
        ('missed_preparation', 93000), ('missed_preparation', 138000)]
    assert diagnosis['pool']['operations']
    assert all(row['certainty'] == 'hypothesis' for row in findings)


@pytest.mark.parametrize('additional_unknown_filler', [False, True])
def test_public_idle_template_reduces_one_proven_wait_or_inserts_one_filler(tmp_path, monkeypatch, additional_unknown_filler):
    import sequence
    from rule_config import DEFAULT_PATH
    from rule_diagnostics import apply
    pack = _condition_pack()
    pack['general']['templates'] = {'idle-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['可避免空闲']}
    pack['object_sets']['sample'].update(occupancy=dict(kind='state', native_identity='controlled_input.occupancy'),
        reservations=dict(kind='policy', value='effective_execution_constraints'))
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='idle input',
        template='idle-renamed', arguments=dict(priority_refs=[], edit_range='editable', allowed_actions=['consumer'],
            occupancy='occupancy', reservations='reservations', wait_delta=1))]
    if additional_unknown_filler:
        pack['configurations'][0]['states']['only']['priority'][0]['arguments']['allowed_actions'].append('first')
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 800
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def idle_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in payload[name]:
                row['source_step'] = row['input_index'] % 8
        for row in payload['inputs']:
            row['occupancy'] = dict(empty=row['input_index'] == 1, gcd=False,
                                    casting=False, channeling=False, queue_committed=False)
        payload['state_observations'] = [dict(row, object='occupancy', value=row['occupancy'])
                                         for row in payload['inputs']]
        if additional_unknown_filler:
            payload['action_observations'] += [dict(row, object='first', actual_form='outbreak',
                base_button='outbreak', native_qualified=None) for row in payload['action_observations']]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=idle_engine) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    assert [(row['kind'], row.get('input_index')) for row in diagnosis['rules'][0]['findings']] == [
        ('avoidable_idle', 1)]
    operations = diagnosis['pool']['operations']
    assert [(row['operation'], row['source_path'], row['destination_path']) for row in operations] == [
        ('reduce_wait', [1], [1]), ('insert', None, [1])]
    changed = apply(result['rule_initialization']['program'], operations[0])
    assert changed[1] == dict(kind='WaitClicks', clicks=2)


def test_public_search_reuses_parent_score_feedback_without_diagnostic_simulation(tmp_path, monkeypatch):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    traced = []

    def feedback_engine(*args, **kwargs):
        if kwargs.get('trace'): traced.append(args[1]['blocks'])
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        action = result['blocks'][0][0]
        payload['feedback_events'] = [dict(event=event, ms=0, origin=1, step=0,
            action=action if event != 'input' else '-', signature=action if event != 'input' else '-',
            battle=1, rp=0, source='loop', event_index=10000+index)
            for index, event in enumerate(('input', 'dispatch_failed'))]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=feedback_engine):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=5, batch_targets=(2,),
                               iterations=2, validation_batches=1, final_batches=1, final_iterations=2,
                               scenarios=('nominal',)))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    assert traced == []
    assert result['search']['candidate_count'] == 5
    steps = list(saved['search']['rule_steps'].values())
    assert steps
    for step in steps:
        parent = next(row for row in result['search']['records']
                      if row['key'] == step['parent_candidate_key'])
        batch = parent['batches'][0]
        assert batch['feedback_evidence']['batch_key'] == batch['data_key']
        assert batch['feedback_evidence']['availability'] == 'same_scoring_batch'
        assert batch['feedback']['attempts'] == {parent['candidate']['blocks'][0][0]['simc_action']: 1}
        position = batch['position_summary'][0]
        assert position['candidate_identity'] == parent['key']
        assert position['click_position'] == position['action_position'] == 0
        assert position['action'] == parent['program'][0][0]
        assert position['failures'] == {'dispatch_failed': 1}


@pytest.mark.parametrize('missing_events,lifecycle_complete', [(False, True), (True, None), (False, False), (False, None)])
def test_public_short_window_uses_real_instance_bounds_and_keeps_missing_lifecycle_unknown(tmp_path, monkeypatch, missing_events, lifecycle_complete):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'short-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']}
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_short_buff')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='use short effect',
        template='short-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect_refs=['window'], window_selection='earliest_end', use_position='first_eligible', consume_required=True, usage_time_basis='effect_completion'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def window_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for row in payload['action_observations']:
            row['effect_completion_time'] = row['time']
            row['event_index'] += 1
        if not missing_events:
            event = dict(object='window', sample_id=1, effect_id='fixture_short_buff', instance_id=1,
                target_id=0, source_id=0, applicable=True, start=0, end=400)
            if lifecycle_complete is not None: event['lifecycle_complete'] = lifecycle_complete
            payload['effect_events'] = [dict(event, event_index=0, kind='start', time=0, end_reason=None),
                dict(event, event_index=10001, kind='expire', time=400, end_reason='expired')]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=window_engine) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    if missing_events or lifecycle_complete is not True:
        assert diagnosis['rules'][0]['status'] == 'unknown'
        assert diagnosis['pool']['operations'] == []
    else:
        assert [(row['kind'], row.get('input_index')) for row in diagnosis['rules'][0]['findings']] == [
            ('missed_short_window', 0), ('expired_unused', None)]
        assert len(diagnosis['pool']['operations']) == 2
        assert diagnosis['rules'][0]['findings'][0]['window']['instance_id'] == 1


@pytest.mark.parametrize('case', ['opportunity', 'input_before_execution_inside', 'input_inside_execution_after',
                                 'same_ms_before_end', 'same_ms_after_end', 'missing_execution',
                                 'duplicate_execution', 'wrong_execution_form', 'unknown_cast', 'wrong_precision',
                                 'missing_execution_input_before_end', 'missing_execution_input_after_end'])
def test_public_short_window_execution_basis_separates_estimate_and_actual_use(tmp_path, monkeypatch, case):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'short-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']}
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_short_buff')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='execute during window',
        template='short-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect_refs=['window'], window_selection='earliest_end', use_position='first_eligible',
            consume_required=False, usage_time_basis='execution'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def window_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['effect_events_complete'] = {'window': True}
        payload['scope']['execution_events_complete'] = False
        boundary_unknown = case.startswith('missing_execution_input_')
        for name in ('inputs', 'action_observations', 'state_observations'):
            payload[name] = payload[name][:4 if boundary_unknown else 3]
        for row in payload['action_observations']:
            row.update(effect_completion_time=None, event_index=row['input_index'] * 10 + 5,
                earliest_execute=row['time'], cast_ms=0, channel_ms=0,
                timing_precision='current_state_estimate', occupancy_end=row['time'] + 1000)
            if case == 'unknown_cast': row['cast_ms'] = None
            if case == 'wrong_precision': row['timing_precision'] = 'unverified'
        if case == 'missing_execution': payload['action_observations'][1]['success'] = None
        if boundary_unknown:
            payload['action_observations'][3].update(success=None,
                event_index=90 if case.endswith('before_end') else 110)
        event = dict(object='window', sample_id=1, effect_id='fixture_short_buff', instance_id=1,
            target_id=0, source_id=0, applicable=True, start=200, lifecycle_complete=True)
        payload['effect_events'] = [dict(event, event_index=10, kind='start', time=200, end=None, end_reason=None),
            dict(event, event_index=100, kind='expire', time=600, end=600, end_reason='expired')]
        execution = {
            'input_before_execution_inside': (0, 400, 50, 'death_coil'),
            'input_inside_execution_after': (1, 800, 110, 'death_coil'),
            'same_ms_before_end': (1, 600, 90, 'death_coil'),
            'same_ms_after_end': (1, 600, 110, 'death_coil'),
            'duplicate_execution': (1, 400, 50, 'death_coil'),
            'wrong_execution_form': (1, 400, 50, 'outbreak'),
        }.get(case)
        payload['action_events'] = [] if execution is None else [dict(
            object='consumer', sample_id=1, input_index=execution[0], time=execution[1],
            event_index=execution[2], kind='execute', success=True, actual_form=execution[3], target_id=1)]
        if case == 'duplicate_execution':
            payload['action_events'].append(dict(payload['action_events'][0], time=500, event_index=70))
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=window_engine) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    diagnosis = result['search']['rule_diagnostics']
    assert diagnosis == saved['search']['rule_diagnostics']
    kinds = {row['kind'] for row in diagnosis['rules'][0]['findings']}
    assert scoring.call_count == 1
    if case in ('unknown_cast', 'wrong_precision'):
        assert diagnosis['pool']['operations'] == []
    elif case in ('missing_execution', 'duplicate_execution', 'missing_execution_input_before_end'):
        assert 'expired_unused' not in kinds
        assert 'covered' not in kinds
    else:
        assert 'missed_short_window' in kinds or 'covered' in kinds
        assert bool(diagnosis['pool']['operations']) is (case not in ('same_ms_before_end',))
        assert ('covered' in kinds) is (case == 'same_ms_before_end')
        assert ('utilized_off_selected_position' in kinds) is (case == 'input_before_execution_inside')
        assert ('expired_unused' in kinds) is (case not in ('input_before_execution_inside', 'same_ms_before_end'))


@pytest.mark.parametrize('loop', [False, True])
def test_diagnostic_interface_enumerates_every_intermediate_gap_and_keeps_loop_repeats(tmp_path, monkeypatch, loop):
    """补充诊断/单操作公开接口；最高task公开链由上面用例覆盖。"""
    import sequence
    from program import canonicalize_search_program, compile_program
    from rule_diagnostics import apply, diagnose
    from runtime import TaskRuntime
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate):
        task = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
        blocks = [['outbreak'], ['outbreak'], ['outbreak'], ['death_coil']]
        program = [dict(kind='Loop', count=3, blocks=blocks)] if loop else blocks
        canonical = canonicalize_search_program(program, task['capabilities'])
        compiled = compile_program(canonical['program'], tmp_path / 'parent', identity=task['native_reference']['identity'],
                                   capabilities=task['capabilities'])
        evidence = sequence.evaluate(source, compiled, tmp_path / 'evidence', character=task['character'],
                                     iterations=2, trace=False)
        raw = evidence['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in raw[name]: row['source_step'] = row['input_index'] % len(compiled['blocks'])
        diagnosis = diagnose(program, task['capabilities'], task['rule_initialization'], evidence['report'],
            task_run_id=task['profile']['run_id'], batch_key='constructed-same-batch',
            behavior_identity=canonical['identity'], runtime=TaskRuntime())
        prefix = [0] if loop else []
        assert [(row['operation'], row['source_path'], row['destination_path'])
                for row in diagnosis['pool']['operations']] == [
            ('move', prefix+[3], prefix+[0]), ('move', prefix+[3], prefix+[1]),
            ('move', prefix+[3], prefix+[2]), ('insert', None, prefix+[0])]
        changed = apply(program, diagnosis['pool']['operations'][0])
        changed_canonical = canonicalize_search_program(changed, task['capabilities'])
        selected = compile_program(changed_canonical['program'], tmp_path / 'selected', identity=task['native_reference']['identity'],
                                   capabilities=task['capabilities'])
        scored = sequence.evaluate(source, selected, tmp_path / 'selected-score',
                                   character=task['character'], iterations=2, trace=False)
    assert diagnosis['pool']['complete'] is True
    if loop:
        assert changed == [dict(kind='Loop', count=3,
            blocks=[['death_coil'], ['outbreak'], ['outbreak'], ['outbreak']])]
    assert scored['blocks'] == [['death_coil'], ['outbreak'], ['outbreak'], ['outbreak']] * (3 if loop else 1)
    assert scored['summary']['dps'] > 0


def test_diagnostic_reuses_rejected_concrete_operations_within_existing_budget(tmp_path, monkeypatch):
    import sequence
    from program import canonicalize_search_program, compile_program
    from rule_diagnostics import diagnose
    from runtime import TaskRuntime
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate):
        task = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
        program = [['death_coil']] * 16 + [['outbreak']] * 2
        canonical = canonicalize_search_program(program, task['capabilities'])
        compiled = compile_program(canonical['program'], tmp_path / 'parent', identity=task['native_reference']['identity'],
                                   capabilities=task['capabilities'])
        evidence = sequence.evaluate(source, compiled, tmp_path / 'evidence', character=task['character'],
                                     iterations=2, trace=False)
        raw = evidence['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in raw[name]: row['source_step'] = row['input_index'] % 18
        for row in raw['state_observations']: row['value'] = 1
        diagnosis = diagnose(program, task['capabilities'], task['rule_initialization'], evidence['report'],
            task_run_id=task['profile']['run_id'], batch_key='repeated-concrete-operations',
            behavior_identity=canonical['identity'], runtime=TaskRuntime(2), requested_iterations=2)
    assert diagnosis['pool']['complete'] is True
    assert len(diagnosis['pool']['operations']) == 4


@pytest.mark.parametrize('case,expected', [('missing', 'unknown'), ('null_key', 'unknown'),
    ('null_record', 'unknown'), ('positive', 'true'), ('negative', 'false')])
def test_public_indexed_any_preserves_unknown_keys_and_true_false_results(tmp_path, monkeypatch, case, expected):
    import sequence
    pack = _condition_pack()
    rows = dict(op='map', args=[dict(var='scalar'), dict(var='raw.value')], **{'as': 'raw'})
    answer = dict(op='any3', args=[dict(op='map', args=[rows, dict(op='and', args=[True,
        dict(op='eq', args=[dict(var='item.input_index'), 7])])], **{'as': 'item'})])
    template = dict(application_phase='post_simulation_diagnosis_and_next_candidate',
        parameters=dict(state=dict(type='state_ref')),
        reads=[dict(**{'as': 'scalar', 'from': 'student.state_observations'}, object=dict(arg='state'),
                    fields=['value'], same_run=True, on_declared_null_object='not_applicable_identity_rows')],
        diagnose=dict(let=[dict(name='answer', value=answer)], for_each=[{}], **{'as': 'unused'},
            cases=[dict(kind=name, when=condition, certainty='unknown' if name == 'unknown' else 'observed_fact',
                        evidence={}) for name, condition in [
                ('unknown', dict(op='unknown', args=[dict(var='answer')])),
                ('true', dict(var='answer')), ('false', dict(op='not', args=[dict(var='answer')]))]],
            export_trigger_records=[]), edits=[])
    pack['general']['templates'] = {'generic-any': template}
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='any result',
        template='generic-any', arguments=dict(state='counter'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def indexed_rows(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        observations = result['report']['sim']['players'][0]['sim2gse_rule_observations']['state_observations']
        for row in observations: row['value'] = dict(input_index=8)
        if case != 'negative': observations[0]['value'] = None if case == 'null_record' else (
            dict(input_index=None) if case == 'null_key' else {})
        if case == 'positive': observations[1]['value'] = dict(input_index=7)
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=indexed_rows):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    assert [row['kind'] for row in result['search']['rule_diagnostics']['rules'][0]['findings']] == [expected]


@pytest.mark.parametrize('first_scope,second_scope', [('scope_a', 'scope_b'), ('renamed_a', 'renamed_b')])
def test_public_observation_request_closes_only_declared_object_dependencies(tmp_path, monkeypatch, first_scope, second_scope):
    import sequence
    pack = _condition_pack()
    pack['object_sets']['sample'].update({
        first_scope: dict(kind='target_scope', value='current_attack_target'),
        second_scope: dict(kind='target_scope', value='all_currently_engaged_required_targets'),
        'unused_scope': dict(kind='target_scope', value='controlled_player'),
        'qualification': dict(kind='state', native_identity='literal.true'),
        'compound': dict(kind='effect', components=[
            dict(native_identity='first_component', target_scope=first_scope),
            dict(native_identity='second_component', target_scope=second_scope)],
            from_action='first', qualification='qualification')})
    for rule in pack['configurations'][0]['states']['only']['priority']:
        rule['arguments']['activation_effect'] = 'compound'
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    requests = []

    def requested_engine(*args, **kwargs):
        requests.append(copy.deepcopy(kwargs['rule_observation_request']))
        return _observed_evaluate(*args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=requested_engine):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    request, = requests
    assert set(request['objects']) == {'consumer', 'counter', 'compound', 'first', 'qualification', first_scope, second_scope}


@pytest.mark.parametrize('entry', ['resume', 'run_resume'])
def test_public_failed_rule_step_is_terminal_and_repeat_does_not_score(tmp_path, monkeypatch, entry):
    import sequence
    from engine import CandidateError
    from runtime import TaskCancelled
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    calls, selected_failures = [], []

    def failed_engine(*args, **kwargs):
        actions = tuple(command['simc_action'] for block in args[1]['blocks'] for command in block)
        calls.append(actions)
        if len(calls) == 1: return _observed_evaluate(*args, **kwargs)
        if actions == ('death_coil', 'outbreak'):
            selected_failures.append(actions)
            raise CandidateError('constructed selected operation scoring failure')
        raise TaskCancelled('pause original pending at external dispatch boundary')

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=failed_engine):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=3, batch_targets=(2,), iterations=2))
        parent = read_task(tmp_path / 'task')['search']['rule_diagnostics']
        operation = next(row for row in parent['pool']['operations'] if row['operation'] == 'move')
        request = dict(parent_identity=parent['parent_identity'], operation_id=operation['operation_id'])
        invoke = (lambda: resume_task(tmp_path / 'task', rule_step=request)) if entry == 'resume' else (
            lambda: run_task(source, tmp_path / 'task', resume=True, rule_step=request))
        invoke()
        saved = read_task(tmp_path / 'task')
        step = saved['search']['rule_steps'][request['operation_id']]
        assert step['status'] == 'failed'
        assert 'constructed selected operation scoring failure' in step['reason']
        count = len(calls)
        again = invoke()
    assert len(calls) == count
    assert len(selected_failures) == 1
    assert again['search']['rule_steps'][request['operation_id']] == step


@pytest.mark.parametrize('requested,actual_form,supported', [
    ('consumer', 'death_coil', True), ('consumer', 'fixture_form', True),
    ('specific_form', 'fixture_form', True), ('specific_form', 'death_coil', False)])
def test_public_rule_rejects_known_form_mismatch_but_keeps_declared_base_family(tmp_path, monkeypatch, requested, actual_form, supported):
    import sequence
    pack = _condition_pack()
    pack['object_sets']['sample']['consumer']['native_forms'].append('fixture_form')
    pack['object_sets']['sample']['specific_form'] = dict(kind='action', native_action='fixture_form',
        base_button='death_coil', native_forms=['fixture_form'])
    for rule in pack['configurations'][0]['states']['only']['priority']: rule['arguments']['action'] = requested
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def form_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        for row in result['report']['sim']['players'][0]['sim2gse_rule_observations']['action_observations']:
            row.update(object=requested, actual_form=actual_form, native_qualified=None,
                has_cooldown=False, resource_costs={'runic_power': 10}, resource_balances={'runic_power': 20},
                known_native_requirements=[])
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=form_engine):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    diagnosis = result['search']['rule_diagnostics']
    assert bool(diagnosis['pool']['operations']) is supported
    if not supported:
        assert not any(row['kind'] == 'missed_opportunity' for row in diagnosis['rules'][0]['findings'])


@pytest.mark.parametrize('use_burst', [False, True])
@pytest.mark.parametrize('requested_form', ['army_of_the_dead', 'fixture_protected_form'])
def test_public_frozen_burst_protection_blocks_high_rule_without_suppressing_ordinary_rule(tmp_path, monkeypatch, use_burst, requested_form):
    import burst, result_store, sequence
    from test_burst import reviewed_fixture, character_seed_boundary
    pack = _condition_pack()
    pack['object_sets']['sample']['protected'] = dict(kind='action', native_action=requested_form,
        base_button='army_of_the_dead', native_forms=[requested_form])
    rules = pack['configurations'][0]['states']['only']['priority']
    rules[0].update(name='high protected')
    rules[0]['arguments'].update(action='protected', state=None, compare='always', value=None)
    rules[1].update(name='ordinary consumer')
    rules[1]['arguments'].update(priority_refs=['high protected'], state=None, compare='always', value=None)
    _configure_opener(tmp_path, monkeypatch, pack)
    result_store.DATA_ROOT.mkdir()
    definition, profile = reviewed_fixture()
    burst.publish(definition)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(profile, encoding='utf-8')

    def protected_engine(*args, **kwargs):
        sources = kwargs.pop('input_sources', None)
        kwargs.pop('burst_candidate', None)
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for index, row in enumerate(payload[name]):
                row['input_source'] = sources[index] if sources else 'loop'
        ordinary = payload['action_observations']
        for row in ordinary: row['input_allowed'] = row['input_source'] == 'loop'
        payload['action_observations'] += [dict(row, object='protected', actual_form=requested_form,
            base_button='army_of_the_dead') for row in ordinary]
        return result

    with character_seed_boundary(native_reference=native), patch.object(sequence, 'evaluate', side_effect=protected_engine):
        result = run_task(source, tmp_path / 'task', use_burst=use_burst,
            simulation_config=dict(scene='single_target'), search_config=dict(input_interval_ms=200,
                candidate_limit=1, batch_targets=(2,), iterations=2))
    diagnosis = result['search']['rule_diagnostics']
    high, low = diagnosis['rules']
    if use_burst:
        assert {row['kind'] for row in high['findings']} == {'blocked_by_plan'}
        assert 'missed_opportunity' in {row['kind'] for row in low['findings']}
        assert diagnosis['pool']['operations']
        assert all(c['rule'] == 'ordinary consumer' for op in diagnosis['pool']['operations'] for c in op['contributors'])
    else:
        assert {row['kind'] for row in high['findings']} == {'missed_opportunity'}
        assert {row['kind'] for row in low['findings']} == {'yielded'}


@pytest.mark.parametrize('selected_outcome', ['scored', 'failed'])
def test_public_terminal_rule_step_republishes_saved_result_after_storage_crash_without_scoring(tmp_path, monkeypatch, selected_outcome):
    import result_store, sequence
    from engine import CandidateError
    from runtime import TaskCancelled

    class StorageCrash(BaseException):
        pass

    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    calls = []

    def interrupted_engine(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 2: raise TaskCancelled('pause after first scored parent')
        if len(calls) > 2 and selected_outcome == 'failed':
            raise CandidateError('selected operation failed before result publication')
        return _observed_evaluate(*args, **kwargs)

    write, intended_limits = result_store.write, []
    def crash_result_save(table, *args, **kwargs):
        if table == 'runs':
            intended_limits.append(args[1][0]['search_metrics']['no_improvement_round_limit'])
            raise StorageCrash('process stopped before result publication')
        return write(table, *args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=interrupted_engine):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=3, batch_targets=(2,), iterations=2))
        diagnosis = read_task(tmp_path / 'task')['search']['rule_diagnostics']
        operation = next(row for row in diagnosis['pool']['operations'] if row['operation'] == 'move')
        request = dict(parent_identity=diagnosis['parent_identity'], operation_id=operation['operation_id'])
        with patch.object(result_store, 'write', side_effect=crash_result_save), pytest.raises(StorageCrash):
            resume_task(tmp_path / 'task', rule_step=request)
        count = len(calls)
        recovered = resume_task(tmp_path / 'task', rule_step=request)
        saved = read_task(tmp_path / 'task', include_search_records=True)
    assert len(calls) == count
    assert recovered['status'] != 'running'
    assert recovered['independent_validation_complete'] is False
    assert recovered['final']['status'] == 'not_requested'
    assert saved['search']['rule_steps'][request['operation_id']]['status'] == selected_outcome
    assert saved['search']['candidate_count'] == 3
    assert saved['search']['no_improvement_round_limit'] == intended_limits[0]
    if selected_outcome == 'scored':
        assert any(row.get('rule_step', {}).get('request') == request for row in saved['search']['records'])


def test_public_logging_off_strips_reused_diagnostic_costs_before_task_checkpoint(tmp_path, monkeypatch):
    import sequence, sqlite3
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    config = dict(input_interval_ms=200, candidate_limit=2, batch_targets=(2,), iterations=2)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate):
        run_task(source, tmp_path / 'logged', search_config=dict(config, diagnostic_logging=True),
                 simulation_config=dict(scene='single_target'))
        second = run_task(source, tmp_path / 'quiet', search_config=dict(config, diagnostic_logging=False),
                          simulation_config=dict(scene='single_target'))
        saved = read_task(tmp_path / 'quiet', include_search_records=True)
    reused = [batch['data_key'] for row in second['search']['records'] for batch in row['batches'] if batch.get('cached')]
    assert reused
    assert all('costs' not in row['rule_diagnostics'] for row in saved['search']['records'])

    def checkpoint(folder):
        with sqlite3.connect((tmp_path / folder / 'task.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
            return {key: json.loads(value) for key, value in db.execute('SELECT key,value FROM batches')}

    before, after = checkpoint('logged'), checkpoint('quiet')
    assert any('costs' in before[key].get('rule_diagnostics', {}) for key in reused)
    assert all('costs' not in row.get('rule_diagnostics', {}) for row in after.values())


def test_public_rule_step_cancelled_during_comparison_resumes_pending_without_rescoring(tmp_path, monkeypatch):
    import sequence
    from runtime import TaskCancelled
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    search_calls, validation_calls = [], []
    cancel_comparison = [True]

    def interrupted_engine(*args, **kwargs):
        if kwargs.get('rule_observation_request') is not None:
            search_calls.append(args[1])
            if len(search_calls) == 2: raise TaskCancelled('pause original pending')
        else:
            validation_calls.append(args[1])
            if cancel_comparison[0]:
                cancel_comparison[0] = False
                raise TaskCancelled('selected score saved, comparison not archived')
        return _observed_evaluate(*args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=interrupted_engine):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=3, batch_targets=(2,),
                               iterations=2, validation_batches=1, max_processes=1))
        parent = read_task(tmp_path / 'task')['search']['rule_diagnostics']
        operation = next(row for row in parent['pool']['operations'] if row['operation'] == 'insert')
        request = dict(parent_identity=parent['parent_identity'], operation_id=operation['operation_id'])
        stopped = resume_task(tmp_path / 'task', rule_step=request)
        assert stopped['status'] == 'cancelled'
        before = read_task(tmp_path / 'task', include_search_records=True)
        assert not any(row.get('rule_step') for row in before['search']['records'])
        selected_identity = sequence.behavior_key(search_calls[-1])
        count = sum(sequence.behavior_key(row) == selected_identity for row in search_calls)
        resume_task(tmp_path / 'task', rule_step=request)
        saved = read_task(tmp_path / 'task', include_search_records=True)
    assert sum(sequence.behavior_key(row) == selected_identity for row in search_calls) == count == 1
    assert len(validation_calls) >= 2
    assert any(row.get('rule_step', {}).get('request') == request for row in saved['search']['records'])
    assert saved['search']['rule_steps'][request['operation_id']]['status'] == 'scored'


@pytest.mark.parametrize('incomplete_extra', [False, True])
@pytest.mark.parametrize('copy_window', [False, True])
def test_public_overlapping_short_effects_select_per_input_and_keep_original_instances(tmp_path, monkeypatch, incomplete_extra, copy_window):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    template = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']
    # 通过可编辑模板额外输出支持集合，核对A→B→A而非切断/复制A实例。
    next(row['value'] for row in template['diagnose']['let'] if row['name'] == 'contexts')['args'][1]['fields']['assigned_inputs'] = dict(op='map',
        args=[dict(var='rows'), dict(var='q.action.input_index')], **{'as': 'q'})
    template['diagnose']['cases'].append(dict(kind='window_assignment', when=True, certainty='observed_fact',
        evidence=dict(window=dict(var='c.window'), inputs=dict(var='c.assigned_inputs'))))
    if copy_window:
        next(row['value'] for row in template['diagnose']['let'] if row['name'] == 'contexts')['let'][0]['value']['args'][0]['args'][1] = dict(
            op='merge', args=[dict(var='w'), {}])
    pack['general']['templates'] = {'overlap-renamed': template}
    pack['object_sets']['sample'].update(window_a=dict(kind='effect', native_identity='first_buff'),
                                        window_b=dict(kind='effect', native_identity='second_buff'))
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='earliest actual end',
        template='overlap-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect_refs=['window_a', 'window_b'], window_selection='earliest_end',
            use_position='last_finishable', consume_required=False, usage_time_basis='effect_completion'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def overlap_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['effect_events_complete'] = {'window_a': True, 'window_b': True}
        for name in ('inputs', 'action_observations', 'state_observations'):
            payload[name] = payload[name][:6]
        for row in payload['action_observations']:
            row.update(effect_completion_time=row['time'], event_index=row['input_index'] * 10 + 1)
        payload['effect_events'] = []
        for alias, instance, start, end, start_index, end_index, complete in [
                ('window_a', 101, 0, 1000, 0, 60, True), ('window_b', 102, 400, 600, 20, 40, True),
                *([('window_a', 103, 0, 200, 2, 15, False)] if incomplete_extra else [])]:
            event = dict(object=alias, sample_id=1, effect_id=alias, instance_id=instance,
                target_id=0, source_id=0, applicable=True, start=start, lifecycle_complete=complete)
            payload['effect_events'].extend([
                dict(event, event_index=start_index, kind='start', time=start, end=None, end_reason=None),
                dict(event, event_index=end_index, kind='expire', time=end, end=end, end_reason='expired')])
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=overlap_engine) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    rule, = result['search']['rule_diagnostics']['rules']
    assignments = [row for row in rule['findings'] if row['kind'] == 'window_assignment']
    assert [(row['window']['instance_id'], row['window']['start'], row['window']['end'], row['inputs'])
            for row in assignments] == [(101, 0, 1000, [0, 1, 4, 5]), (102, 400, 600, [2, 3])]
    assert [(row['window']['instance_id'], row['input_index']) for row in rule['findings']
            if row['kind'] == 'missed_short_window'] == [(101, 5), (102, 3)]
    assert bool(rule['unknown_evidence']) is incomplete_extra
    assert scoring.call_count == 1


@pytest.mark.parametrize('windows', ['empty', 'unproven', 'incomplete', 'incomplete_before_start', 'mixed',
                                     'known_uncovered', 'known_coverage_false'])
def test_public_incomplete_window_keeps_scoped_unknown_trigger_without_erasing_known_support(tmp_path, monkeypatch, windows):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    template = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']
    pack['general']['templates']['window-renamed'] = template
    pack['object_sets']['sample'].update(window=dict(kind='effect', native_identity='fixture_window'),
        high_action=copy.deepcopy(pack['object_sets']['sample']['consumer']))
    low = pack['configurations'][0]['states']['only']['priority'][0]
    low.update(name='ordinary lower')
    low['arguments']['priority_refs'] = ['higher window']
    high = dict(name='higher window', template='window-renamed', arguments=dict(action='high_action',
        priority_refs=[], edit_range='editable', effect_refs=['window'], window_selection='earliest_end',
        use_position='first_eligible', consume_required=False, usage_time_basis='effect_completion'))
    pack['configurations'][0]['states']['only']['priority'] = [high, low]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def uncertain_engine(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:6]
        for row in payload['state_observations']: row['value'] = 1 if row['input_index'] in (0, 2, 3, 4) else 0
        ordinary = payload['action_observations']
        payload['action_observations'] += [dict(row, object='high_action', effect_completion_time=row['time'],
            event_index=row['input_index'] * 10 + 1, native_qualified=row['input_index'] != 3) for row in ordinary]
        if windows == 'incomplete_before_start':
            next(row for row in payload['action_observations'] if row['object'] == 'high_action' and row['input_index'] == 2)['event_index'] = 19
        payload['effect_events'] = []
        if windows not in ('unproven', 'known_uncovered', 'known_coverage_false'):
            payload['scope']['effect_events_complete'] = {'window': True}
        elif windows == 'known_coverage_false': payload['scope']['effect_events_complete'] = {'window': False}
        episodes = [('not_requested', 999, 0, 1000, 0, 60, False)]
        if windows not in ('empty', 'unproven', 'known_uncovered', 'known_coverage_false'):
            episodes.append(('window', 102, 400, 600, 20, 40, False))
        if windows == 'mixed': episodes.append(('window', 101, 0, 1000, 0, 60, True))
        if windows in ('known_uncovered', 'known_coverage_false'):
            episodes.append(('window', 101, 0, 200, 0, 15, True))
        for alias, instance, start, end, start_index, end_index, complete in episodes:
            event = dict(object=alias, sample_id=1, effect_id=alias, instance_id=instance,
                target_id=0, source_id=0, applicable=True, start=start, lifecycle_complete=complete)
            payload['effect_events'].extend([
                dict(event, event_index=start_index, kind='start', time=start, end=None, end_reason=None),
                dict(event, event_index=end_index, kind='expire', time=end, end=end, end_reason='expired')])
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=uncertain_engine):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    higher, lower = result['search']['rule_diagnostics']['rules']
    findings = {(row.get('input_index'), row['kind']) for row in lower['findings']}
    if windows != 'unproven':
        assert (0, 'yielded' if windows in ('mixed', 'known_uncovered', 'known_coverage_false') else 'missed_opportunity') in findings
    assert (3, 'missed_opportunity') in findings  # 高位自身已知不符合，不能扩成未知让位。
    if windows not in ('unproven', 'known_uncovered', 'known_coverage_false'):
        assert (4, 'missed_opportunity') in findings  # 可信窗口外，不受未知实例污染。
    else:
        assert all((index, 'missed_opportunity') not in findings for index in (2, 4))
        if windows == 'unproven': assert (0, 'missed_opportunity') not in findings
    if windows in ('empty', 'incomplete_before_start'):
        assert (2, 'missed_opportunity') in findings
        if windows == 'empty': assert higher['status'] == 'not_applicable'
    else:
        assert (2, 'missed_opportunity') not in findings
        assert (2, 'yielded') not in findings
        assert any(row['input_index'] == 2 for row in lower['unknown_conditions'])


@pytest.mark.parametrize('evidence', ['success', 'consume', 'blocked', 'uncertain_only'])
def test_public_short_window_keeps_known_existence_with_additional_uncertain_members(tmp_path, monkeypatch, evidence):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'window-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']}
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_window')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='known positive evidence',
        template='window-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect_refs=['window'], window_selection='earliest_end', use_position='first_eligible',
            consume_required=evidence == 'consume', usage_time_basis='effect_completion'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def known_and_unknown(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['effect_events_complete'] = {'window': True}
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:3]
        for row in payload['action_observations']:
            row.update(effect_completion_time=row['time'], event_index=row['input_index'] * 10 + 1,
                success=[False, evidence != 'uncertain_only', None][row['input_index']])
            if evidence == 'blocked': row['input_allowed'] = None if row['input_index'] == 1 else False
        event = dict(object='window', sample_id=1, effect_id='fixture_window', instance_id=1,
            target_id=0, source_id=0, applicable=True, start=0, lifecycle_complete=True)
        payload['effect_events'] = [dict(event, event_index=0, kind='start', time=0, end=None, end_reason=None),
            dict(event, event_index=100, kind='expire', time=400, end=400, end_reason='expired')]
        if evidence == 'consume':
            payload['effect_events'] += [dict(event, event_index=20, kind='consume', time=200,
                source_input_index=1, source_actual_action='death_coil', end=None, end_reason=None),
                dict(event, event_index=39, kind='consume', time=400, source_input_index=None,
                source_actual_action=None, end=None, end_reason=None)]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=known_and_unknown):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    rule, = result['search']['rule_diagnostics']['rules']
    kinds = {row['kind'] for row in rule['findings']}
    if evidence == 'uncertain_only':
        assert 'utilized_off_selected_position' not in kinds
    else:
        assert ('blocked_by_plan' if evidence == 'blocked' else 'utilized_off_selected_position') in kinds
    assert 'expired_unused' not in kinds


@pytest.mark.parametrize('uncertain_side', ['left', 'right'])
@pytest.mark.parametrize('matching_key', [False, True])
def test_collection_join_preserves_membership_without_promoting_unknown_support(uncertain_side, matching_key):
    from rule_diagnostics import Evaluation, Rows, UNKNOWN
    evaluation = Evaluation({}, {}, None, lambda: None, None, {})
    known = dict(run_id='task', sample_id=1, input_index=7)
    possible = dict(known, input_index=7 if matching_key else 9)
    env = {name: Rows([known], [possible] if name == uncertain_side else [])
           for name in ('left', 'right')}
    joined = evaluation.value(dict(op='join', keys=['run_id', 'sample_id', 'input_index'], args=[
        dict(**{'as': name}, rows=dict(var=name)) for name in ('left', 'right')]), env)
    assert len(joined) == 1
    assert len(joined.uncertain) == int(matching_key)
    filtered = evaluation.value(dict(op='filter', args=[dict(var='joined'),
        dict(op='eq', args=[dict(var='row.input_index'), 7])], **{'as': 'row'}), dict(joined=joined))
    assert len(filtered) == 1 and len(filtered.uncertain) == int(matching_key)
    env = dict(rows=filtered)
    assert evaluation.value(dict(op='not', args=[dict(op='empty', args=[dict(var='rows')])]), env) is True
    assert evaluation.value(dict(op='any3', args=[dict(op='map', args=[dict(var='rows'), True],
        **{'as': 'row'})]), env) is True
    count = evaluation.value(dict(op='count', args=[dict(var='rows')]), env)
    assert count is UNKNOWN if matching_key else count == 1
    for operation in ('first_true', 'last_true'):
        expression = dict(op=operation, args=[dict(var='rows'), True], **{'as': 'row'}, order_by='input_index')
        assert evaluation.value(expression, env) == joined[0]
        possible_only = dict(rows=Rows(uncertain=filtered.uncertain))
        selected = evaluation.value(expression, possible_only)
        assert selected is UNKNOWN if matching_key else selected == {}
    excluded = evaluation.value(dict(op='filter', args=[dict(var='rows'), False], **{'as': 'row'}), env)
    assert evaluation.value(dict(op='empty', args=[dict(var='excluded')]), dict(excluded=excluded)) is True


@pytest.mark.parametrize('membership_known', [False, True])
def test_public_left_join_keeps_possible_missing_effect_when_only_uncertain_match_exists(tmp_path, monkeypatch, membership_known):
    import sequence
    pack = _condition_pack()
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_effect')
    template = dict(application_phase='post_simulation_diagnosis_and_next_candidate',
        parameters=dict(action=dict(type='action_ref'), effect=dict(type='effect_ref')),
        reads=[dict(**{'as': alias, 'from': source}, object=dict(arg=argument), fields=fields,
                    same_run=True, on_declared_null_object='not_applicable_identity_rows')
            for alias, source, argument, fields in [
                ('actions', 'student.action_observations', 'action', ['input_index']),
                ('effects', 'student.effect_observations', 'effect', ['input_index', 'active', 'applicable'])]],
        diagnose=dict(let=[dict(name='possible', value=dict(op='filter',
                args=[dict(var='effects'), dict(var='effect.applicable')], **{'as': 'effect'})),
            dict(name='joined', value=dict(op='join',
                args=[dict(**{'as': 'action'}, rows=dict(var='actions')),
                      dict(**{'as': 'effect'}, rows=dict(var='possible'))],
                keys=['run_id', 'sample_id', 'input_index'], join_type='left', preserve_aliases=True)),
            dict(name='missing', value=dict(op='filter', args=[dict(var='joined'),
                dict(op='not', args=[dict(var='row.effect.active')])], **{'as': 'row'}))],
            for_each=dict(var='actions'), **{'as': 'action'}, cases=[
                dict(kind='proven_no_missing', when=dict(op='empty', args=[dict(var='missing')]), certainty='observed_fact'),
                dict(kind='unknown', when=dict(op='unknown', args=[dict(op='empty', args=[dict(var='missing')])]), certainty='unknown')],
            export_trigger_records=[]), edits=[])
    pack['general']['templates'] = {'left-effect-join': template}
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='possible effect member',
        template='left-effect-join', arguments=dict(action='consumer', effect='window'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def possible_effect(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:1]
        payload['effect_observations'] = [dict(payload['inputs'][0], object='window', active=True,
            applicable=True if membership_known else None)]
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=possible_effect):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    rule, = result['search']['rule_diagnostics']['rules']
    assert [row['kind'] for row in rule['findings']] == ['proven_no_missing' if membership_known else 'unknown']


@pytest.mark.parametrize('future_storage_version', [False, True])
def test_public_mixed_state_values_keep_types_through_batch_storage_and_cache(tmp_path, monkeypatch, future_storage_version):
    import result_store, sequence, sqlite3
    pack = _condition_pack()
    values = dict(flag=True, health=99.5, uncertain=None, empty={},
                  occupancy=dict(gcd=False, casting=False, channeling=False, queue_committed=False))
    for name in values:
        pack['object_sets']['sample'][name] = dict(kind='state', native_identity='fixture.'+name)
        template = pack['general']['templates']['renamed-template']
        template['parameters'][name] = dict(type='state_ref')
        template['reads'].append(dict(**{'as': name, 'from': 'student.state_observations'},
            object=dict(arg=name), fields=['input_index', 'value'], same_run=True,
            on_declared_null_object='not_applicable_identity_rows'))
        for binding in pack['configurations'][0]['states']['only']['priority']: binding['arguments'][name] = name
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    original = []

    def mixed_states(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:2]
        payload['state_observations'] += [dict(row, object=name, value=value)
            for row in payload['inputs'] for name, value in values.items()]
        original.append(copy.deepcopy(payload))
        return result

    config = dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=mixed_states) as scoring:
        first = run_task(source, tmp_path / 'first', simulation_config=dict(scene='single_target'), search_config=config)
        saved = read_task(tmp_path / 'first', include_search_records=True, include_reports=True)
        if future_storage_version:
            receipt = first['search']['records'][0]['batches'][0]
            batch = result_store.one('batches', 'batch_key', receipt['data_key'])
            group = batch['storage_group_key']
            api = result_store._api()
            with api['read_key'](result_store.DATA_ROOT, 'batches', group) as cursor:
                names = [column[0] for column in cursor.description]
                rows = [dict(zip(names, values)) for values in cursor.fetchall()]
            rows[0]['report']['sim']['players'][0]['sim2gse_rule_observations']['state_observations'][0]['value_storage']['version'] = 3
            api['write'](result_store.DATA_ROOT, 'batches', group, rows)  # 模拟由更新版本合法保存的分片。
            with sqlite3.connect(tmp_path / 'cache.sqlite3') as database:
                before = database.execute('SELECT value FROM reusable WHERE key=?', (receipt['data_key'],)).fetchone()
            physical = result_store.DATA_ROOT / 'batches' / (group+'.parquet')
            before_bytes = physical.read_bytes()
            with patch.object(sequence, 'evaluate', side_effect=AssertionError('不应重模拟未知存储版本')) as extra:
                with pytest.raises(TaskError, match='状态值存储版本'):
                    run_task(source, tmp_path / 'second', simulation_config=dict(scene='single_target'), search_config=config)
            assert extra.call_count == 0 and scoring.call_count == 1
            with sqlite3.connect(tmp_path / 'cache.sqlite3') as database:
                assert database.execute('SELECT value FROM reusable WHERE key=?', (receipt['data_key'],)).fetchone() == before
            assert physical.read_bytes() == before_bytes
            return
        second = run_task(source, tmp_path / 'second', simulation_config=dict(scene='single_target'), search_config=config)
    assert scoring.call_count == 1
    assert first['status'] == saved['status'] == second['status'] == 'completed'
    receipt = first['search']['records'][0]['batches'][0]
    batch = result_store.one('batches', 'batch_key', receipt['data_key'])
    for read in (batch, *result_store.read_records('batches', batch['storage_group_key']),
                 *result_store.read_many('batches', [batch['storage_group_key']])):
        actual = read['report']['sim']['players'][0]['sim2gse_rule_observations']['state_observations']
        expected = original[0]['state_observations']
        assert [(row['object'], type(row['value']), row['value']) for row in actual] == [
            (row['object'], type(row['value']), row['value']) for row in expected]
        assert all('value_storage' not in row for row in actual)
    assert second['search']['records'][0]['batches'][0]['cached'] is True


def test_batch_state_value_storage_is_idempotent_and_reads_with_legacy_scalar_shard():
    import result_store
    def record(key, values):
        return dict(batch_key=key, report=dict(sim=dict(players=[dict(collected_data=dict(dps=dict(mean=1.0)), sim2gse_rule_observations=dict(
            state_observations=[dict(object='state', value=value) for value in values]))])))
    legacy = record('legacy', [3])
    modern = record('modern', [True, False, 3, 99.5, None, dict(gcd=False)])
    modern['report']['sim']['players'][0]['sim2gse_rule_observations']['state_observations'].append(dict(object='missing'))
    untouched = copy.deepcopy(modern)
    prepared = result_store.prepare_batch(modern)
    assert result_store.prepare_batch(prepared) == prepared
    assert modern == untouched
    result_store.write('batches', 'legacy', [legacy])
    result_store.write_batch('modern', modern)
    rows = result_store.read_many('batches', ['legacy', 'modern'])
    assert {row['batch_key'] for row in rows} == {'legacy', 'modern'}
    by_key = {row['batch_key']: row for row in rows}
    for key, expected in (('legacy', [3]), ('modern', [True, False, 3, 99.5, None, dict(gcd=False)])):
        actual = by_key[key]['report']['sim']['players'][0]['sim2gse_rule_observations']['state_observations']
        assert [(type(row['value']), row['value']) for row in actual if row['object'] != 'missing'] == [
            (type(value), value) for value in expected]
        if key == 'modern': assert 'value' not in next(row for row in actual if row['object'] == 'missing')


def test_batch_observation_empty_values_and_sparse_costs_keep_their_original_meaning():
    import result_store
    from search import digest
    costs = [{}, {'rune': 0}, {'runic_power': 2}, {'runic_power': None}, None]
    actions = [dict(object='action', resource_costs=value) for value in costs] + [dict(object='missing-cost')]
    payload = dict(state_observations=[dict(object='empty', value={}), dict(object='unknown', value=None)],
                   action_observations=actions, action_events=[dict(row, kind='qualification') for row in actions]
                       + [dict(object='executed-action', kind='execute')])
    row = dict(batch_key='shape-modern', report=dict(sim=dict(players=[dict(
        collected_data=dict(dps=dict(mean=1.0), absent_statistics={}), sim2gse_rule_observations=payload)])))
    original = copy.deepcopy(row)
    prepared = result_store.prepare_batch(row)
    assert result_store.prepare_batch(prepared) == prepared
    result_store.write_batch('shape-modern', row)
    legacy = dict(batch_key='shape-legacy', report=dict(sim=dict(players=[dict(
        collected_data=dict(dps=dict(mean=1.0)), sim2gse_rule_observations=dict(
            action_observations=[dict(object='legacy', resource_costs={'rune': 0})]))])))
    result_store.write('batches', 'shape-legacy', [legacy])
    assert row == original
    for read in (result_store.one('batches', 'batch_key', 'shape-modern'),
                 *result_store.read_records('batches', 'shape-modern'),
                 *result_store.read_many('batches', ['shape-legacy', 'shape-modern'], columns=['batch_key', 'report'])):
        player = read['report']['sim']['players'][0]
        actual = player['sim2gse_rule_observations']
        if read['batch_key'] == 'shape-legacy':
            # A legacy padded NULL is not evidence that this key was originally absent.
            assert actual['action_observations'][0]['resource_costs']['runic_power'] is None
            continue
        assert actual['state_observations'][0]['value'] == {}
        assert actual['state_observations'][1]['value'] is None
        for collection in ('action_observations', 'action_events'):
            assert [item['resource_costs'] for item in actual[collection][:len(costs)]] == costs
            assert all('resource_costs' not in item for item in actual[collection][len(costs):])
            assert all('resource_costs_storage' not in item for item in actual[collection])
        assert digest(result_store._report_columns(actual)) == digest(result_store._report_columns(payload))
        assert player['collected_data']['absent_statistics'] is None  # Existing statistics convention remains.
    with result_store.query('SELECT typeof(report.sim.players[1].sim2gse_rule_observations.action_observations[1].resource_costs) FROM batches', tables=['batches']) as cursor:
        assert all('STRUCT' in value[0] for value in cursor.fetchall())


@pytest.mark.parametrize('fault', ['future_version', 'duplicate_keys', 'missing_declared_key', 'extra_nonnull'])
def test_batch_cost_storage_rejects_unknown_or_conflicting_shape_without_guessing(fault):
    import result_store
    storage = dict(version=1, kind='record', keys=['rune'])
    costs = dict(rune=0)
    if fault == 'future_version': storage['version'] = 2
    elif fault == 'duplicate_keys': storage['keys'].append('rune')
    elif fault == 'missing_declared_key': costs = None  # Physical NULL cannot contain the declared key.
    else: costs['runic_power'] = 1
    result_store.write('batches', 'cost-shape-broken', [dict(batch_key='cost-shape-broken',
        report=dict(sim=dict(players=[dict(sim2gse_rule_observations=dict(action_observations=[
            dict(object='action', resource_costs=costs, resource_costs_storage=storage)]))])))])
    expected = result_store.DataReadError if fault == 'future_version' else result_store.InvalidRecordError
    for read in (lambda: result_store.one('batches', 'batch_key', 'cost-shape-broken'),
                 lambda: result_store.read_many('batches', ['cost-shape-broken'])):
        with pytest.raises(expected, match='费用映射存储') as caught: read()
        if fault == 'future_version': assert not isinstance(caught.value, result_store.InvalidRecordError)


@pytest.mark.parametrize('fault', ['version', 'kind', 'kind_object', 'conflict'])
def test_batch_state_value_storage_rejects_unknown_encoding_without_guessing(fault):
    import result_store
    encoded = dict(version=1, kind='boolean', boolean=True, integer=None, number=None, record=None)
    state = dict(object='state', value_storage=encoded)
    if fault == 'version': encoded['version'] = 3
    elif fault == 'kind': encoded['kind'] = 'unsupported'
    elif fault == 'kind_object': encoded['kind'] = dict(op='not_a_storage_tag')
    else: state['value'] = 3
    row = dict(batch_key='broken', report=dict(sim=dict(players=[dict(sim2gse_rule_observations=dict(
        state_observations=[state]))])))
    result_store.write('batches', 'broken', [row])
    expected = result_store.DataReadError if fault == 'version' else result_store.InvalidRecordError
    for read in (lambda: result_store.one('batches', 'batch_key', 'broken'),
                 lambda: result_store.read_records('batches', 'broken'),
                 lambda: result_store.read_many('batches', ['broken'])):
        with pytest.raises(expected, match='状态值存储') as caught: read()
        if fault == 'version': assert not isinstance(caught.value, result_store.InvalidRecordError)


@pytest.mark.parametrize('operation', ['and', 'or', 'not', 'select', 'any3', 'any3_fast', 'all3'])
def test_public_boolean_operators_keep_numeric_state_unknown(tmp_path, monkeypatch, operation):
    import sequence
    pack = _condition_pack()
    value = dict(var='row.value')
    expression = dict(op=operation, args={
        'and': [True, value], 'or': [False, value], 'not': [value], 'select': [value, True, False],
        'any3': [[value]], 'all3': [[value]],
        'any3_fast': [dict(op='map', args=[dict(var='scalar'), dict(var='member.value')], **{'as': 'member'})]
    }[operation])
    if operation == 'any3_fast': expression['op'] = 'any3'
    template = pack['general']['templates']['renamed-template']
    template.update(diagnose=dict(let=[], for_each=dict(var='scalar'), **{'as': 'row'}, cases=[
        dict(kind='true', when=expression, certainty='observed_fact'),
        dict(kind='false', when=dict(op='not', args=[expression]), certainty='observed_fact'),
        dict(kind='unknown', when=dict(op='unknown', args=[expression]), certainty='unknown')],
        export_trigger_records=[]), edits=[])
    pack['configurations'][0]['states']['only']['priority'] = pack['configurations'][0]['states']['only']['priority'][:1]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def zero_is_not_a_boolean(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:1]
        payload['state_observations'][0]['value'] = 0
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=zero_is_not_a_boolean):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    rule, = result['search']['rule_diagnostics']['rules']
    assert [row['kind'] for row in rule['findings']] == ['unknown']


def test_boolean_short_circuits_keep_proven_true_false_and_unknown_membership():
    from rule_diagnostics import Evaluation, UNKNOWN
    evaluator = Evaluation({}, {}, None, lambda: None, None, {})
    for expression, expected in [
        (dict(op='and', args=[False, 0]), False), (dict(op='or', args=[True, 0]), True),
        (dict(op='any3', args=[[True, 0]]), True), (dict(op='all3', args=[[False, 0]]), False),
        (dict(op='any3', args=[[False, 0]]), UNKNOWN), (dict(op='all3', args=[[True, 0]]), UNKNOWN),
        (dict(op='select', args=[True, True, dict(op='unsupported')]), True),
        (dict(op='select', args=[False, dict(op='unsupported'), False]), False)]:
        assert evaluator.value(expression, {}) is expected
    rows = evaluator.value(dict(op='filter', args=[[dict(value=0)], dict(var='row.value')], **{'as': 'row'}), {})
    assert evaluator.value(dict(op='empty', args=[dict(var='rows')]), dict(rows=rows)) is UNKNOWN


@pytest.mark.parametrize('representation,value,expected', [
    ('positive_stack_presence', 0, 'false'), ('positive_stack_presence', 1, 'true'),
    ('positive_stack_presence', None, 'unknown'), ('positive_stack_presence', -1, 'unknown'),
    ('positive_stack_presence', 1.5, 'unknown'), ('positive_stack_presence', True, 'unknown'),
    ('boolean', True, 'true'), ('boolean', False, 'false'), ('boolean', 1, 'unknown'),
    (None, 1, 'unknown')])
def test_public_maintenance_qualification_uses_declared_representation(tmp_path, monkeypatch, representation, value, expected):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    template = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['持续效果维护']
    declarations = template['diagnose']['let']
    end = next(index for index, row in enumerate(declarations) if row['name'] == 'player_rows') + 1
    qualified = dict(op='and', args=[True, dict(var='row.effect_qualification.value')])
    # 只展示真实模板已有的资格/同次关联阶段，后续实际事件区间仍未接通。
    template.update(diagnose=dict(let=declarations[:end], for_each=dict(var='player_rows'), **{'as': 'row'}, cases=[
        dict(kind='true', when=qualified, certainty='observed_fact'),
        dict(kind='false', when=dict(op='not', args=[qualified]), certainty='observed_fact'),
        dict(kind='unknown', when=dict(op='unknown', args=[qualified]), certainty='unknown')], export_trigger_records=[]), edits=[])
    objects = pack['object_sets']['sample']
    if representation is not None: objects['counter']['representation'] = representation
    objects.update(always=dict(kind='state', native_identity='literal.true', representation='boolean'),
        scope=dict(kind='target_scope', value='controlled_player'), owner=dict(kind='source', value='controlled_player'),
        effect=dict(kind='effect', native_identity='fixture_buff'))
    pack['general']['templates'] = {'qualification-renamed': template}
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='declared qualification',
        template='qualification-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect='effect', effect_qualification='counter', replacement_qualification='always', target_scope='scope', source='owner'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def typed_state(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:1]
        payload['state_observations'][0]['value'] = value
        payload['state_observations'].append(dict(payload['inputs'][0], object='always', value=True))
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=typed_state):
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    rule, = result['search']['rule_diagnostics']['rules']
    assert [row['kind'] for row in rule['findings']] == [expected]


@pytest.mark.parametrize('preceding', ['absent', 'known', 'unknown', 'coverage_unknown',
                                     'incomplete_inserted', 'empty', 'dynamic', 'unknown_state',
                                     'left_censored', 'empty_unidentified', 'linked_apply', 'unlinked_apply',
                                     'later_state', 'scoped_trigger', 'foreign_sample',
                                     'same_time_before', 'before_unknown_after_known', 'before_unknown_after_empty'])
def test_public_maintenance_reports_initial_gap_from_actual_buff_edges(tmp_path, monkeypatch, preceding):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'renamed-maintenance':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['持续效果维护']}
    pack['object_sets']['sample'].update(
        always=dict(kind='state', native_identity='literal.true', representation='boolean'),
        scope=dict(kind='target_scope', value='controlled_player'),
        owner=dict(kind='source', value='controlled_player'),
        effect=dict(kind='effect', native_identity='fixture_buff'))
    if preceding == 'dynamic': pack['object_sets']['sample']['scope']['value'] = 'current_attack_target'
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='actual maintenance gap',
        template='renamed-maintenance', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect='effect', effect_qualification='always', replacement_qualification='always',
            target_scope='scope', source='owner'))]
    if preceding == 'later_state':
        pack['object_sets']['sample']['switch'] = dict(kind='effect', native_identity='fixture_switch')
        pack['configurations'][0]['states']['only'].update(effect='switch', expected=True)
    if preceding == 'scoped_trigger':
        pack['general']['templates']['lower-template'] = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['条件触发与CD使用']
        pack['object_sets']['sample']['gate'] = dict(kind='state', native_identity='fixture_gate', representation='boolean')
        pack['configurations'][0]['states']['only']['priority'][0]['arguments']['replacement_qualification'] = 'gate'
        pack['configurations'][0]['states']['only']['priority'].append(dict(name='lower condition',
            template='lower-template', arguments=dict(action='consumer', priority_refs=['actual maintenance gap'],
                edit_range='editable', state='counter', compare='eq', value=1,
                activation_effect=None, activation_expected=True)))
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')

    def actual_buff_edges(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope'].update(end_ms=1000, controlled_actor_index=0, effect_events_complete={'effect': True})
        for name in ('inputs', 'action_observations'): payload[name] = payload[name][:4]
        for row in payload['inputs']:
            row.update(event_index=row['input_index'] * 10 + 1,
                       target_scopes={'scope': [dict(target_id=0, required=True)]})
        for row in payload['action_observations']: row['event_index'] = row['input_index'] * 10 + 1
        payload['state_observations'] = [dict(row, object='always', value=True) for row in payload['inputs']]
        if preceding == 'scoped_trigger':
            payload['state_observations'] += [dict(row, object='counter', value=int(row['input_index'] in (1, 2, 3)))
                                                for row in payload['inputs']]
            payload['state_observations'] += [dict(row, object='gate', value=row['input_index'] != 1)
                                                for row in payload['inputs']]
        payload['effect_observations'] = [dict(row, object='effect', target_id=0, source_id=0,
            component_id='fixture_buff', active=row['time'] > 400, applicable=True) for row in payload['inputs']]
        if preceding == 'later_state':
            payload['effect_observations'] += [dict(row, object='switch', active=row['time'] >= 600)
                                               for row in payload['inputs']]
        event = dict(object='effect', sample_id=1, effect_id='fixture_buff', instance_id=9,
            target_id=0, source_id=0, applicable=True, start=400, stacks=1, lifecycle_complete=True)
        payload['effect_events'] = [dict(event, kind='apply', time=400, event_index=25, end=None, end_reason=None),
            dict(event, kind='end', time=1000, event_index=50, end=1000, end_reason='simulation_end')]
        if preceding in ('known', 'unknown'):
            previous = dict(event, instance_id=8, start=0, lifecycle_complete=preceding == 'known')
            payload['effect_events'][:0] = [
                dict(previous, kind='start', time=0, event_index=0, end=None, end_reason=None),
                dict(previous, kind='expire', time=200, event_index=15, stacks=0, end=200, end_reason='expired')]
            for row in payload['effect_observations']:
                row['active'] = row['time'] < 200 or row['time'] > 400
        if preceding == 'coverage_unknown': payload['scope']['effect_events_complete']['effect'] = False
        if preceding == 'incomplete_inserted':
            possible = dict(event, instance_id=8, start=200, lifecycle_complete=False)
            payload['effect_events'][:0] = [
                dict(possible, kind='start', time=200, event_index=15, end=None, end_reason=None),
                dict(possible, kind='expire', time=300, event_index=20, stacks=0, end=300, end_reason='unknown')]
        if preceding == 'empty':
            payload['effect_events'] = []
            for row in payload['effect_observations']: row['active'] = False
        if preceding == 'unknown_state': payload['effect_events'][0]['stacks'] = None
        if preceding == 'left_censored':
            for row in payload['effect_events']: row.update(start=None, lifecycle_complete=False)
            previous = dict(event, instance_id=8, start=0)
            payload['effect_events'][:0] = [
                dict(previous, kind='start', time=0, event_index=2, end=None, end_reason=None),
                dict(previous, kind='expire', time=200, event_index=15, stacks=0, end=200, end_reason='expired')]
        if preceding == 'empty_unidentified':
            payload['effect_events'] = []
            for row in payload['effect_observations']: row['source_id'] = None
        if preceding in ('linked_apply', 'unlinked_apply', 'foreign_sample'):
            for row in payload['action_observations']:
                row.update(native_qualified=row['input_index'] == 2, success=row['input_index'] == 2,
                           effect_completion_time=400 if row['input_index'] == 2 else None)
            payload['effect_events'][0].update(source_input_index=None if preceding == 'unlinked_apply' else 2,
                                               source_actual_action='death_coil')
            # 点击快照不证明应用谱系，故刻意与实际事件是否有来源分开。
            payload['effect_observations'][2].update(applied=preceding == 'unlinked_apply', source_input_index=2)
        if preceding == 'foreign_sample':
            for row in payload['effect_events']: row['sample_id'] = 99
        if preceding == 'same_time_before':
            for row in payload['effect_events']: row['start'] = 600
            payload['effect_events'][0].update(time=600, event_index=50)
            payload['effect_events'][1]['event_index'] = 80
            previous = dict(event, instance_id=8, start=0)
            payload['effect_events'][:0] = [
                dict(previous, kind='start', time=0, event_index=0, end=None, end_reason=None),
                dict(previous, kind='refresh', time=400, event_index=25, end=None, end_reason=None,
                     source_input_index=2, source_actual_action='death_coil'),
                dict(previous, kind='expire', time=400, event_index=30, stacks=0, end=400, end_reason='expired')]
            for row in payload['effect_observations']: row['active'] = row['time'] <= 400
        if preceding in ('before_unknown_after_known', 'before_unknown_after_empty'):
            previous = dict(event, instance_id=8, start=0)
            payload['effect_events'][:0] = [
                dict(previous, kind='start', time=0, event_index=0, end=None, end_reason=None),
                dict(previous, kind='expire', time=200, event_index=15, stacks=0, end=200, end_reason='expired')]
            payload['effect_events'][2].update(source_input_index=2, source_actual_action='death_coil')
            for row in payload['effect_observations']: row['active'] = row['time'] <= 200 or row['time'] > 400
        if preceding in ('same_time_before', 'before_unknown_after_known', 'before_unknown_after_empty'):
            for row in payload['action_observations']:
                row.update(native_qualified=row['input_index'] in (
                    (0, 2) if preceding == 'before_unknown_after_known' else
                    (0,) if preceding == 'before_unknown_after_empty' else (2,)),
                    success=row['input_index'] == 2 and preceding != 'before_unknown_after_empty',
                    effect_completion_time=400 if row['input_index'] == 2 and preceding != 'before_unknown_after_empty' else None)
        if preceding in ('linked_apply', 'unlinked_apply', 'foreign_sample', 'same_time_before', 'before_unknown_after_known'):
            # 当前状态预计作用时间与已经发生的应用时刻独立提供，不能互相回填。
            payload['action_observations'][2].update(estimated_effect_completion_time=400,
                effect_completion_estimate=dict(effect_id='fixture_buff', target_id=0, source_id=0,
                    actual_form='death_coil', effect_delay_ms=0, precision='current_state_estimate'))
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=actual_buff_edges) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        saved = read_task(tmp_path / 'task')
    rule = saved['search']['rule_diagnostics']['rules'][0]
    kinds = [row['kind'] for row in rule['findings']]
    gaps = [row['gap'] for row in rule['findings'] if row['kind'] == (
        'effect_absence' if preceding == 'dynamic' else 'actual_coverage_gap')]
    expected = {'coverage_unknown': [], 'left_censored': [], 'empty_unidentified': [], 'later_state': [], 'foreign_sample': [],
                'same_time_before': [(400, 600, 50)], 'before_unknown_after_known': [(200, 400, 25)],
                'before_unknown_after_empty': [(200, 400, 25)],
                'incomplete_inserted': [(0, 200, 15), (300, 400, 25)],
                'empty': [(0, 1000, None)]}.get(preceding,
                   [(200 if preceding in ('known', 'unknown') else 0, 400, 25)])
    assert [(row['start'], row['end'], row.get('end_event_index')) for row in gaps] == expected
    if preceding in ('absent', 'empty', 'dynamic'): assert gaps[0]['preceding_interval'] == {}
    elif preceding == 'known':
        assert (gaps[0]['preceding_interval']['start'], gaps[0]['preceding_interval']['end']) == (0, 200)
    elif preceding == 'unknown': assert gaps[0]['preceding_interval'] is None
    if preceding == 'dynamic':
        assert 'actual_coverage_gap' not in kinds
        assert 'requirement_interval_unknown' in kinds
    if preceding in ('linked_apply', 'unlinked_apply'):
        assert ('covered' in kinds) is (preceding == 'linked_apply')
    if preceding == 'foreign_sample':
        assert 'covered' not in kinds
        assert rule['status'] == 'unknown' and '计分样本' in rule['reason']
    if preceding in ('same_time_before', 'before_unknown_after_known'):
        assert 'covered' in kinds
        assert 'no_opportunity' not in kinds
    if preceding == 'before_unknown_after_empty':
        assert 'unknown' in kinds and 'no_opportunity' not in kinds
    if preceding in ('coverage_unknown', 'incomplete_inserted', 'unknown_state', 'left_censored', 'empty_unidentified'):
        assert any(row['case'] == 'uncertain_context' for row in rule['unknown_conditions'])
    assert all(row['effect'] == dict(component_id='fixture_buff', target_id=0, source_id=0) for row in gaps)
    assert scoring.call_count == 1
    if preceding == 'scoped_trigger':
        lower = saved['search']['rule_diagnostics']['rules'][1]
        assert [(row['input_index'], row['kind']) for row in lower['findings'] if row['kind'] == 'missed_opportunity'] == [
            (1, 'missed_opportunity'), (3, 'missed_opportunity')]
        assert (2, 'yielded') not in [(row.get('input_index'), row['kind']) for row in lower['findings']]
        assert any(row.get('input_index') == 2 for row in lower['unknown_conditions'])
    else: assert result['search']['rule_diagnostics']['pool']['operations'] == []

@pytest.mark.parametrize('estimate_case', ['matching', 'wrong_effect', 'wrong_target', 'wrong_source', 'wrong_form',
    'wrong_precision', 'missing_time', 'missing_relation', 'missing_delay', 'negative_delay', 'boolean_time',
    'boolean_source', 'native_forbidden'])
def test_public_maintenance_uses_identity_bound_estimate_without_fabricating_actual_completion(tmp_path, monkeypatch, estimate_case):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'maintenance-estimate':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['持续效果维护']}
    pack['object_sets']['sample'].update(
        always=dict(kind='state', native_identity='literal.true', representation='boolean'),
        scope=dict(kind='target_scope', value='controlled_player'),
        owner=dict(kind='source', value='controlled_player'),
        effect=dict(kind='effect', native_identity='fixture_buff'))
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='estimated maintenance opportunity',
        template='maintenance-estimate', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect='effect', effect_qualification='always', replacement_qualification='always',
            target_scope='scope', source='owner'))]
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    observed = []

    def estimated_boundary(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope'].update(end_ms=1000, controlled_actor_index=0, effect_events_complete={'effect': True})
        for name in ('inputs', 'action_observations'): payload[name] = payload[name][:4]
        for row in payload['inputs']:
            row.update(event_index=row['input_index'] * 10 + 1,
                       target_scopes={'scope': [dict(target_id=0, required=True)]})
        payload['state_observations'] = [dict(row, object='always', value=True) for row in payload['inputs']]
        payload['effect_observations'] = [dict(row, object='effect', target_id=0, source_id=0,
            component_id='fixture_buff', active=row['time'] > 400, applicable=True) for row in payload['inputs']]
        event = dict(object='effect', sample_id=1, effect_id='fixture_buff', instance_id=9,
            target_id=0, source_id=0, applicable=True, start=400, stacks=1, lifecycle_complete=True)
        payload['effect_events'] = [dict(event, kind='apply', time=400, event_index=25, end=None, end_reason=None),
            dict(event, kind='end', time=1000, event_index=50, end=1000, end_reason='simulation_end')]
        for row in payload['action_observations']:
            row.update(native_qualified=False if row['input_index'] else None, has_cooldown=False,
                cooldown_remaining=0, charges_current=1, charges_maximum=1,
                resource_costs={}, known_native_requirements=[], effect_completion_time=None,
                occupancy_end=700, estimated_effect_completion_time=None, effect_completion_estimate=None)
        payload['action_observations'][0].update(estimated_effect_completion_time=0,
            effect_completion_estimate=dict(effect_id='fixture_buff', target_id=0, source_id=0,
                actual_form='death_coil', effect_delay_ms=0, precision='current_state_estimate'))
        action = payload['action_observations'][0]
        mutations = dict(wrong_effect=('effect_id', 'other_effect'), wrong_target=('target_id', 1),
            wrong_source=('source_id', 1), wrong_form=('actual_form', 'outbreak'),
            wrong_precision=('precision', 'native_static_estimate'), missing_delay=('effect_delay_ms', None),
            negative_delay=('effect_delay_ms', -1), boolean_source=('source_id', False))
        if estimate_case in mutations:
            field, value = mutations[estimate_case]
            action['effect_completion_estimate'][field] = value
        if estimate_case == 'missing_time': action['estimated_effect_completion_time'] = None
        if estimate_case == 'boolean_time': action['estimated_effect_completion_time'] = True
        if estimate_case == 'missing_relation': action['effect_completion_estimate'] = None
        if estimate_case == 'native_forbidden': action['native_qualified'] = False
        observed.append(copy.deepcopy(payload))
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=estimated_boundary) as scoring:
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        saved = read_task(tmp_path / 'task')
    diagnostic = saved['search']['rule_diagnostics']
    rule, = diagnostic['rules']
    if estimate_case != 'matching':
        assert diagnostic['pool']['operations'] == []
        assert all(row['kind'] != 'maintenance_opportunity' for row in rule['findings'])
        assert scoring.call_count == 1
        return
    assert any(row['kind'] == 'maintenance_opportunity' and row['input_index'] == 0 for row in rule['findings'])
    assert [(row['operation'], row['destination_path']) for row in diagnostic['pool']['operations']] == [
        ('move', [0]), ('insert', [0])]
    assert scoring.call_count == 1
    assert all(row['effect_completion_time'] is None for row in observed[0]['action_observations'])
    assert observed[0]['effect_events'][0].get('source_input_index') is None
