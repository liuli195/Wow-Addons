"""同次外部引擎证据经公开任务入口交付诊断与合法操作。"""
import copy
import json
from unittest.mock import patch
import pytest

from task import TaskError, read_task, resume_task, run_task
from test_character_export import sample_profile
from test_engine import apl_pool_reference
from test_rule_initialization import _configure_opener, _opener_pack
from test_search import _apl_task_boundary, _fast_evaluate, _initialized_starts


def test_public_search_keeps_intermediate_results_in_memory_until_user_pause(
        tmp_path, monkeypatch, installed_data_store_api):
    """界面的启动/取消/读取/继续接口共用真实选择器与隔离结果中心。"""
    from collections import Counter
    import threading
    import sequence
    import result_store
    import selector
    from task import cancel_task, start_task

    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    destination = tmp_path / 'task'
    ready_to_pause = threading.Event()
    completed_scores = []
    premature_publications = []
    active_runtime = None
    ordinary_requests = 0
    interrupted_once = False
    real_write = installed_data_store_api['write']

    def write(root, table, key, rows, **kwargs):
        # 外部存储边界；小进度摘要和引擎必要交换文件不属报告/模型发布。
        if active_runtime is not None and not active_runtime.cancel_event.is_set():
            if table in ('search_learners', 'search_learner_controls') or (
                    table == 'batches' and any(row.get('purpose') in
                        ('search', 'diagnostic', 'validation') for row in rows)):
                premature_publications.append((table, key))
        return real_write(root, table, key, rows, **kwargs)

    def evaluate(*args, **kwargs):
        nonlocal active_runtime, ordinary_requests, interrupted_once
        active_runtime = kwargs['runtime']
        observed = kwargs.get('rule_observation_request') is not None
        if not observed:
            ordinary_requests += 1
            # 四个起点和第一个已选择子候选完成后，由公开取消接口暂停。
            if ordinary_requests == 6 and not interrupted_once:
                interrupted_once = True
                ready_to_pause.set()
                assert active_runtime.cancel_event.wait(20), '公开取消信号未送达外部评分边界'
                active_runtime.check()
        result = (_observed_evaluate if observed else _fast_evaluate)(*args, **kwargs, score=100.0)
        # 与真实引擎相同，完整报告只写入本次既有native.json交换文件。
        (args[2] / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        if not observed:
            completed_scores.append((
                tuple(tuple(command['simc_action'] for command in block) for block in args[1]['blocks']),
                kwargs['seed'], kwargs['iterations']))
        return result

    monkeypatch.setitem(installed_data_store_api, 'write', write)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=evaluate):
        handle = start_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(total_budget_seconds=60, input_interval_ms=200,
                candidate_limit=6, round_candidate_limit=1, max_processes=1,
                batch_targets=(2,), iterations=2, validation_batches=1))
        try:
            assert ready_to_pause.wait(20), f'搜索未到主动暂停接缝: {handle.error!r}'
            live = read_task(destination)
            assert live['status'] == 'running' and live['elapsed_seconds'] > 0
            # 在用户暂停前固定观测，恢复后的正常结束不计入计算期发布。
            computing_publications = list(premature_publications)
            cancel_task(handle)
            handle.join(10)
            assert handle.done and handle.error is None, repr(handle.error)
            paused = read_task(destination, include_search_records=True)
            assert paused['status'] == 'cancelled'
            assert len(paused['search']['records']) == 5
            learned, = [step['selection'] for step in paused['search']['rule_steps'].values()
                        if step.get('selection', {}).get('feedback', {}).get('status') == 'learned']
            assert len(learned['context']) == 50 and len(learned['action_features']) == 21
            assert 0 < learned['probability'] <= 1 and learned['feedback']['reward'] == 0
            shared = result_store.read_search_learner(selector.MODEL_KEY)
            assert shared['settled'][paused['run_id']] >= learned['decision_id']
            completed_before_resume = Counter(completed_scores)
            before_records = {row['key']: row['score'] for row in paused['search']['records']}
            for record in paused['search']['records']:
                for receipt in record['batches'] + record.get('diagnostic_batches', []):
                    report = result_store.one('batches', 'batch_key', receipt['data_key'])
                    assert report is not None and report['dps'] == receipt['dps']

            resume_task(destination)
            resumed = read_task(destination, include_search_records=True)
            assert resumed['status'] == 'completed' and len(resumed['search']['records']) == 6
            assert before_records.items() <= {
                row['key']: row['score'] for row in resumed['search']['records']}.items()
            completed_after_resume = Counter(completed_scores)
            assert all(completed_after_resume[key] == count
                       for key, count in completed_before_resume.items())
            same_decision, = [step['selection'] for step in resumed['search']['rule_steps'].values()
                             if step.get('selection', {}).get('decision_id') == learned['decision_id']]
            assert same_decision['feedback'] == learned['feedback']
            assert computing_publications == [], (
                '无全局晋升的计算期不应发布报告或共享模型', computing_publications)
        finally:
            if not handle.done:
                cancel_task(handle)
                handle.join(10)


def test_public_on_demand_parent_replays_separately_before_real_selection(tmp_path, monkeypatch):
    import sequence, search
    scoped = []
    original_store = search.TaskStore

    class CheckedStore(original_store):
        def save(self, **changes):
            with self.lock:
                super().save(**changes)
                if changes.get('fields') is not None and not self.report_buffer:
                    assert self.load_state(self.db) == json.loads(json.dumps(self.state))
                    scoped.append(changes)

    monkeypatch.setattr(search, 'TaskStore', CheckedStore)
    from result_store import one
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    requests = []

    def scoring(*args, **kwargs):
        requests.append(dict(seed=kwargs['seed'], iterations=kwargs['iterations'],
                             observed=kwargs.get('rule_observation_request') is not None))
        return (_observed_evaluate if requests[-1]['observed'] else _fast_evaluate)(*args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=scoring) as calls:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
                               batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task', include_search_records=True)
        before = calls.call_count
        resumed = resume_task(tmp_path / 'task')
        assert calls.call_count == before
    assert sum(row['observed'] for row in requests) == 1
    assert saved['search']['candidate_count'] == 5
    assert saved['search']['native_batch_starts_total'] == len(requests)
    step, = [row for row in saved['search']['rule_steps'].values() if row.get('selection')]
    parent = next(row for row in saved['search']['records'] if row['key'] == step['parent_candidate_key'])
    child = next(row for row in saved['search']['records'] if row['key'] == step['candidate_key'])
    assert parent['rule_diagnostic_status'] == 'complete'
    assert child['rule_diagnostic_status'] == 'not_diagnosed'
    selection = step['selection']
    assert len(selection['context']) == 50 and len(selection['action_features']) == 21
    assert 0 < selection['probability'] <= 1
    assert step['request']['parent_identity'] == parent['rule_diagnostics']['parent_identity']
    assert any(row['operation_id'] == step['request']['operation_id']
               for row in parent['rule_diagnostics']['pool']['operations'])
    assert child['rule_step']['request'] == step['request']
    diagnostic_batch, = parent['diagnostic_batches']
    score_batch, = parent['batches']
    assert diagnostic_batch['data_key'] != score_batch['data_key']
    assert parent['rule_diagnostic_source'] == dict(kind='on_demand_replay',
        scoring_batch_key=score_batch['data_key'], diagnostic_batch_key=diagnostic_batch['data_key'])
    assert parent['rule_diagnostics']['evidence']['batch_key'] == diagnostic_batch['data_key']
    assert diagnostic_batch['request']['source_scoring_batch_key'] == score_batch['data_key']
    assert diagnostic_batch['request']['iterations'] == score_batch['request']['iterations'] == 2
    assert diagnostic_batch['dps'] == score_batch['dps']
    diagnostic = parent['rule_diagnostics']
    assert diagnostic['evidence']['kind'] == 'on_demand_replay'
    assert diagnostic['evidence']['source_scoring_batch_key'] == score_batch['data_key']
    assert diagnostic['parent_identity'] == __import__('search').digest(diagnostic['parent'])
    assert {name: value for name, value in diagnostic_batch['request'].items()
            if name not in ('purpose', 'source_scoring_batch_key', 'rule_observations')} == {
            name: value for name, value in score_batch['request'].items() if name != 'purpose'}
    feedback = step['selection']['feedback']
    assert feedback['status'] == 'learned'
    assert feedback['common_batches'] == 1
    assert feedback['evidence'][0]['parent_batch'] == score_batch['data_key']
    assert feedback['reward'] == pytest.approx((child['score'] - parent['score']) / parent['score'])
    assert resumed['search_result'] == result['search_result']
    # Ordinary and observation reports share the real typed storage/restore boundary.
    ordinary = one('batches', 'batch_key', score_batch['data_key'])
    observed = one('batches', 'batch_key', diagnostic_batch['data_key'])
    assert ordinary['rule_observations'] is None
    assert observed['rule_observations'] is not None
    assert 'rule_observations' not in score_batch['request']
    assert ordinary['report']['sim']['players'][0].get('sim2gse_rule_observations') is None

    assert result['status'] == saved['status'] == 'completed'
    assert saved['selected_candidate_key'] == result['selected_candidate_key']
    assert scoped
    saved_fields = set().union(*(row['fields'] for row in scoped))
    assert {'selection_feedback_intents', 'selection_feedback_incomplete', 'pending',
            'rule_steps', 'selection_generation'} <= saved_fields
    import result_store, selector
    snapshot = result_store.read_search_learner(selector.MODEL_KEY)
    control = result_store.read_search_learner_control(selector.MODEL_KEY)
    assert snapshot['state_version'] == 3
    assert snapshot['matrix_format'] == 'f64-le-v1'
    assert snapshot['dimension'] == 1072
    assert isinstance(snapshot['theta_bytes'], bytes) and len(snapshot['theta_bytes']) == 8576
    assert isinstance(snapshot['a_inv_bytes'], bytes) and len(snapshot['a_inv_bytes']) == 9193472
    assert snapshot['theta'] is None and snapshot['a_inv'] is None
    assert not {'theta', 'a_inv', 'theta_bytes', 'a_inv_bytes', 'matrix_format'} & control.keys()



@pytest.mark.parametrize('different', ['dps', 'samples', 'variance'])
def test_public_on_demand_mismatch_preserves_scores_and_never_selects(tmp_path, monkeypatch, different):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    observations, scores = [], []

    def scoring(*args, **kwargs):
        observed = kwargs.get('rule_observation_request') is not None
        result = (_observed_evaluate if observed else _fast_evaluate)(*args, **kwargs)
        if not observed:
            statistics = result['report']['sim']['players'][0]['collected_data']['dps']
            scores.append(dict(result['summary'], variance=statistics['variance']))
        if observed:
            observations.append(result)
            player = result['report']['sim']['players'][0]
            if different == 'dps':
                result['summary']['dps'] += 1
                player['collected_data']['dps']['mean'] += 1
            elif different == 'samples':
                result['summary']['samples'] += 1
                player['collected_data']['dps']['count'] += 1
            else:
                player['collected_data']['dps']['variance'] += 1
        return result

    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=scoring):
        with pytest.raises(TaskError, match='原评分成绩不一致'):
            run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=dict(input_interval_ms=200, candidate_limit=2, round_candidate_limit=1,
                                   batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    assert len(observations) == 1
    assert not saved['search'].get('rule_steps')
    parent, = [row for row in saved['search']['records'] if row['rule_diagnostic_status'] == 'mismatch']
    original, = parent['batches']
    capture, = parent['diagnostic_batches']
    assert len(scores) == 1
    assert {field: original[field] for field in ('dps', 'samples', 'variance')} == scores[0]
    assert parent['score'] == original['dps']
    assert parent.get('rule_diagnostics') is None
    assert capture[different] != original[different]
    assert saved['search']['candidate_count'] == 1



def test_public_on_demand_cancelled_capture_reuses_published_report_without_sweeping(tmp_path, monkeypatch):
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    captures = []

    def scoring(*args, **kwargs):
        observed = kwargs.get('rule_observation_request') is not None
        result = (_observed_evaluate if observed else _fast_evaluate)(*args, **kwargs)
        if observed:
            captures.append(kwargs['seed'])
            if len(captures) == 1:
                kwargs['runtime'].cancel()
        return result

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=scoring) as calls:
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=5, round_candidate_limit=1,
                               batch_targets=(2,), iterations=2, validation_batches=1))
        stopped = read_task(tmp_path / 'task', include_search_records=True)
        assert stopped['status'] == 'cancelled'
        parent, = [row for row in stopped['search']['records'] if row.get('diagnostic_batches')]
        assert parent['rule_diagnostic_status'] == 'incomplete'
        assert sum(row['rule_diagnostic_status'] == 'not_diagnosed' for row in stopped['search']['records']) == 3
        before = calls.call_count
        read_task(tmp_path / 'task', include_search_records=True, include_reports=True)
        assert calls.call_count == before
        resume_task(tmp_path / 'task')
        saved = read_task(tmp_path / 'task', include_search_records=True)
    assert len(captures) == 1
    assert saved['status'] == 'completed'
    restored = next(row for row in saved['search']['records'] if row['key'] == parent['key'])
    assert restored['rule_diagnostic_status'] == 'complete'
    assert restored['diagnostic_batches'][0]['data_key'] == parent['diagnostic_batches'][0]['data_key']
    assert restored['batches'] == parent['batches']
    assert sum(row['rule_diagnostic_status'] == 'not_diagnosed' for row in saved['search']['records']) == 4
    assert len(restored['rule_diagnostics']['selection_context']['values']) == 50



def test_public_manual_diagnosis_requires_explicit_budget_and_preserves_finished_task(tmp_path, monkeypatch):
    import sequence
    import sqlite3
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    destination = tmp_path / 'task'
    captures, requests = [], []

    def scoring(*args, **kwargs):
        requests.append(kwargs.get('rule_observation_request'))
        observed = requests[-1] is not None
        if observed: captures.append(kwargs['seed'])
        return (_observed_evaluate if observed else _fast_evaluate)(*args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=scoring) as calls:
        original = run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=2, batch_targets=(2,), iterations=2,
                               diagnostic_logging=False))
        count = calls.call_count
        before = read_task(destination, include_search_records=True, include_reports=True)
        assert calls.call_count == count
        assert original['config']['rule_diagnostics_policy'] == 'on_demand'
        assert requests and all(request is None for request in requests)
        assert original['status'] == before['status'] == 'completed'
        assert before['candidate']['text'] == original['candidate']['text']
        assert len(before['search']['records']) == 2
        assert before['search']['rule_diagnostic_status'] == 'not_diagnosed'
        for record in [*original['search']['records'], *before['search']['records']]:
            assert record['rule_diagnostic_status'] == 'not_diagnosed'
            assert record.get('rule_diagnostics') is None
            assert all('rule_observations' not in batch['request'] for batch in record['batches'])
        key = before['selected_candidate_key']
        for budget in (None, 0, -1, True, float('inf')):
            with pytest.raises(TaskError, match='diagnostic_budget_seconds'):
                resume_task(destination, diagnostic_candidate_key=key, diagnostic_budget_seconds=budget)
        assert not captures
        # Emulate a recovered task whose original budget was fully consumed.
        with sqlite3.connect(destination / 'task.sqlite3') as database:
            database.execute("UPDATE state_fields SET value='600.0' WHERE key='elapsed_seconds'")
            database.execute('UPDATE runtime_progress SET elapsed=600.0')
        from result_store import one, write, RUN_SCHEMA
        published = one('runs', 'run_id', before['run_id'])
        published = {name: json.loads(value) if RUN_SCHEMA.get(name) == 'JSON' and isinstance(value, str)
                     else value for name, value in published.items()}
        published['elapsed_seconds'] = 600.0
        write('runs', before['run_id'], [published], schema=RUN_SCHEMA)
        before = read_task(destination, include_search_records=True)
        result = resume_task(destination, diagnostic_candidate_key=key, diagnostic_budget_seconds=10)
        after = read_task(destination, include_search_records=True)
        count = calls.call_count
        resume_task(destination, diagnostic_candidate_key=key, diagnostic_budget_seconds=10)
        assert calls.call_count == count
    assert len(captures) == 1
    assert result['status'] == after['status'] == before['status'] == 'completed'
    assert after['elapsed_seconds'] == before['elapsed_seconds'] == 600.0
    assert after['config'] == before['config']
    assert after['search_result'] == before['search_result']
    assert after['candidate'] == before['candidate']
    for name in ('candidate_count', 'unique_candidates', 'rounds', 'native_batch_starts_total'):
        assert after['search'][name] == before['search'][name]
    assert after['completed_batches'] == before['completed_batches']
    assert after['search']['rule_diagnostic_status'] == 'complete'
    assert len(after['search']['rule_diagnostics']['selection_context']['values']) == 50
    diagnosed = next(row for row in after['search']['records'] if row['key'] == key)
    assert diagnosed['rule_diagnostic_status'] == 'complete'
    assert len(diagnosed['diagnostic_batches']) == 1
    assert sum(row['rule_diagnostic_status'] == 'not_diagnosed' for row in after['search']['records']) == 1
    operation = after['search']['diagnostic_operations'][key]
    assert operation['budget_seconds'] == 10
    assert 0 < operation['elapsed_seconds'] <= 10
    assert operation['native_batch_starts'] == 1



def test_public_old_missing_policy_preserves_eager_identity_and_refuses_policy_change(tmp_path, monkeypatch):
    import search
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    original_config_for = search.config_for

    def legacy_configuration(values=None, **kwargs):
        config = original_config_for(values, **kwargs)
        config.pop('rule_diagnostics_policy', None)
        return config

    # Materialize the old public task/config shape, with real task identity and storage.
    cancelled, requests = [], []
    def observed(*args, **kwargs):
        requests.append((kwargs['seed'], tuple(tuple(row['simc_action'] for row in block) for block in args[1]['blocks'])))
        result = _observed_evaluate(*args, **kwargs)
        if not cancelled:
            cancelled.append(True)
            kwargs['runtime'].cancel()
        return result
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=observed) as calls:
        with patch.object(search, 'config_for', side_effect=legacy_configuration):
            result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=dict(input_interval_ms=200, candidate_limit=2, batch_targets=(2,), iterations=2))
        assert 'rule_diagnostics_policy' not in result['config']
        assert result['search']['rule_diagnostic_status'] == ('incomplete')
        count = calls.call_count
        resumed = resume_task(tmp_path / 'task')
        assert count == 1
        assert requests.count(requests[0]) == 1
        assert 'rule_diagnostics_policy' not in resumed['config']
        assert resumed['status'] == 'completed'
        restored = read_task(tmp_path / 'task', include_search_records=True)
        assert restored['search']['records'][0]['batches'][0]['data_key'] == result['search']['records'][0]['batches'][0]['data_key']
        assert all('diagnostic_batches' not in row for row in restored['search']['records'])
        after = calls.call_count
        with pytest.raises(TaskError, match='恢复配置发生变化'):
            resume_task(tmp_path / 'task', search_config=dict(result['config'], rule_diagnostics_policy='on_demand'))
        assert calls.call_count == after



def test_public_on_demand_capture_publication_recovery_never_recaptures_or_relearns(tmp_path, monkeypatch):
    import result_store
    import sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    captures, interrupted = [], []
    def scoring(*args, **kwargs):
        observed = kwargs.get('rule_observation_request') is not None
        if observed: captures.append(kwargs['seed'])
        return (_observed_evaluate if observed else _fast_evaluate)(*args, **kwargs)
    original_write = result_store.write
    def after_durable_capture(table, key, rows, **kwargs):
        result = original_write(table, key, rows, **kwargs)
        if table == 'batches' and any(row.get('purpose') == 'diagnostic' for row in rows) and not interrupted:
            interrupted.append(True)
            raise PermissionError('constructed capture published before checkpoint')
        return result
    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=scoring) as calls:
        with patch.object(result_store, 'write', side_effect=after_durable_capture):
            with pytest.raises(TaskError, match='capture published before checkpoint'):
                run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                    search_config=dict(input_interval_ms=200, candidate_limit=2, round_candidate_limit=1,
                                       batch_targets=(2,), iterations=2))
        resume_task(tmp_path / 'task')
        saved = read_task(tmp_path / 'task', include_search_records=True)
        before = calls.call_count
        resume_task(tmp_path / 'task')
        assert calls.call_count == before
    assert interrupted == [True] and len(captures) == 1
    assert calls.call_count == 3
    assert saved['status'] == 'completed'
    assert saved['search']['candidate_count'] == 2
    steps = [row for row in saved['search']['rule_steps'].values() if row.get('selection')]
    assert len(steps) == 1 and steps[0]['selection']['feedback']['status'] == 'learned'
    parent = next(row for row in saved['search']['records'] if row['key'] == steps[0]['parent_candidate_key'])
    assert parent['rule_diagnostic_status'] == 'complete'
    assert parent['rule_diagnostics']['evidence']['batch_key'] == parent['diagnostic_batches'][0]['data_key']



def test_public_manual_capture_preserves_burst_and_full_frozen_request_on_read(tmp_path, monkeypatch):
    import burst, result_store, sequence
    from test_burst import reviewed_fixture, character_seed_boundary
    from search import digest
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    result_store.DATA_ROOT.mkdir()
    definition, profile = reviewed_fixture()
    burst.publish(definition)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(profile, encoding='utf-8')
    requests = []
    def scoring(*args, **kwargs):
        sources = kwargs.pop('input_sources', None)
        kwargs.pop('burst_candidate', None)
        requests.append(dict(seed=kwargs['seed'], input_times=kwargs['input_times'],
                             iterations=kwargs['iterations'], sources=sources))
        observed = kwargs.get('rule_observation_request') is not None
        result = (_observed_evaluate if observed else _fast_evaluate)(*args, **kwargs)
        if observed:
            payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
            for name in ('inputs', 'action_observations', 'state_observations'):
                for row, source_name in zip(payload[name], sources, strict=True): row['input_source'] = source_name
        return result
    with character_seed_boundary(native_reference=native), patch.object(sequence, 'evaluate', side_effect=scoring) as calls:
        original = run_task(source, tmp_path / 'task', use_burst=True,
            simulation_config=dict(scene='single_target'), search_config=dict(input_interval_ms=200,
                candidate_limit=1, batch_targets=(2,), iterations=2))
        key = original['selected_candidate_key']
        resume_task(tmp_path / 'task', diagnostic_candidate_key=key, diagnostic_budget_seconds=10)
        saved = read_task(tmp_path / 'task', include_search_records=True)
        assert calls.call_count == 2
    assert requests[0] == requests[1]
    record, = saved['search']['records']
    scored, = record['batches']
    capture, = record['diagnostic_batches']
    original_scored = original['search']['records'][0]['batches'][0]
    assert scored['request'] == original_scored['request']
    assert capture['request']['burst'] == scored['request']['burst']
    assert digest(scored['request']) == scored['data_key']
    assert digest(capture['request']) == capture['data_key']
    assert saved['search_result'] == original['search_result']



def test_public_manual_diagnosis_uses_invocation_logging_and_preserves_original_trace(tmp_path, monkeypatch):
    import result_store, sequence
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    destination = tmp_path / 'task'
    traces = []
    def scoring(*args, **kwargs):
        traces.append(kwargs['trace'])
        result = (_observed_evaluate if kwargs.get('rule_observation_request') is not None
                  else _fast_evaluate)(*args, **kwargs)
        if kwargs['trace']:
            result['report']['sim']['players'][0]['collected_data']['action_sequence'] = result['trace']
        return result
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=scoring):
        original = run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2,
                               diagnostic_logging=True, trace_search=True))
        original = read_task(destination)
        old_log = (destination / 'diagnostics.json').read_bytes()
        key = original['selected_candidate_key']
        result = resume_task(destination, diagnostic_candidate_key=key, diagnostic_budget_seconds=10,
                             diagnostic_logging=False)
        saved = read_task(destination, include_search_records=True)
    assert traces == [True, True]
    assert result['config'] == saved['config'] == original['config']
    assert saved['elapsed_seconds'] == original['elapsed_seconds']
    record, = saved['search']['records']
    capture, = record['diagnostic_batches']
    assert capture['request']['trace'] is True
    assert ('costs' in record['rule_diagnostics']) is False
    stored = result_store.one('batches', 'batch_key', capture['data_key'])
    assert ('action_sequence' in stored['report']['sim']['players'][0]['collected_data']) is (False)
    assert (destination / 'diagnostics.json').read_bytes() == old_log
    trace_rows = list(result_store.iter_rows('SELECT batch_key FROM traces', tables=['traces'])) if (result_store.DATA_ROOT / 'traces').exists() else []
    assert any(row['batch_key'] == capture['data_key'] for row in trace_rows) is (False)



def _task_clock_offset(monkeypatch):
    """只推进任务预算/恢复记账，不改变标准time或存储锁的时钟。"""
    import runtime, search, task, time
    from types import SimpleNamespace
    offset = [0.0]
    clock = SimpleNamespace(**dict(vars(time), monotonic=lambda: time.monotonic() + offset[0]))
    for module in (runtime, search, task):
        monkeypatch.setattr(module, 'time', clock)
    return offset


def test_public_manual_diagnosis_accounts_publication_and_retry_time_separately(tmp_path, monkeypatch):
    import result_store, sequence
    offset = _task_clock_offset(monkeypatch)
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    destination = tmp_path / 'task'
    def scoring(*args, **kwargs):
        return (_observed_evaluate if kwargs.get('rule_observation_request') is not None
                else _fast_evaluate)(*args, **kwargs)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=scoring) as calls:
        run_task(source, destination, simulation_config=dict(scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        original = read_task(destination)
        key = original['selected_candidate_key']
        real_write = result_store.write
        delayed, delay_next, failed = [], [True], []
        def delayed_publication(table, logical_key, rows, **kwargs):
            if table == 'runs' and delay_next[0]:
                delay_next[0] = False
                metrics = rows[0]['search_metrics']
                if isinstance(metrics, str): metrics = json.loads(metrics)
                delayed.append(metrics['diagnostic_operations'][key]['elapsed_seconds'])
                offset[0] += 0.15
                if not failed:
                    failed.append(True)
                    raise PermissionError('constructed delayed publication failure')
            return real_write(table, logical_key, rows, **kwargs)
        with patch.object(result_store, 'write', side_effect=delayed_publication):
            with pytest.raises((TaskError, PermissionError), match='delayed publication failure'):
                resume_task(destination, diagnostic_candidate_key=key, diagnostic_budget_seconds=10)
            delay_next[0] = True
            result = resume_task(destination, diagnostic_candidate_key=key, diagnostic_budget_seconds=10)
        saved = read_task(destination, include_search_records=True)
        assert calls.call_count == 2
    assert result['search']['rule_diagnostic_status'] == saved['search']['rule_diagnostic_status'] == 'complete'
    assert saved['search']['records'][0]['rule_diagnostic_status'] == 'complete'
    operation = saved['search']['diagnostic_operations'][key]
    assert operation['elapsed_seconds'] >= delayed[-1] + 0.12
    assert operation['native_batch_starts'] == 1
    assert saved['elapsed_seconds'] == original['elapsed_seconds'] == result['elapsed_seconds']
    assert saved['search_result'] == original['search_result']



def test_public_on_demand_restores_declared_state_order_for_full_pool_and_features(tmp_path, monkeypatch):
    import sequence, selector
    pack = _condition_pack()
    state = pack['configurations'][0]['states'].pop('only')
    pack['configurations'][0]['states'] = {'z_first': state, 'a_second': copy.deepcopy(state),
                                         'empty': dict(effect=None, expected=True, priority=[])}
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    def scoring(*args, **kwargs):
        return (_observed_evaluate if kwargs.get('rule_observation_request') is not None
                else _fast_evaluate)(*args, **kwargs)
    config = dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=scoring):
        original = run_task(source, tmp_path / 'B', simulation_config=dict(scene='single_target'), search_config=config)
        resumed = resume_task(tmp_path / 'B', diagnostic_candidate_key=original['selected_candidate_key'],
                              diagnostic_budget_seconds=10)
    left = resumed['search']['rule_diagnostics']
    # 右侧从原始声明和独立原报告重新诊断，不读取左侧的恢复诊断/响应。
    right = _direct_diagnosis(tmp_path / 'eager', copy.deepcopy(pack), copy.deepcopy(native),
                              include_context=True)
    assert [row['state'] for row in left['rules']] == [row['state'] for row in right['rules']] == [
        'z_first', 'z_first', 'a_second', 'a_second']
    assert left['pool']['complete'] is right['pool']['complete'] is True
    assert [[item['state'] for item in operation['contributors']] for operation in left['pool']['operations']] == [
        [item['state'] for item in operation['contributors']] for operation in right['pool']['operations']]
    assert left['selection_context'] == right['selection_context']
    program = original['search']['records'][0]['program']
    assert selector.action_features(left, program, left['pool']['operations']) == selector.action_features(
        right, program, right['pool']['operations'])


def _eager_search_config(**values):
    return dict(rule_diagnostics_policy='eager', **values)


def _assert_pending_selector_receipts(receipts):
    import result_store
    from selector import MODEL_KEY

    with result_store.search_learner_lock():
        full = result_store.read_search_learner(MODEL_KEY)
        control = result_store.read_search_learner_control(MODEL_KEY)
    assert control['phase'] == 'active'
    assert control['base_version'] == full['version'] < control['version']
    assert sorted(control['reservations'], key=lambda row: row['decision_id']) == sorted(
        receipts, key=lambda row: row['decision_id'])


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


def _observation_payload(input_times, request=None):
    inputs = [dict(input_index=i, time=ms, sample_id=1, event_index=i,
                   source_step=i % 2, input_source='loop')
              for i, ms in enumerate(input_times)]
    payload = dict(
        protocol=1, scope=dict(sample_selection='first_scored_complete', sample_id=1,
            start_ms=0, end_ms=180000, complete=True), inputs=inputs,
        action_observations=[dict(row, object='consumer', native_qualified=True,
            input_allowed=True, actual_form='death_coil', base_button='death_coil',
            attempt=False, success=False, earliest_execute=row['time'],
            occupancy_start=row['time'], occupancy_end=row['time'] + 200,
            occupancy_domains=['player_gcd'], target_id=1) for row in inputs],
        state_observations=[dict(row, object='counter', value=1 if row['input_index'] == 0 else 0)
                            for row in inputs], effect_observations=[])
    if request is not None and request['protocol'] == 2:
        payload.update(protocol=2, request=copy.deepcopy(request))
        payload['scope']['effect_events_complete'] = {
            name: False for name in request['collections']['effect_events']}
    return payload


def _observed_evaluate(*args, **kwargs):
    """仅替换已存在的外部引擎边界，不替换解释器或编辑器。"""
    request = kwargs.pop('rule_observation_request', None)
    result = _fast_evaluate(*args, **kwargs)
    result['report']['sim']['players'][0]['sim2gse_rule_observations'] = _observation_payload(
        result['input_times'], request)
    return result


def _diagnostic_initialization(tmp_path, pack, native):
    """真实目录、声明校验和冻结初始化；不建立任务或评分存储。"""
    import engine, rule_config, rule_initialization
    from search import digest
    capabilities = engine.inspect(native, tmp_path / 'catalogue')
    snapshot = dict(pack=copy.deepcopy(pack), resolved=rule_config.validate(pack),
                    rule_config_digest=digest(pack))
    binding = rule_config.bind(capabilities, native['static_snapshot'], 1,
        spec_id=native['identity']['spec_id'], rule_snapshot=snapshot, scene='single_target')
    initialization = rule_initialization.generate(capabilities, native, binding=binding,
        input_interval_ms=200, rule_snapshot=snapshot)
    return capabilities, initialization


def _direct_diagnosis(tmp_path, pack, native, mutate=None, *, iterations=2,
                      input_times=None, batch_request=None, include_context=False):
    """独立报告与权威请求交给公开diagnose；每个参数仍独立执行。"""
    from rule_diagnostics import diagnose
    from runtime import TaskRuntime
    capabilities, initialization = _diagnostic_initialization(tmp_path, pack, native)
    times = list(range(0, 180000, 200)) if input_times is None else list(input_times)
    request = copy.deepcopy(initialization['rule_observation_request'])
    evidence = dict(input_times=times, report=dict(sim=dict(players=[dict(
        sim2gse_rule_observations=_observation_payload(times, request))])))
    if batch_request is None:
        batch_request = dict(times=times, rule_observations=dict(request=copy.deepcopy(request)))
    else:
        batch_request = copy.deepcopy(batch_request)
        batch_request['rule_observations'] = dict(request=copy.deepcopy(request))
    if mutate is not None:
        mutate(evidence)
    diagnosis = diagnose(initialization['program'], capabilities, initialization, evidence['report'],
        task_run_id='fixture', batch_key='same-batch',
        behavior_identity=initialization['behavior_identity'], runtime=TaskRuntime(),
        requested_iterations=iterations, batch_request=batch_request)
    if include_context:
        from selector import context_features, FEATURE_VERSION
        resolved = next(row for row in initialization['rule_snapshot']['resolved']
                        if row['key'] == initialization['configuration_key'])
        diagnosis['selection_context'] = dict(version=FEATURE_VERSION, values=context_features(
            diagnosis, evidence['report']['sim']['players'][0]['sim2gse_rule_observations'],
            objects=resolved['objects']))
    return diagnosis


def test_public_task_exposes_same_batch_complete_diagnostics_and_legal_pool(tmp_path, monkeypatch):
    import sequence
    import rule_diagnostics
    def no_performance_clock():
        raise AssertionError('关闭性能诊断时不应额外计时')
    monkeypatch.setattr(rule_diagnostics.time, 'perf_counter', no_performance_clock)
    pack = _condition_pack()
    _configure_opener(tmp_path, monkeypatch, pack)
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=_observed_evaluate) as scoring:
        result = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=_eager_search_config(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1, diagnostic_logging=False))
        saved = read_task(tmp_path / 'task', include_search_records=True)
        diagnosis = result['search']['records'][0]['rule_diagnostics']
        with pytest.raises(TaskError, match='候选预算'):
            resume_task(tmp_path / 'task', rule_step=dict(parent_identity=diagnosis['parent_identity'],
                operation_id=diagnosis['pool']['operations'][0]['operation_id']))
    assert scoring.call_count == 1
    diagnosis = result['search']['records'][0]['rule_diagnostics']
    assert diagnosis == saved['search']['rule_diagnostics']
    assert diagnosis == saved['search']['records'][0]['rule_diagnostics']
    assert ('costs' in diagnosis) is False
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


@pytest.mark.parametrize('representation', ['legacy_equal', 'bad_parent'])
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
            search_config=_eager_search_config(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2))
        before = read_task(destination, include_search_records=True)
        with sqlite3.connect(destination / 'task.sqlite3') as database:
            key, payload = database.execute('SELECT key,value FROM state_archive').fetchone()
            physical = json.loads(payload)
            canonical = physical['batches'][0]['rule_diagnostics']
            if representation.startswith('legacy'):
                physical.pop('rule_diagnostics_ref')
                physical['rule_diagnostics'] = copy.deepcopy(canonical)

            else:
                physical['rule_diagnostics_ref']['parent_identity'] = 'foreign-parent'
            database.execute('UPDATE state_archive SET value=? WHERE key=?', (json.dumps(physical), key))
        if representation.startswith('legacy'):
            resume_task(destination)
            with sqlite3.connect(destination / 'task.sqlite3') as database:
                restored, = TaskStore.load_state(database)['archive']
            assert restored['rule_diagnostics'] == canonical
            assert restored['rule_diagnostics'] is restored['batches'][0]['rule_diagnostics']
            assert read_task(destination, include_search_records=True)['search']['rule_diagnostics'] == before['search']['rule_diagnostics']
        else:
            with pytest.raises(ValueError, match='诊断引用'): resume_task(destination)
            with sqlite3.connect(destination / 'task.sqlite3') as database:
                assert json.loads(database.execute('SELECT value FROM state_archive WHERE key=?', (key,)).fetchone()[0]) == physical
    assert scoring.call_count == 1


@pytest.mark.parametrize('qualification', ['resource_blocked', 'supported', 'missing_fact'])
def test_public_supported_hypothesis_keeps_known_negative_requirements_false(tmp_path, monkeypatch, qualification):
    pack = _condition_pack()
    high = pack['configurations'][0]['states']['only']['priority'][0]
    high['name'] = 'higher opportunity'
    low = copy.deepcopy(high)
    low.update(name='ordinary lower')
    low['arguments'].update(action='first', priority_refs=['higher opportunity'])
    pack['configurations'][0]['states']['only']['priority'] = [high, low]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def partial_qualification(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for row in payload['action_observations']:
            row.update(native_qualified=None, has_cooldown=True, cooldown_remaining=0,
                charges_current=0, resource_costs={}, resource_balances={}, known_native_requirements=[])

            if qualification == 'resource_blocked':
                row.update(resource_costs={'mana': 2}, resource_balances={'mana': 1})

            if qualification == 'missing_fact': row.update(cooldown_remaining=None, charges_current=None)

        payload['action_observations'] += [dict(row, object='first', actual_form='outbreak',
            base_button='outbreak', native_qualified=True, cooldown_remaining=0,
            resource_costs={}, resource_balances={}, known_native_requirements=[])
            for row in payload['action_observations']]
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, partial_qualification)
    diagnostic = diagnosis
    higher, lower = diagnostic['rules']
    higher_kinds = {row['kind'] for row in higher['findings']}
    lower_kinds = {row['kind'] for row in lower['findings']}
    contributors = {row['rule'] for operation in diagnostic['pool']['operations'] for row in operation['contributors']}
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
    pack = _condition_pack()
    higher, lower = pack['configurations'][0]['states']['only']['priority']
    lower['arguments'].update(action='first', value=1, priority_refs=[higher['name']])
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def unmapped_first_input(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['inputs'][0].update(input_source='precombat')
        for row in payload['state_observations']:
            row['value'] = 1 if row['input_index'] in (0, 2) else 0
        payload['action_observations'] += [dict(row, object='first', actual_form='outbreak',
            base_button='outbreak') for row in payload['action_observations']]
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, unmapped_first_input)
    diagnostic = diagnosis
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
            if len(normal_requests) == 2:
                raise TaskCancelled('constructed external boundary before selected score')
        return _observed_evaluate(*args, **kwargs)

    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=cancel_once):
        stopped = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=_eager_search_config(input_interval_ms=200, candidate_limit=2, round_candidate_limit=1,
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
    assert step['status'] == 'scored' and after['search']['candidate_count'] == 2
    assert after['status'] == 'completed' and after['search']['stop_reason'] == 'candidate_limit'
    assert len(normal_requests) == 3
    assert normal_requests[-1] == normal_requests[-2]


def test_public_budget_end_learns_completed_pending_common_batches_without_more_scores(tmp_path, monkeypatch, installed_data_store_api):
    import search
    import result_store
    from selector import MODEL_KEY
    import sequence
    from test_search import _initialized_starts
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
            if len(requests) == 3:
                kwargs['runtime'].used_seconds = kwargs['runtime'].budget_seconds
        return result

    real_runtime = search.TaskRuntime
    cleanup_calls = []
    def expired_cleanup(total, **kwargs):
        cleanup_calls.append(total)
        return real_runtime(total, used_seconds=total, **kwargs)
    monkeypatch.setattr(search, 'TaskRuntime', expired_cleanup)
    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=finish_at_budget):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=_eager_search_config(total_budget_seconds=60, input_interval_ms=200, candidate_limit=3,
                round_candidate_limit=2, max_processes=1, batch_targets=(2,), iterations=2,
                validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',)))
        saved = read_task(tmp_path / 'task', include_search_records=True)
    selections = [step['selection'] for step in saved['search']['rule_steps'].values() if step.get('selection')]
    assert len(selections) == 2 and len(requests) == 3
    checkpoint = search.TaskStore(tmp_path / 'task')
    try:
        assert cleanup_calls == [30]
        assert checkpoint.state['selection_feedback_incomplete'] is True
        assert len(checkpoint.state['selection_feedback_intents']) == 2
        assert all(intent['common_batches'] == 1 for intent in checkpoint.state['selection_feedback_intents'].values())
        frozen_receipts = [intent['receipt'] for intent in checkpoint.state['selection_feedback_intents'].values()]
    finally:
        checkpoint.close()
    _assert_pending_selector_receipts(frozen_receipts)
    assert saved['search']['selection_feedback_incomplete'] is True
    monkeypatch.setattr(search, 'TaskRuntime', real_runtime)
    published_before = result_store.one('runs', 'run_id', saved['run_id'])
    real_write = installed_data_store_api['write']
    publish_failed = False
    def fail_result_once(root, table, key, rows, **kwargs):
        nonlocal publish_failed
        if table == 'runs' and not publish_failed:
            publish_failed = True
            raise PermissionError('constructed completed-result publication failure')
        return real_write(root, table, key, rows, **kwargs)
    monkeypatch.setitem(installed_data_store_api, 'write', fail_result_once)
    real_save = search.TaskStore.save
    def save_complete_flag_with_intents(store, **changes):
        result = real_save(store, **changes)
        persisted = search.TaskStore.load_state(store.db)
        if not persisted.get('selection_feedback_intents'):
            assert not persisted.get('selection_feedback_incomplete'), '空intent与complete标记必须同次保存'
        return result
    monkeypatch.setattr(search.TaskStore, 'save', save_complete_flag_with_intents)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=AssertionError('预算耗尽不能补评分')):
        with pytest.raises(PermissionError, match='completed-result'):
            resume_task(tmp_path / 'task')
        committed = result_store.read_search_learner(MODEL_KEY)
        resume_task(tmp_path / 'task')
    again = read_task(tmp_path / 'task', include_search_records=True)

    assert all(step['selection']['feedback']['status'] == 'learned'
               for step in again['search']['rule_steps'].values())
    assert result_store.read_search_learner(MODEL_KEY)['reservations'] == []
    assert result_store.read_search_learner(MODEL_KEY) == committed
    assert again['search']['selection_feedback_incomplete'] is False
    published_after = result_store.one('runs', 'run_id', saved['run_id'])
    for name in published_before.keys() - {'search_metrics', 'elapsed_seconds'}:
        assert published_after[name] == published_before[name]


def test_public_selector_recovers_process_exit_after_shared_publish(tmp_path, monkeypatch):
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
    api = result_store._api()
    real_write = api['write']
    interrupted = False
    normal_requests = []

    def published_then_exit(root, table, key, rows, **kwargs):
        nonlocal interrupted
        result = real_write(root, table, key, rows, **kwargs)
        if table == 'search_learners' and not interrupted and rows[0]['version'] == 2:
            interrupted = True
            raise SystemExit('constructed process exit after real shared atomic replacement')
        return result

    def observed(*args, **kwargs):
        if kwargs.get('rule_observation_request') is not None:
            normal_requests.append(args[1]['blocks'])
        return _observed_evaluate(*args, **kwargs)

    monkeypatch.setitem(api, 'write', published_then_exit)
    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=observed):
        with pytest.raises(SystemExit, match='after real shared'):
            run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=_eager_search_config(input_interval_ms=200, candidate_limit=2, round_candidate_limit=1,
                    batch_targets=(2,), iterations=2, validation_batches=1,
                    final_batches=1, final_iterations=2, scenarios=('nominal',)))
        before = result_store.read_search_learner(MODEL_KEY)
        requests_before = len(normal_requests)
        assert interrupted and requests_before == 2
        checkpoint = TaskStore(tmp_path / 'task')
        try:
            used_before = checkpoint.state['elapsed_seconds']
        finally:
            checkpoint.close()
        external = TaskRuntime(600)
        external_started = external.started
        resume_task(tmp_path / 'task', _runtime=external)
        assert abs(external.elapsed_seconds - (used_before + time.monotonic()-external_started)) < .02
        saved = read_task(tmp_path / 'task', include_search_records=True)
    step = next(step for step in saved['search']['rule_steps'].values() if step.get('selection'))
    assert step['selection']['feedback']['status'] == 'learned'
    assert result_store.read_search_learner(MODEL_KEY)['version'] == 2
    assert result_store.read_search_learner(MODEL_KEY) == before
    assert len(normal_requests) == requests_before


def test_public_budget_recovery_freezes_remaining_pending_after_partial_freeze_exit(tmp_path, monkeypatch):
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
            if len(requests) == 3:
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
    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=completed_at_budget):
        with pytest.raises(SystemExit, match='halfway'):
            run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=_eager_search_config(total_budget_seconds=60, input_interval_ms=200, candidate_limit=3,
                    round_candidate_limit=2, max_processes=1, batch_targets=(2,), iterations=2,
                    validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',)))
    assert exited
    checkpoint = search.TaskStore(tmp_path / 'task')
    try:
        assert len(checkpoint.state['selection_feedback_intents']) == 1
        assert len(checkpoint.state['pending']) == 2
    finally:
        checkpoint.close()
    monkeypatch.setattr(search, 'freeze_selection_feedback', real_freeze)
    cancellation = threading.Event()
    cancellation.set()
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=AssertionError('预算恢复不能增加评分')):
        resume_task(tmp_path / 'task', cancel_event=cancellation)
        checkpoint = search.TaskStore(tmp_path / 'task')
        try:
            assert len(checkpoint.state['selection_feedback_intents']) == 2
            assert checkpoint.state['selection_feedback_incomplete'] is True
            frozen_receipts = [intent['receipt'] for intent in checkpoint.state['selection_feedback_intents'].values()]
        finally:
            checkpoint.close()
        _assert_pending_selector_receipts(frozen_receipts)
        cancellation.clear()
        resume_task(tmp_path / 'task', cancel_event=cancellation)
    assert len(requests) == 3
    assert result_store.read_search_learner(MODEL_KEY)['reservations'] == []
    saved = read_task(tmp_path / 'task', include_search_records=True)
    assert len(saved['search']['rule_steps']) == 2
    assert all(step['selection']['feedback']['status'] == 'learned'
               for step in saved['search']['rule_steps'].values())


def test_public_feedback_recovery_time_exhausts_budget_before_any_new_score(tmp_path, monkeypatch):
    offset = _task_clock_offset(monkeypatch)
    import sequence, result_store
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    api = result_store._api()
    real_write, real_read = api['write'], api['read_key']
    active_runtime = None
    interrupted = False
    delayed = False
    score_calls = 0

    def publish_then_exit(root, table, key, rows, **kwargs):
        nonlocal interrupted
        result = real_write(root, table, key, rows, **kwargs)
        if table == 'search_learners' and rows[0]['settled'] and not interrupted:
            interrupted = True
            offset[0] += max(0.0, active_runtime.remaining_seconds - 1.0)
            raise SystemExit('constructed exit with one second of task budget left')
        return result

    def delayed_read(root, table, key, **kwargs):
        nonlocal delayed
        if table == 'search_learners' and interrupted and not delayed:
            delayed = True
            offset[0] += 1.2  # 真read_key边界推进时钟，仍由原TaskRuntime记账。
        return real_read(root, table, key, **kwargs)

    def observed(*args, **kwargs):
        nonlocal active_runtime, score_calls
        score_calls += 1
        active_runtime = kwargs['runtime']
        return _observed_evaluate(*args, **kwargs)

    monkeypatch.setitem(api, 'write', publish_then_exit)
    with _apl_task_boundary(native), _initialized_starts([[['outbreak'], ['death_coil']]]), \
            patch.object(sequence, 'evaluate', side_effect=observed):
        with pytest.raises(SystemExit, match='one second'):
            run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
                search_config=_eager_search_config(total_budget_seconds=30, input_interval_ms=200, candidate_limit=3,
                    round_candidate_limit=2, max_processes=1, batch_targets=(2,), iterations=2, validation_batches=1,
                    final_batches=1, final_iterations=2, scenarios=('nominal',)))
    assert interrupted and score_calls == 3
    from search import TaskStore
    checkpoint = TaskStore(tmp_path / 'task')
    try:
        used_before_recovery = checkpoint.state['elapsed_seconds']
        checkpoint.state.update(status='running', inflight={})
        checkpoint.save()  # A process can exit before its running marker is cleared.
    finally:
        checkpoint.close()
    monkeypatch.setitem(api, 'read_key', delayed_read)
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
    def save_acknowledged_elapsed(store, **changes):
        result = original_save(store, **changes)
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


def test_public_resume_scores_one_requested_operation_and_keeps_pending_starts(tmp_path, monkeypatch):
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
            search_config=_eager_search_config(input_interval_ms=200, candidate_limit=3, batch_targets=(2,),
                               iterations=2, validation_batches=1, diagnostic_logging=True,
                               search_observability='summary'))
        assert stopped['status'] == 'cancelled'
        diagnosis = read_task(tmp_path / 'task')['search']['rule_diagnostics']
        operation = next(row for row in diagnosis['pool']['operations'] if row['operation'] == 'insert')
        request = dict(parent_identity=diagnosis['parent_identity'], operation_id=operation['operation_id'])
        with pytest.raises(TaskError, match='父身份'):
            resume_task(tmp_path / 'task', diagnostic_logging=True, rule_step=dict(request, parent_identity='foreign-parent'))
        resumed = resume_task(tmp_path / 'task', diagnostic_logging=True, rule_step=request)
        saved = read_task(tmp_path / 'task', include_search_records=True)
        again = resume_task(tmp_path / 'task', diagnostic_logging=True, rule_step=request)
    changed = next(row for row in resumed['search']['records'] if row.get('rule_step'))
    expected = [['death_coil'], ['outbreak']] + ([['death_coil']])
    assert changed['program'] == expected
    assert changed['rule_step']['request'] == request
    assert changed['rule_step']['parent_score'] > 0
    assert changed['score'] > 0
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
    pack = _condition_pack()
    pack['object_sets']['sample']['switch'] = dict(kind='effect', native_identity='fixture_switch')
    active = pack['configurations'][0]['states'].pop('only')
    active.update(effect='switch', expected=False)
    inactive = copy.deepcopy(active)
    inactive['expected'] = True
    pack['configurations'][0]['states'] = {'inactive': inactive, 'active': active}
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def switched_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['effect_observations'] = [dict(row, object='switch', active=False) for row in payload['inputs']]
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, switched_engine)
    assert len(diagnosis['rules']) == 4
    assert [(row['state'], row['status']) for row in diagnosis['rules']] == [
        ('inactive', 'not_applicable'), ('inactive', 'not_applicable'),
        ('active', 'diagnosed'), ('active', 'not_applicable')]
    assert all(c['state'] == 'active' for op in diagnosis['pool']['operations'] for c in op['contributors'])


def test_public_unknown_execution_is_not_reported_as_inactive_or_failed(tmp_path, monkeypatch):
    pack = _condition_pack()
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def missing_outcomes(result):
        for row in result['report']['sim']['players'][0]['sim2gse_rule_observations']['action_observations']:
            row.update(native_qualified=None, success=None, has_cooldown=False,
                       resource_costs={'rune': 0}, resource_balances={'rune': 6}, known_native_requirements=[])
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, missing_outcomes)
    assert diagnosis['rules'][0]['status'] == 'unknown'
    assert {row['case'] for row in diagnosis['rules'][0]['unknown_conditions']} == {'covered', 'missed_opportunity'}
    assert diagnosis['rules'][0]['findings'] == []
    assert diagnosis['pool']['operations'] == []


@pytest.mark.parametrize('iterations,sample_id,supported', [(2, 0, False), (1, 1, True)])
def test_public_diagnostics_use_actual_scored_sample_not_warmup(tmp_path, monkeypatch, iterations, sample_id, supported):
    pack = _condition_pack()
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def selected_sample(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['sample_id'] = sample_id
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in payload[name]: row['sample_id'] = sample_id
        return result

    # 原task的首评分批由batch_targets=(2,)决定，config.iterations=1也实际请求2场。
    diagnosis = _direct_diagnosis(tmp_path, pack, native, selected_sample, iterations=2)
    assert bool(diagnosis['pool']['operations']) is supported
    if not supported:
        assert all(row['status'] == 'unknown' for row in diagnosis['rules'])
        assert '计分样本' in diagnosis['rules'][0]['reason']


def test_public_window_template_uses_configured_effect_without_enabling_full_charge_branch(tmp_path, monkeypatch):
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'another-name': json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['Buff窗口与充能使用']}
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_window')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='window use', template='another-name',
        arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
                       window_effect='window', allow_full_charge=False))]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def window_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['effect_observations'] = [dict(row, object='window', active=row['input_index'] == 0)
                                          for row in payload['inputs']]
        for row in payload['action_observations']: row.update(charges_current=2, charges_maximum=2)
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, window_engine)
    assert [(finding['kind'], finding.get('input_index')) for finding in diagnosis['rules'][0]['findings']] == [('missed_window', 0)]
    assert len(diagnosis['pool']['operations']) == 2


def test_public_pool_respects_configured_edit_unit_range(tmp_path, monkeypatch):
    pack = _condition_pack()
    pack['object_sets']['sample']['editable']['allow_units'] = ['wait_block']
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    diagnosis = _direct_diagnosis(tmp_path, pack, native)
    assert diagnosis['rules'][0]['findings'][0]['kind'] == 'missed_opportunity'
    assert diagnosis['pool']['complete'] is True
    assert diagnosis['pool']['operations'] == []
    assert diagnosis['pool']['empty_reason'] == 'no_supported_legal_operation'
    assert diagnosis['pool']['rejections']['edit_unit_not_allowed'] == 2


def test_public_resource_template_uses_configured_native_resource_identity(tmp_path, monkeypatch):
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'resource-template-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['资源近满与溢出处理']}
    pack['object_sets']['sample']['tank'] = dict(kind='resource', native_identity='runic_power')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='spend before overflow',
        template='resource-template-renamed', arguments=dict(action='consumer', priority_refs=[],
            edit_range='editable', resource='tank', margin_source='native_cost', near_full_margin=None))]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def resource_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['resource_events'] = [dict(row, object='tank', current=95 if row['input_index'] == 0 else 0,
            maximum=100, overflow=0) for row in payload['inputs']]
        for row in payload['action_observations']:
            row.update(resource_costs={'runic_power': 10}, resource_balances={'runic_power': 95})
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, resource_engine)
    assert [(row['kind'], row.get('input_index')) for row in diagnosis['rules'][0]['findings']] == [
        ('near_full_opportunity', 0)]
    assert len(diagnosis['pool']['operations']) == 2


def test_public_reservation_template_enumerates_all_later_positions(tmp_path, monkeypatch):
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
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def reservation_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in payload[name]: row['source_step'] = row['input_index'] % 3
        payload['resource_events'] = [dict(row, object='tank', before=40, after=20,
            actual_delta=-20) for row in payload['inputs']]
        payload['effect_observations'] = [dict(row, object='reserve', active=row['input_index'] == 1)
            for row in payload['inputs']]
        for row in payload['action_observations']: row['success'] = row['input_index'] == 1
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, reservation_engine)
    assert [(row['kind'], row.get('input_index')) for row in diagnosis['rules'][0]['findings']] == [
        ('reservation_crowding_hypothesis', 1)]
    assert [(row['operation'], row['source_path'], row['destination_path'])
        for row in diagnosis['pool']['operations']] == [('move', [1], [3])]


@pytest.mark.parametrize('scope_case', ['known', 'missing_component_key'])
def test_public_join_keeps_target_components_and_missing_effect_unknown(tmp_path, monkeypatch, scope_case):
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
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def component_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['inputs'] = payload['inputs'][:1]
        row = payload['inputs'][0]
        row['target_scopes'] = dict(scope=[dict(target_id=target, required=True) for target in (1, 2)])
        row['target_scope_sources'] = dict(scope='sim.target_non_sleeping_list')

        payload['state_observations'] = payload['state_observations'][:1]
        payload['action_observations'] = [dict(payload['action_observations'][0], target_id=999)]
        payload['effect_observations'] = [dict(row, object='effect', target_id=target,
            component_id='dot', applicable=True, active=True if target == 1 else None) for target in (1, 2)]
        if scope_case == 'missing_component_key': payload['effect_observations'][0].pop('target_id')

        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, component_engine)
    rule, = diagnosis['rules']
    if scope_case == 'missing_component_key':
        assert rule['status'] == 'unknown'
        assert '关联键缺失' in rule['reason']
        assert diagnosis['pool']['operations'] == []
        return

    findings = rule['findings']
    assert [row for row in findings if row['input_index'] == 0] == [
        dict(kind='joined', certainty='observed_fact', input_index=0, target=1,
             component='dot', action_target=999, active=True, applicable=True),
        dict(kind='joined', certainty='observed_fact', input_index=0, target=2,
             component='dot', action_target=999, active=None, applicable=True)]


@pytest.mark.parametrize('missing_input_source', [False, 'scoped_unknown'])
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
    if missing_input_source == 'scoped_unknown':
        pack['general']['templates']['lower-template'] = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['条件触发与CD使用']
        pack['object_sets']['sample']['low_counter'] = dict(kind='state', native_identity='fixture_low_counter')
        pack['configurations'][0]['states']['only']['priority'].append(dict(name='after final anchor',
            template='lower-template', arguments=dict(action='consumer', priority_refs=['prepare before anchor'],
                edit_range='editable', state='low_counter', compare='eq', value=1,
                activation_effect=None, activation_expected=True)))

    definition, profile = reviewed_fixture()
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def preparation_engine(*args, **kwargs):
        sources = kwargs.pop('input_sources')
        kwargs.pop('burst_candidate')
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row, input_source in zip(payload[name], sources, strict=True): row['input_source'] = input_source
        for row in payload['state_observations']: row['value'] = 1
        for row in payload['action_observations']: row['input_allowed'] = row['input_source'] == 'loop'
        return result

    if missing_input_source == 'scoped_unknown':
        times, sources = burst.combined_inputs(list(range(0, 180000, 200)), definition, 200)

        def scoped_unknown_report(result):
            payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
            for name in ('inputs', 'action_observations', 'state_observations'):
                for row, input_source in zip(payload[name], sources, strict=True):
                    row['input_source'] = input_source
            for row in payload['state_observations']: row['value'] = 1
            for row in payload['action_observations']: row['input_allowed'] = row['input_source'] == 'loop'
            for row in payload['inputs']: row.pop('input_source')
            payload['state_observations'] += [dict(row, object='low_counter', value=int(index == len(payload['inputs'])-1))
                for index, row in enumerate(payload['inputs'])]

        diagnosis = _direct_diagnosis(tmp_path, pack, native, scoped_unknown_report,
            input_times=times, batch_request=dict(times=times, burst=dict(sources=sources)))
        lower = diagnosis['rules'][1]
        assert [(row['input_index'], row['kind']) for row in lower['findings'] if row['kind'] == 'missed_opportunity'] == [
            (len(times)-1, 'missed_opportunity')]
        return

    _configure_opener(tmp_path, monkeypatch, pack)
    result_store.DATA_ROOT.mkdir()
    burst.publish(definition)
    source = tmp_path / 'role.simc'
    source.write_text(profile, encoding='utf-8')
    with character_seed_boundary(native_reference=native), patch.object(sequence, 'evaluate', side_effect=preparation_engine) as scoring:
        result = run_task(source, tmp_path / 'task', use_burst=True, simulation_config=dict(scene='single_target'),
            search_config=_eager_search_config(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                               iterations=2, validation_batches=1))
    diagnosis = result['search']['rule_diagnostics']
    assert scoring.call_count == 1
    findings = diagnosis['rules'][0]['findings']
    assert [(row['kind'], row.get('anchor')) for row in findings] == [
        ('missed_preparation', 3000), ('missed_preparation', 48000),
        ('missed_preparation', 93000), ('missed_preparation', 138000)]
    assert diagnosis['pool']['operations']
    assert all(row['certainty'] == 'hypothesis' for row in findings)


@pytest.mark.parametrize('lifecycle_complete', [True, False])
def test_public_short_window_uses_real_instance_bounds_and_keeps_missing_lifecycle_unknown(tmp_path, monkeypatch, lifecycle_complete):
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'short-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']}
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_short_buff')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='use short effect',
        template='short-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect_refs=['window'], window_selection='earliest_end', use_position='first_eligible', consume_required=True, usage_time_basis='effect_completion'))]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def window_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for row in payload['action_observations']:
            row['effect_completion_time'] = row['time']
            row['event_index'] += 1
        event = dict(object='window', sample_id=1, effect_id='fixture_short_buff', instance_id=1,
            target_id=0, source_id=0, applicable=True, start=0, end=400)
        event['lifecycle_complete'] = lifecycle_complete
        payload['effect_events'] = [dict(event, event_index=0, kind='start', time=0, end_reason=None),
            dict(event, event_index=10001, kind='expire', time=400, end_reason='expired')]
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, window_engine)
    if lifecycle_complete is not True:
        assert diagnosis['rules'][0]['status'] == 'unknown'
        assert diagnosis['pool']['operations'] == []
    else:
        assert [(row['kind'], row.get('input_index')) for row in diagnosis['rules'][0]['findings']] == [
            ('missed_short_window', 0), ('expired_unused', None)]
        assert len(diagnosis['pool']['operations']) == 2
        assert diagnosis['rules'][0]['findings'][0]['window']['instance_id'] == 1


@pytest.mark.parametrize('case', ['opportunity', 'input_inside_execution_after', 'missing_execution'])
def test_public_short_window_execution_basis_separates_estimate_and_actual_use(tmp_path, monkeypatch, case):
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'short-renamed':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']}
    pack['object_sets']['sample']['window'] = dict(kind='effect', native_identity='fixture_short_buff')
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='execute during window',
        template='short-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect_refs=['window'], window_selection='earliest_end', use_position='first_eligible',
            consume_required=False, usage_time_basis='execution'))]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def window_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['effect_events_complete'] = {'window': True}
        payload['scope']['execution_events_complete'] = False
        for name in ('inputs', 'action_observations', 'state_observations'):
            payload[name] = payload[name][:3]
        for row in payload['action_observations']:
            row.update(effect_completion_time=None, event_index=row['input_index'] * 10 + 5,
                earliest_execute=row['time'], cast_ms=0, channel_ms=0,
                timing_precision='current_state_estimate', occupancy_end=row['time'] + 1000)

        if case == 'missing_execution': payload['action_observations'][1]['success'] = None

        event = dict(object='window', sample_id=1, effect_id='fixture_short_buff', instance_id=1,
            target_id=0, source_id=0, applicable=True, start=200, lifecycle_complete=True)
        payload['effect_events'] = [dict(event, event_index=10, kind='start', time=200, end=None, end_reason=None),
            dict(event, event_index=100, kind='expire', time=600, end=600, end_reason='expired')]
        execution = (1, 800, 110, 'death_coil') if case == 'input_inside_execution_after' else None
        payload['action_events'] = [] if execution is None else [dict(
            object='consumer', sample_id=1, input_index=execution[0], time=execution[1],
            event_index=execution[2], kind='execute', success=True, actual_form=execution[3], target_id=1)]

        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, window_engine)
    kinds = {row['kind'] for row in diagnosis['rules'][0]['findings']}
    if case == 'missing_execution':
        assert 'expired_unused' not in kinds
        assert 'covered' not in kinds
    else:
        assert 'missed_short_window' in kinds or 'covered' in kinds
        assert diagnosis['pool']['operations']
        assert 'covered' not in kinds
        assert 'utilized_off_selected_position' not in kinds
        assert 'expired_unused' in kinds


def test_diagnostic_interface_enumerates_every_intermediate_gap_and_keeps_loop_repeats(tmp_path, monkeypatch):
    """真实诊断、单操作和编译接口；不另建外围评分任务。"""
    from program import canonicalize_search_program, compile_program
    from rule_diagnostics import apply, diagnose
    from runtime import TaskRuntime
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    capabilities, initialization = _diagnostic_initialization(tmp_path, _condition_pack(), native)
    blocks = [['outbreak'], ['outbreak'], ['outbreak'], ['death_coil']]
    program = [dict(kind='Loop', count=3, blocks=blocks)]
    canonical = canonicalize_search_program(program, capabilities)
    # 复用原外部Lua进程边界；Program编译、编辑、合法性均真实。
    with _apl_task_boundary(native):
        compiled = compile_program(canonical['program'], tmp_path / 'parent',
            identity=native['identity'], capabilities=capabilities)
        raw = _observation_payload(list(range(0, 180000, 300)))
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in raw[name]: row['source_step'] = row['input_index'] % len(compiled['blocks'])
        diagnosis = diagnose(program, capabilities, initialization,
            dict(sim=dict(players=[dict(sim2gse_rule_observations=raw)])),
            task_run_id='fixture', batch_key='constructed-same-batch',
            behavior_identity=canonical['identity'], runtime=TaskRuntime())
        prefix = [0]
        assert [(row['operation'], row['source_path'], row['destination_path'])
                for row in diagnosis['pool']['operations']] == [
            ('move', prefix+[3], prefix+[0]), ('move', prefix+[3], prefix+[1]),
            ('move', prefix+[3], prefix+[2]), ('insert', None, prefix+[0])]
        changed = apply(program, diagnosis['pool']['operations'][0])
        changed_canonical = canonicalize_search_program(changed, capabilities)
        selected = compile_program(changed_canonical['program'], tmp_path / 'selected',
            identity=native['identity'], capabilities=capabilities)
    assert diagnosis['pool']['complete'] is True
    assert changed == [dict(kind='Loop', count=3,
        blocks=[['death_coil'], ['outbreak'], ['outbreak'], ['outbreak']])]
    assert [[command['simc_action'] for command in block] for block in selected['blocks']] == [
        ['death_coil'], ['outbreak'], ['outbreak'], ['outbreak']] * (3)

def test_public_observation_request_closes_only_declared_object_dependencies(tmp_path, monkeypatch):
    from rule_diagnostics import observation_request
    pack = _condition_pack()
    pack['object_sets']['sample'].update({
        'scope_a': dict(kind='target_scope', value='current_attack_target'),
        'scope_b': dict(kind='target_scope', value='all_currently_engaged_required_targets'),
        'unused_scope': dict(kind='target_scope', value='controlled_player'),
        'qualification': dict(kind='state', native_identity='literal.true'),
        'compound': dict(kind='effect', components=[
            dict(native_identity='first_component', target_scope='scope_a'),
            dict(native_identity='second_component', target_scope='scope_b')],
            from_action='first', qualification='qualification')})
    for rule in pack['configurations'][0]['states']['only']['priority']:
        rule['arguments']['activation_effect'] = 'compound'
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    _, initialization = _diagnostic_initialization(tmp_path, pack, native)
    # 去掉初始化缓存，确实由声明解析闭包，不能预填预期请求自比。
    initialization.pop('rule_observation_request')
    request = observation_request(initialization, protocol=2)
    assert set(request['objects']) == {'consumer', 'counter', 'compound', 'first', 'qualification', 'scope_a', 'scope_b'}


def test_public_failed_rule_step_is_terminal_and_repeat_does_not_score(tmp_path, monkeypatch):
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
            search_config=_eager_search_config(input_interval_ms=200, candidate_limit=3, batch_targets=(2,), iterations=2))
        parent = read_task(tmp_path / 'task')['search']['rule_diagnostics']
        operation = next(row for row in parent['pool']['operations'] if row['operation'] == 'move')
        request = dict(parent_identity=parent['parent_identity'], operation_id=operation['operation_id'])
        invoke = lambda: resume_task(tmp_path / 'task', rule_step=request)
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


@pytest.mark.parametrize('actual_form,supported', [('fixture_form', True), ('death_coil', False)])
def test_public_rule_checks_the_requested_specific_form(tmp_path, monkeypatch, actual_form, supported):
    pack = _condition_pack()
    pack['object_sets']['sample']['consumer']['native_forms'].append('fixture_form')
    pack['object_sets']['sample']['specific_form'] = dict(kind='action', native_action='fixture_form',
        base_button='death_coil', native_forms=['fixture_form'])
    for rule in pack['configurations'][0]['states']['only']['priority']: rule['arguments']['action'] = 'specific_form'
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def form_engine(result):
        for row in result['report']['sim']['players'][0]['sim2gse_rule_observations']['action_observations']:
            row.update(object='specific_form', actual_form=actual_form, native_qualified=None,
                has_cooldown=False, resource_costs={'runic_power': 10}, resource_balances={'runic_power': 20},
                known_native_requirements=[])
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, form_engine)
    assert bool(diagnosis['pool']['operations']) is supported
    if not supported:
        assert not any(row['kind'] == 'missed_opportunity' for row in diagnosis['rules'][0]['findings'])


def test_public_frozen_burst_protection_blocks_high_rule_without_suppressing_ordinary_rule(tmp_path, monkeypatch):
    import burst, result_store, sequence
    from test_burst import reviewed_fixture, character_seed_boundary
    pack = _condition_pack()
    pack['object_sets']['sample']['protected'] = dict(kind='action', native_action='fixture_protected_form',
        base_button='army_of_the_dead', native_forms=['fixture_protected_form'])
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
        payload['action_observations'] += [dict(row, object='protected', actual_form='fixture_protected_form',
            base_button='army_of_the_dead') for row in ordinary]
        return result

    with character_seed_boundary(native_reference=native), patch.object(sequence, 'evaluate', side_effect=protected_engine):
        result = run_task(source, tmp_path / 'task', use_burst=True,
            simulation_config=dict(scene='single_target'), search_config=_eager_search_config(input_interval_ms=200,
                candidate_limit=1, batch_targets=(2,), iterations=2))
    diagnosis = result['search']['rule_diagnostics']
    high, low = diagnosis['rules']
    assert {row['kind'] for row in high['findings']} == {'blocked_by_plan'}
    assert 'missed_opportunity' in {row['kind'] for row in low['findings']}
    assert diagnosis['pool']['operations']
    assert all(c['rule'] == 'ordinary consumer' for op in diagnosis['pool']['operations'] for c in op['contributors'])


def test_public_terminal_rule_step_republishes_saved_result_after_storage_crash_without_scoring(tmp_path, monkeypatch):
    import result_store, sequence
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
        return _observed_evaluate(*args, **kwargs)

    write, intended_limits = result_store.write, []
    def crash_result_save(table, *args, **kwargs):
        if table == 'runs':
            intended_limits.append(args[1][0]['search_metrics']['no_improvement_round_limit'])
            raise StorageCrash('process stopped before result publication')
        return write(table, *args, **kwargs)

    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=interrupted_engine):
        run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=_eager_search_config(input_interval_ms=200, candidate_limit=3, batch_targets=(2,), iterations=2))
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
    assert saved['search']['rule_steps'][request['operation_id']]['status'] == 'scored'
    assert saved['search']['candidate_count'] == 3
    assert saved['search']['no_improvement_round_limit'] == intended_limits[0]
    assert any(row.get('rule_step', {}).get('request') == request for row in saved['search']['records'])


def test_public_overlapping_short_effects_select_per_input_and_keep_original_instances(tmp_path, monkeypatch):
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    template = json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['短期增益利用']
    # 通过可编辑模板额外输出支持集合，核对A→B→A而非切断/复制A实例。
    next(row['value'] for row in template['diagnose']['let'] if row['name'] == 'contexts')['args'][1]['fields']['assigned_inputs'] = dict(op='map',
        args=[dict(var='rows'), dict(var='q.action.input_index')], **{'as': 'q'})
    template['diagnose']['cases'].append(dict(kind='window_assignment', when=True, certainty='observed_fact',
        evidence=dict(window=dict(var='c.window'), inputs=dict(var='c.assigned_inputs'))))

    pack['general']['templates'] = {'overlap-renamed': template}
    pack['object_sets']['sample'].update(window_a=dict(kind='effect', native_identity='first_buff'),
                                        window_b=dict(kind='effect', native_identity='second_buff'))
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='earliest actual end',
        template='overlap-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect_refs=['window_a', 'window_b'], window_selection='earliest_end',
            use_position='last_finishable', consume_required=False, usage_time_basis='effect_completion'))]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def overlap_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope']['effect_events_complete'] = {'window_a': True, 'window_b': True}
        for name in ('inputs', 'action_observations', 'state_observations'):
            payload[name] = payload[name][:6]
        for row in payload['action_observations']:
            row.update(effect_completion_time=row['time'], event_index=row['input_index'] * 10 + 1)
        payload['effect_events'] = []
        for alias, instance, start, end, start_index, end_index, complete in [
                ('window_a', 101, 0, 1000, 0, 60, True), ('window_b', 102, 400, 600, 20, 40, True),
                *([('window_a', 103, 0, 200, 2, 15, False)])]:
            event = dict(object=alias, sample_id=1, effect_id=alias, instance_id=instance,
                target_id=0, source_id=0, applicable=True, start=start, lifecycle_complete=complete)
            payload['effect_events'].extend([
                dict(event, event_index=start_index, kind='start', time=start, end=None, end_reason=None),
                dict(event, event_index=end_index, kind='expire', time=end, end=end, end_reason='expired')])
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, overlap_engine)
    rule, = diagnosis['rules']
    assignments = [row for row in rule['findings'] if row['kind'] == 'window_assignment']
    assert [(row['window']['instance_id'], row['window']['start'], row['window']['end'], row['inputs'])
            for row in assignments] == [(101, 0, 1000, [0, 1, 4, 5]), (102, 400, 600, [2, 3])]
    assert [(row['window']['instance_id'], row['input_index']) for row in rule['findings']
            if row['kind'] == 'missed_short_window'] == [(101, 5), (102, 3)]
    assert bool(rule['unknown_evidence']) is True


def test_public_incomplete_window_keeps_scoped_unknown_trigger_without_erasing_known_support(tmp_path, monkeypatch):
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
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def uncertain_engine(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:6]
        for row in payload['state_observations']: row['value'] = 1 if row['input_index'] in (0, 2, 3, 4) else 0
        ordinary = payload['action_observations']
        payload['action_observations'] += [dict(row, object='high_action', effect_completion_time=row['time'],
            event_index=row['input_index'] * 10 + 1, native_qualified=row['input_index'] != 3) for row in ordinary]

        payload['effect_events'] = []
        payload['scope']['effect_events_complete'] = {'window': True}
        episodes = [('not_requested', 999, 0, 1000, 0, 60, False)]
        episodes.append(('window', 102, 400, 600, 20, 40, False))
        episodes.append(('window', 101, 0, 1000, 0, 60, True))

        for alias, instance, start, end, start_index, end_index, complete in episodes:
            event = dict(object=alias, sample_id=1, effect_id=alias, instance_id=instance,
                target_id=0, source_id=0, applicable=True, start=start, lifecycle_complete=complete)
            payload['effect_events'].extend([
                dict(event, event_index=start_index, kind='start', time=start, end=None, end_reason=None),
                dict(event, event_index=end_index, kind='expire', time=end, end=end, end_reason='expired')])
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, uncertain_engine)
    higher, lower = diagnosis['rules']
    findings = {(row.get('input_index'), row['kind']) for row in lower['findings']}
    assert (0, 'yielded') in findings
    assert (3, 'missed_opportunity') in findings  # 高位自身已知不符合，不能扩成未知让位。
    assert (4, 'missed_opportunity') in findings
    assert (2, 'missed_opportunity') not in findings
    assert (2, 'yielded') not in findings
    assert any(row['input_index'] == 2 for row in lower['unknown_conditions'])


def test_public_mixed_state_values_keep_types_through_batch_storage_and_cache(tmp_path, monkeypatch):
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

    config = _eager_search_config(input_interval_ms=200, candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1)
    with _apl_task_boundary(native), patch.object(sequence, 'evaluate', side_effect=mixed_states) as scoring:
        first = run_task(source, tmp_path / 'first', simulation_config=dict(scene='single_target'), search_config=config)
        saved = read_task(tmp_path / 'first', include_search_records=True, include_reports=True)

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


def test_batch_cost_storage_rejects_duplicate_declared_keys():
    import result_store
    storage = dict(version=1, kind='record', keys=['rune'])
    costs = dict(rune=0)
    storage['keys'].append('rune')
    result_store.write('batches', 'cost-shape-broken', [dict(batch_key='cost-shape-broken',
        report=dict(sim=dict(players=[dict(sim2gse_rule_observations=dict(action_observations=[
            dict(object='action', resource_costs=costs, resource_costs_storage=storage)]))])))])
    expected = result_store.InvalidRecordError
    for read in (lambda: result_store.one('batches', 'batch_key', 'cost-shape-broken'),
                 lambda: result_store.read_many('batches', ['cost-shape-broken'])):
        with pytest.raises(expected, match='费用映射存储') as caught: read()



@pytest.mark.parametrize('operation', ['and', 'any3'])
def test_public_boolean_operators_keep_numeric_state_unknown(tmp_path, monkeypatch, operation):
    pack = _condition_pack()
    value = dict(var='row.value')
    expression = dict(op=operation, args={'and': [True, value], 'any3': [[value]]}[operation])

    template = pack['general']['templates']['renamed-template']
    template.update(diagnose=dict(let=[], for_each=dict(var='scalar'), **{'as': 'row'}, cases=[
        dict(kind='true', when=expression, certainty='observed_fact'),
        dict(kind='false', when=dict(op='not', args=[expression]), certainty='observed_fact'),
        dict(kind='unknown', when=dict(op='unknown', args=[expression]), certainty='unknown')],
        export_trigger_records=[]), edits=[])
    pack['configurations'][0]['states']['only']['priority'] = pack['configurations'][0]['states']['only']['priority'][:1]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def zero_is_not_a_boolean(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:1]
        payload['state_observations'][0]['value'] = 0
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, zero_is_not_a_boolean)
    rule, = diagnosis['rules']
    assert [row['kind'] for row in rule['findings']] == ['unknown']


@pytest.mark.parametrize('representation,value,expected', [('positive_stack_presence', 1, 'true'), ('positive_stack_presence', None, 'unknown'), ('boolean', 1, 'unknown')])
def test_public_maintenance_qualification_uses_declared_representation(tmp_path, monkeypatch, representation, value, expected):
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
    objects['counter']['representation'] = representation
    objects.update(always=dict(kind='state', native_identity='literal.true', representation='boolean'),
        scope=dict(kind='target_scope', value='controlled_player'), owner=dict(kind='source', value='controlled_player'),
        effect=dict(kind='effect', native_identity='fixture_buff'))
    pack['general']['templates'] = {'qualification-renamed': template}
    pack['configurations'][0]['states']['only']['priority'] = [dict(name='declared qualification',
        template='qualification-renamed', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect='effect', effect_qualification='counter', replacement_qualification='always', target_scope='scope', source='owner'))]
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def typed_state(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        for name in ('inputs', 'action_observations', 'state_observations'): payload[name] = payload[name][:1]
        payload['state_observations'][0]['value'] = value
        payload['state_observations'].append(dict(payload['inputs'][0], object='always', value=True))
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, typed_state)
    rule, = diagnosis['rules']
    assert [row['kind'] for row in rule['findings']] == [expected]


@pytest.mark.parametrize('preceding', ['absent', 'known', 'unknown', 'foreign_sample'])
def test_public_maintenance_reports_initial_gap_from_actual_buff_edges(tmp_path, monkeypatch, preceding):
    from rule_config import DEFAULT_PATH
    pack = _condition_pack()
    pack['general']['templates'] = {'renamed-maintenance':
        json.loads(DEFAULT_PATH.read_bytes())['general']['templates']['持续效果维护']}
    pack['object_sets']['sample'].update(
        always=dict(kind='state', native_identity='literal.true', representation='boolean'),
        scope=dict(kind='target_scope', value='controlled_player'),
        owner=dict(kind='source', value='controlled_player'),
        effect=dict(kind='effect', native_identity='fixture_buff'))

    pack['configurations'][0]['states']['only']['priority'] = [dict(name='actual maintenance gap',
        template='renamed-maintenance', arguments=dict(action='consumer', priority_refs=[], edit_range='editable',
            effect='effect', effect_qualification='always', replacement_qualification='always',
            target_scope='scope', source='owner'))]

    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200

    def actual_buff_edges(result):
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        payload['scope'].update(end_ms=1000, controlled_actor_index=0, effect_events_complete={'effect': True})
        for name in ('inputs', 'action_observations'): payload[name] = payload[name][:4]
        for row in payload['inputs']:
            row.update(event_index=row['input_index'] * 10 + 1,
                       target_scopes={'scope': [dict(target_id=0, required=True)]})
        for row in payload['action_observations']: row['event_index'] = row['input_index'] * 10 + 1
        payload['state_observations'] = [dict(row, object='always', value=True) for row in payload['inputs']]

        payload['effect_observations'] = [dict(row, object='effect', target_id=0, source_id=0,
            component_id='fixture_buff', active=row['time'] > 400, applicable=True) for row in payload['inputs']]

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

        if preceding == 'foreign_sample':
            for row in payload['action_observations']:
                row.update(native_qualified=row['input_index'] == 2, success=row['input_index'] == 2,
                           effect_completion_time=400 if row['input_index'] == 2 else None)
            payload['effect_events'][0].update(source_input_index=2,
                                               source_actual_action='death_coil')
            # 点击快照不证明应用谱系，故刻意与实际事件是否有来源分开。
            payload['effect_observations'][2].update(applied=False, source_input_index=2)
        if preceding == 'foreign_sample':
            for row in payload['effect_events']: row['sample_id'] = 99

        if preceding == 'foreign_sample':
            # 当前状态预计作用时间与已经发生的应用时刻独立提供，不能互相回填。
            payload['action_observations'][2].update(estimated_effect_completion_time=400,
                effect_completion_estimate=dict(effect_id='fixture_buff', target_id=0, source_id=0,
                    actual_form='death_coil', effect_delay_ms=0, precision='current_state_estimate'))
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, actual_buff_edges)
    rule = diagnosis['rules'][0]
    kinds = [row['kind'] for row in rule['findings']]
    gaps = [row['gap'] for row in rule['findings'] if row['kind'] == (
        'actual_coverage_gap')]
    expected = [] if preceding == 'foreign_sample' else [
        (200 if preceding in ('known', 'unknown') else 0, 400, 25)]
    assert [(row['start'], row['end'], row.get('end_event_index')) for row in gaps] == expected
    if preceding == 'absent': assert gaps[0]['preceding_interval'] == {}
    elif preceding == 'known':
        assert (gaps[0]['preceding_interval']['start'], gaps[0]['preceding_interval']['end']) == (0, 200)
    elif preceding == 'unknown': assert gaps[0]['preceding_interval'] is None

    if preceding == 'foreign_sample':
        assert 'covered' not in kinds
        assert rule['status'] == 'unknown' and '计分样本' in rule['reason']

    assert all(row['effect'] == dict(component_id='fixture_buff', target_id=0, source_id=0) for row in gaps)
    assert diagnosis['pool']['operations'] == []

@pytest.mark.parametrize('estimate_case', ['matching', 'wrong_target', 'native_forbidden'])
def test_public_maintenance_uses_identity_bound_estimate_without_fabricating_actual_completion(tmp_path, monkeypatch, estimate_case):
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
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']: row['gcd_ms'] = 200
    observed = []

    def estimated_boundary(result):
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
        if estimate_case == 'wrong_target': action['effect_completion_estimate']['target_id'] = 1
        if estimate_case == 'native_forbidden': action['native_qualified'] = False
        observed.append(copy.deepcopy(payload))
        return result

    diagnosis = _direct_diagnosis(tmp_path, pack, native, estimated_boundary)
    diagnostic = diagnosis
    rule, = diagnostic['rules']
    if estimate_case != 'matching':
        assert diagnostic['pool']['operations'] == []
        assert all(row['kind'] != 'maintenance_opportunity' for row in rule['findings'])
        return
    assert any(row['kind'] == 'maintenance_opportunity' and row['input_index'] == 0 for row in rule['findings'])
    assert [(row['operation'], row['destination_path']) for row in diagnostic['pool']['operations']] == [
        ('move', [0]), ('insert', [0])]
    assert all(row['effect_completion_time'] is None for row in observed[0]['action_observations'])
    assert observed[0]['effect_events'][0].get('source_input_index') is None
