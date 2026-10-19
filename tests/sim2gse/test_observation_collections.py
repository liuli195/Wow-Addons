"""按冻结依赖采集事实；通过任务/外部引擎/恢复公开接缝验证。"""
import copy
import json
from unittest.mock import patch
import pytest

from task import run_task, read_task
from test_character_export import sample_profile
from test_engine import apl_pool_reference
from test_rule_diagnostics import _condition_pack, _observed_evaluate
from test_rule_initialization import _configure_opener


def test_public_task_collects_only_required_effect_rows_and_keeps_action_and_feedback_audits(tmp_path, monkeypatch):
    import sequence
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['object_sets']['sample'].update({
        'snapshot_only': dict(kind='effect', native_identity='fixture_gate'),
        'events_only': dict(kind='effect', native_identity='fixture_window'),
        'unused_effect': dict(kind='effect', native_identity='fixture_unused')})
    states = pack['configurations'][0]['states']['only']
    states['priority'][0]['arguments']['activation_effect'] = 'snapshot_only'
    pack['general']['templates']['renamed-window'] = copy.deepcopy(
        json.loads(DEFAULT_PATH.read_text())['general']['templates']['短期增益利用'])
    states['priority'].append(dict(name='window opportunity', template='renamed-window', arguments=dict(
        action='consumer', priority_refs=['supported opportunity', 'inactive condition'],
        edit_range='editable', effect_refs=['events_only'], usage_time_basis='execution',
        use_position='first_eligible', window_selection='earliest_end', consume_required=False)))
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    requests, borrowed = [], []

    def external_engine(*args, **kwargs):
        request = copy.deepcopy(kwargs['rule_observation_request'])
        requests.append(request)
        borrowed.append(kwargs['rule_observation_request'])
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        if request['protocol'] == 2:
            payload.update(protocol=2, request=request)
        return result

    from test_search import _apl_task_boundary
    destination = tmp_path / 'task'
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=external_engine):
        result = run_task(profile, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    saved = read_task(destination, include_search_records=True)
    request, = requests
    assert request['protocol'] == 2
    assert set(request['objects']) == {'consumer', 'counter', 'snapshot_only', 'events_only'}
    assert set(request['collections']['effect_observations']) == {'snapshot_only'}
    assert set(request['collections']['effect_events']) == {'events_only'}
    assert set(request['collections']['action_observations']) == {'consumer'}
    assert {'attempt', 'success', 'known_native_requirements'} <= set(
        request['collections']['action_observations']['consumer'])
    assert result['search']['rule_diagnostics'] == saved['search']['rule_diagnostics']
    assert result['rule_initialization']['rule_observation_request'] == request
    borrowed[0]['objects']['consumer']['native_action'] = 'external_caller_changed_its_copy'
    borrowed[0]['collections']['action_observations']['consumer'].append('external_field')
    assert result['rule_initialization']['rule_observation_request'] == request
    assert saved['rule_initialization']['rule_observation_request'] == request


def test_public_feedback_rejects_self_described_empty_request_instead_of_the_frozen_nonempty_request(tmp_path, monkeypatch):
    import sequence
    from test_search import _apl_task_boundary
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')

    def wrong_request(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['request']['objects'] = None
        payload['request']['collections'] = {name: None for name in payload['request']['collections']}
        payload['feedback_events'] = []
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=wrong_request):
        result = run_task(profile, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    batch = result['search']['records'][0]['batches'][0]
    assert batch['feedback_evidence']['availability'] == 'unavailable'
    assert all(row['status'] == 'unknown' for row in result['search']['rule_diagnostics']['rules'])


@pytest.mark.parametrize('source,fields', [
    ('student.action_events', ['kind']),
    ('student.future_facts', ['time']),
    ('student.action_observations', ['future_field']),
    ('student.target_scope', ['target_id'])])
def test_public_new_unrecognized_collection_dependency_freezes_a_full_v1_request(tmp_path, monkeypatch, source, fields):
    import sequence
    from test_search import _apl_task_boundary
    pack = _condition_pack()
    pack['general']['templates']['renamed-template']['reads'].append(dict(
        **{'as': 'additional_raw_facts', 'from': source}, object={'arg': 'action'}, fields=fields,
        same_run=True, on_declared_null_object='not_applicable_identity_rows'))
    if source == 'student.target_scope':
        pack['object_sets']['sample']['literal_scope'] = dict(kind='target_scope', value='controlled_player')
        # 输入衍生集合的对象表达式也必须识别；未识别时不能静默漏采该范围。
        pack['general']['templates']['renamed-template']['reads'][-1]['object'] = 'literal_scope'
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    requests = []

    def external_engine(*args, **kwargs):
        requests.append(copy.deepcopy(kwargs['rule_observation_request']))
        return _observed_evaluate(*args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=external_engine):
        result = run_task(profile, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    request, = requests
    assert request['protocol'] == 1 and 'collections' not in request
    assert set(request['objects']) == set(pack['object_sets']['sample'])
    assert result['rule_initialization']['rule_observation_request'] == request


@pytest.mark.parametrize('fault', ['legacy_response', 'missing_request', 'extra_coverage'])
def test_public_protocol_or_coverage_mismatch_never_creates_supported_findings(tmp_path, monkeypatch, fault):
    import sequence
    from test_search import _apl_task_boundary
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')

    def malformed_response(*args, **kwargs):
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        if fault == 'legacy_response': payload['protocol'] = 1
        elif fault == 'missing_request': payload.pop('request')
        else: payload['scope']['effect_events_complete']['unrequested_effect'] = True
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=malformed_response):
        result = run_task(profile, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    diagnosis = result['search']['rule_diagnostics']
    assert all(row['status'] == 'unknown' and row['findings'] == [] for row in diagnosis['rules'])
    assert diagnosis['pool']['operations'] == []


@pytest.mark.parametrize('frozen', ['legacy_without_request', 'existing_v2', 'unknown_protocol', 'null_request'])
def test_public_resume_uses_the_actual_frozen_request_and_rejects_unknown_protocol(tmp_path, monkeypatch, frozen):
    import sequence
    from runtime import TaskCancelled
    from search import TaskStore
    from task import TaskError, resume_task
    from test_search import _apl_task_boundary
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    profile, destination = tmp_path / 'role.simc', tmp_path / 'task'
    profile.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=TaskCancelled('before first score')):
        stopped = run_task(profile, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
    assert stopped['status'] == 'cancelled'
    store = TaskStore(destination)
    try:
        initialization = store.state['rule_initialization']
        original = copy.deepcopy(initialization['rule_observation_request'])
        if frozen == 'legacy_without_request': initialization.pop('rule_observation_request')
        elif frozen == 'unknown_protocol': initialization['rule_observation_request']['protocol'] = 99
        elif frozen == 'null_request': initialization['rule_observation_request'] = None
        store.save()
    finally:
        store.close()
    requests = []

    def external_engine(*args, **kwargs):
        requests.append(copy.deepcopy(kwargs['rule_observation_request']))
        return _observed_evaluate(*args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=external_engine):
        if frozen in ('unknown_protocol', 'null_request'):
            with pytest.raises(TaskError, match='冻结规则观察请求'):
                resume_task(destination)
            assert requests == []
            return
        resumed = resume_task(destination)
    assert requests
    if frozen == 'legacy_without_request':
        assert all(row == dict(protocol=1, objects=original['objects']) for row in requests)
        assert 'rule_observation_request' not in resumed['rule_initialization']
    else:
        assert all(row == original for row in requests)
        assert resumed['rule_initialization']['rule_observation_request'] == original
