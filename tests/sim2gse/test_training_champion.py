"""网页双场通过真实任务和隔离中心消费最终训练冠军。"""
import json
from copy import deepcopy
import threading
import sqlite3
import pytest
from unittest.mock import patch
from pathlib import Path
from urllib.request import Request, urlopen

from test_burst import page_task_engine, reviewed_fixture
from test_seed_training import memory_result_center
from engine import check_report as REAL_CHECK_REPORT


@pytest.fixture
def champion_engine(page_task_engine, monkeypatch):
    """构造原生交换与不变源码身份，最终报告仍使用生产角色核验。"""
    import engine
    import task
    rule_hashes, rules = task._rule_hashes, {}
    rules_lock = threading.Lock()
    def verified_rules(*, relative_to=None):
        with rules_lock:
            if relative_to not in rules:
                rules[relative_to] = rule_hashes(relative_to=relative_to)
            return dict(rules[relative_to])

    # 与用例的局部替换同栈撤销，避免其清理时重新装回已结束夹具。
    monkeypatch.setattr(task, '_rule_hashes', verified_rules)
    import sequence
    evaluate = sequence.evaluate
    def persisted_scene_report(profile, candidate, folder, **kwargs):
        result = evaluate(profile, candidate, folder, **kwargs)
        # 模拟外部生产者的落盘报告必须与返回的目标场景一致，供保存报告与旧成果验真。
        (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result
    with patch.object(sequence, 'evaluate', side_effect=persisted_scene_report), \
            patch.object(engine, 'check_report', REAL_CHECK_REPORT):
        yield


@pytest.fixture
def unchanged_offspring(monkeypatch):
    """仅持久化/恢复代表固定子代；真实起点、完整两代和正常3×128不缩减。"""
    import population_training
    monkeypatch.setattr(population_training, '_cross', lambda *args, **kwargs: False)
    monkeypatch.setattr(population_training, 'mutate', lambda program, *args, **kwargs: deepcopy(list(program)))
    yield


@pytest.fixture
def unchanged_champion_engine(champion_engine, unchanged_offspring):
    yield


def completed_training(tmp_path, targets, programs, *, name='current', candidate_offset=0, prepared_context=None, source_engines=None, report_engines=None, legacy_search=False):
    """构造完整最终成绩凭据，不启动训练或原生计算。"""
    from contextlib import closing
    import shutil
    import burst
    import engine
    import result_store
    import seed_training
    from program import canonicalize_search_program
    from runtime import TaskRuntime
    from search import TaskStore, STATS_VERSION, digest
    from test_search import _fast_report

    _, raw = reviewed_fixture()
    template = tmp_path / (name + '-standard.simc')
    template.write_text(raw, encoding='utf-8')
    from legacy_training_fixture import _minimal_rule_pack
    from legacy_training_rules import validate, bind
    pack = _minimal_rule_pack()
    rule_snapshot = dict(pack=pack, resolved=validate(pack), rule_config_digest=digest(pack))
    inputs = seed_training._training_inputs(template, targets, use_burst=True,
        verified_engines=source_engines, rule_snapshot=rule_snapshot)
    versions = seed_training.semantic_versions()
    if legacy_search:
        versions['search'] = 'rule-single-step-coba-linucb-v1'
        for key in ('rule_initialization_enabled', 'adaptive_selector_enabled', 'search_timeline'):
            inputs['config'].pop(key, None)
    character = inputs['character']
    batch = tmp_path / 'custom-training' / str(targets) / name
    batch.mkdir(parents=True)
    if prepared_context is not None:
        capabilities, context = prepared_context['capabilities'], prepared_context['burst']
    else:
        native = engine.reference(template, batch / 'reference', character,
                                  simulation_config=inputs['simulation_config'])
        _, capabilities, context = engine.prepare_loop(native, character, batch, TaskRuntime(600),
            definition=inputs['definition'], interval_ms=200)
    from search import initial_programs
    if prepared_context is not None:
        native = engine.reference(template, batch / 'scope-reference', character,
                                  simulation_config=inputs['simulation_config'])
    binding = bind(capabilities, native['static_snapshot'], targets, spec_id=252,
        scene=inputs['simulation_config']['scene'], rule_snapshot=rule_snapshot)
    initialization = dict(configuration_key=binding['configuration_key'],
        rule_config_digest=rule_snapshot['rule_config_digest'], bindings=[],
        static_snapshot=native['static_snapshot'])
    configuration_key = initialization['configuration_key']
    payload = seed_training.training_condition_input(inputs['template_sha'], inputs['engines'],
        inputs['config'], inputs['simulation_config'], burst_context=context, rule_snapshot=rule_snapshot)
    condition = seed_training.semantic_condition(payload, versions)
    manifest = dict(format=1, condition=condition, condition_input=payload, rule_snapshot=rule_snapshot,
        input_sha256=digest(payload), semantic_versions=versions,
        semantic_condition=condition, executions=[])
    (batch / 'standard.simc').write_text(raw, encoding='utf-8')
    (batch / 'condition.txt').write_text(condition, encoding='ascii')
    (batch / 'identity.json').write_text(json.dumps(manifest), encoding='utf-8')
    times, _ = burst.combined_inputs(list(range(0, 180000, 200)), context, 200)
    rows = []
    schema_template = batch / 'empty-task.sqlite3'
    for ordinal, (program, scores) in enumerate(programs):
        candidate_id = f'{targets:02d}{ordinal + candidate_offset:010d}' + '0' * 52
        folder = batch / candidate_id[:12]
        folder.mkdir()
        if ordinal:
            shutil.copyfile(schema_template, folder / 'task.sqlite3')
        store = TaskStore(folder)
        if ordinal == 0 and len(programs) > 1:
            assert not store.state and not store.persisted_batches
            with closing(sqlite3.connect(schema_template)) as database:
                store.db.backup(database, name='main')
        store.state.update(run_id=candidate_id, training_condition=condition,
            training_candidate_id=candidate_id, config=inputs['config'], capabilities=capabilities,
            burst=context, phase='done', rule_initialization=initialization)
        form = canonicalize_search_program(program, capabilities)['form']
        group = folder.name + '-retest-final'
        reports = []
        for index, (seed, score) in enumerate(zip(seed_training.RETEST_SEEDS, scores)):
            key = digest(dict(folder=str(folder / 'retest-final'), seed=seed))
            request = dict(condition=condition, program=form, behavior_identity=digest(form),
                purpose='seed_retest', seed=seed, input_seed=seed, iterations=128, times=times,
                stats=STATS_VERSION, trace=False, reset_events=[])
            receipt = dict(status='success', request=request, dps=score, samples=127,
                           variance=0., requested_iterations=128, data_key=key, storage_group_key=group)
            report = _fast_report(character, score, 127)
            report['sim']['players'][0]['sim2gse_static_snapshot'] = native['static_snapshot']
            report['sim']['targets'] *= targets
            reports.append(result_store.prepare_batch(dict(batch_key=key, run_id=candidate_id,
                purpose='seed_retest', seed=seed, input_seed=seed, iterations=128,
                requested_iterations=128, samples=127, dps=score, variance=0.,
                engines=report_engines if report_engines is not None else inputs['engines'],
                condition_key=condition, candidate_key=digest(form),
                program_identity=json.dumps(form, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                batch_index=index, scenario='nominal', stats_version=STATS_VERSION,
                times=times, trace=False, report=report)))
            store.put_batch(key, receipt)
        result_store.write('batches', group, reports)
        store.save()
        store.close()
        rows.append(dict(configuration_key=configuration_key, candidate_id=candidate_id, condition=condition, status='completed', error='',
            initial_program=program, program=program, family='plain', core_retained=False,
            rounds=2, stop_reason='no_improvement', elapsed_seconds=1., scores=scores,
            initial_scores=[99999.] * 3, comparison={}, task_path=str(folder),
            native_batch_starts=0, batch_requests=0, cache_hits=0))
    result_store.write('seed_processed', seed_training.shared_scope(configuration_key), rows, schema=seed_training.PROCESSED_SCHEMA)
    return template, rows


def dual_result(tmp_path, raw, candidate_limit=9, *, expected='completed', interval_ms=200, before_resume=None,
                validation_batches=1):
    """走已批准的 POST 双场到 GET 公开结果接缝。"""
    from interface import create_server
    server = create_server(tmp_path / 'page', task_options=dict(search_config=dict(
        candidate_limit=candidate_limit, batch_targets=(2,), iterations=2,
        validation_batches=validation_batches, final_batches=1, final_iterations=2, scenarios=('nominal',))))
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(Request(base + '/api/tasks', json.dumps(dict(profile=raw, mode='dual', input_interval_ms=interval_ms)).encode(),
                             {'Content-Type': 'application/json'}), timeout=5) as response:
            created = json.load(response)
        server.tasks[created['task_id']][1].join(30)
        with urlopen(base + '/api/tasks/' + created['task_id'], timeout=5) as response:
            state = json.load(response)
        assert state['status'] == expected, state
        if before_resume is not None:
            previous = state
            before_resume(state)
            with urlopen(Request(base + '/api/tasks/' + created['task_id'] + '/resume', b'{}',
                                 {'Content-Type': 'application/json'}), timeout=5) as response:
                json.load(response)
            server.tasks[created['task_id']][1].join(30)
            with urlopen(base + '/api/tasks/' + created['task_id'], timeout=5) as response:
                state = json.load(response)
            assert state['status'] == 'completed', state
            state['previous_state'] = previous
        return state
    finally:
        for _, handle in server.tasks.values():
            if not handle.done:
                handle.cancel_event.set()
                handle.join(5)
        server.shutdown()
        server.server_close()
        thread.join(3)


@pytest.mark.parametrize('legacy_search', [False, True])
@pytest.mark.parametrize('wrong_report_engine', [False, True])
def test_dual_rescores_training_champion_from_an_older_engine(monkeypatch, wrong_report_engine, legacy_search):
    from champion_evidence_fixture import training_history, read_training_history
    from task import _seed_programs
    from runtime import TaskRuntime
    history = training_history(monkeypatch, [([['outbreak'], ['death_coil'], ['outbreak']], [99999.] * 3)],
        report_engines=({'baseline': 'current', 'controlled': 'current'} if wrong_report_engine else None),
        legacy_search=legacy_search)
    before = deepcopy(history['rows'])
    champion = read_training_history(history)
    if wrong_report_engine:
        assert champion['status'] == 'absent'
        assert champion['excluded'][0]['status'] == 'invalid'
        assert '复测引擎' in champion['excluded'][0]['reason']
    else:
        assert champion['status'] == 'selected', champion
        assert champion['candidate_id'] == history['rows'][0]['candidate_id']
        assert champion['engines'] == history['inputs']['engines']
        assert champion['scores'] == [99999.] * 3
        starts, decisions = _seed_programs([], [champion], character=history['inputs']['character'],
            targets=1, configuration_key=history['configuration_key'],
            capabilities=next(iter(history['states'].values()))['capabilities'], runtime=TaskRuntime(600))
        assert starts == [history['rows'][0]['program']]
        assert decisions[0]['status'] == 'accepted'
        # 只交付当前角色程序，不带任何历史DPS作当前评分；实际重评分由real旧源消费链保留。
        assert not any(isinstance(item, dict) and 'score' in item for item in starts)
    assert history['rows'] == before


@pytest.mark.parametrize('fault', ['wrong_program', 'report_missing', 'report_corrupt', 'temporary_error'])
def test_training_champion_rejects_invalid_final_evidence_and_reports_temporary_storage_errors(monkeypatch, fault):
    import result_store
    from champion_evidence_fixture import training_history, read_training_history
    history = training_history(monkeypatch, [([['outbreak']], [100.] * 3),
        ([['death_coil']], [200.] * 3)])
    high = history['rows'][1]
    key = next(iter(history['receipts'][high['candidate_id']]))
    if fault == 'wrong_program':
        history['receipts'][high['candidate_id']][key]['request']['program'] = {}
        history['refresh']()
    else:
        one = result_store.one
        def read_report(table, field, value, **kwargs):
            if value == key:
                if fault == 'report_missing': return None
                if fault == 'report_corrupt': raise result_store.InvalidRecordError('corrupt original report')
                raise OSError('temporary isolated storage failure')
            return one(table, field, value, **kwargs)
        monkeypatch.setattr(result_store, 'one', read_report)
    if fault == 'temporary_error':
        with pytest.raises(result_store.DataReadError, match='暂时不可读'):
            read_training_history(history)
        return
    champion = read_training_history(history)
    assert champion['candidate_id'] == history['rows'][0]['candidate_id']
    excluded = next(row for row in champion['excluded'] if row['candidate_id'] == high['candidate_id'])
    assert excluded['status'] == ('missing' if fault == 'report_missing' else 'invalid')


def test_dual_does_not_replace_an_inapplicable_highest_champion_with_second_place(monkeypatch):
    from champion_evidence_fixture import training_history, read_training_history
    from task import _seed_programs
    from runtime import TaskRuntime
    history = training_history(monkeypatch, [([['death_coil']], [100.] * 3),
        ([['outbreak']], [200.] * 3)])
    champion = read_training_history(history)
    capabilities = deepcopy(next(iter(history['states'].values()))['capabilities'])
    capabilities['actions'] = [action for action in capabilities['actions'] if action['simc_action'] != 'outbreak']
    capabilities['sources'].append(dict(catalogue='apl', status='native_unavailable',
        action_initialized=True, available=False, data_valid=True, data_id=1001,
        signature='outbreak', name='outbreak', gcd_ms=1500))
    starts, decisions = _seed_programs([], [champion], character=history['inputs']['character'], targets=1,
        configuration_key=history['configuration_key'], capabilities=capabilities, runtime=TaskRuntime(600))
    assert champion['candidate_id'] == history['rows'][1]['candidate_id']
    assert starts == []
    assert decisions[0]['status'] == 'rejected' and decisions[0]['reason']


@pytest.mark.real
def test_dual_resume_keeps_the_frozen_training_champion_after_new_training_arrives(tmp_path, monkeypatch,
        memory_result_center, unchanged_champion_engine):
    from contextlib import ExitStack
    import burst
    import engine
    import result_store
    import seed_training
    import sequence
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    template, rows = completed_training(tmp_path, 1, [
        ([['outbreak'], ['death_coil'], ['outbreak']], [190., 200., 210.])])
    _, aoe_rows = completed_training(tmp_path, 5, [
        ([['death_coil'], ['outbreak'], ['death_coil']], [290., 300., 310.])])
    monkeypatch.setattr(engine, '_training_template', lambda manifest: template)
    evaluate = sequence.evaluate
    cancelled = False
    def cancel_first_score(*args, **kwargs):
        nonlocal cancelled
        result = evaluate(*args, **kwargs)
        if not cancelled:
            cancelled = True
            kwargs['runtime'].cancel()
        return result
    def update_training(previous):
        assert previous['scenes'][0]['training_champion_snapshot']['candidate_id'] == rows[0]['candidate_id']
        _, arrivals = completed_training(tmp_path, 1, [
            ([['death_coil'], ['outbreak'], ['death_coil']], [900.] * 3)], name='later', candidate_offset=1000)
        # 新训练确有完整更高成绩，但恢复不得重新选择本场冠军。
        result_store.write('seed_processed', __import__('seed_training').shared_scope(dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')), rows + arrivals,
                           schema=seed_training.PROCESSED_SCHEMA)
        api = result_store._api()
        def frozen_read(root, table, key, **kwargs):
            if table == 'seed_processed' and key == __import__('seed_training').shared_scope(dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')):
                raise OSError('恢复刷新了单目标训练库')
            return api['read_key'](root, table, key, **kwargs)
        patches.enter_context(patch.object(result_store, '_api', return_value=dict(api, read_key=frozen_read)))
    with ExitStack() as patches, patch.object(sequence, 'evaluate', side_effect=cancel_first_score):
        state = dual_result(tmp_path, raw, expected='cancelled', before_resume=update_training)
    assert state['scenes'][0]['training_champion_snapshot'] == state['previous_state']['scenes'][0]['training_champion_snapshot']
    assert [scene['training_champion_snapshot']['candidate_id'] for scene in state['scenes']] == [
        rows[0]['candidate_id'], aoe_rows[0]['candidate_id']]
    assert [scene['training_champion_snapshot']['scores'] for scene in state['scenes']] == [
        [190., 200., 210.], [290., 300., 310.]]


@pytest.mark.parametrize('fault', ['processed_corrupt', 'processed_temporary'])
def test_dual_distinguishes_corrupt_training_records_from_temporary_read_failures(monkeypatch, fault):
    import result_store
    from champion_evidence_fixture import training_history, read_training_history
    history = training_history(monkeypatch, [([['outbreak']], [200.] * 3)])
    error = (result_store.InvalidRecordError('corrupt processed record') if fault == 'processed_corrupt'
             else result_store.DataReadError('temporary isolated processed storage error'))
    def unreadable(*args, **kwargs): raise error
    monkeypatch.setattr(result_store, 'read_records', unreadable)
    if fault == 'processed_temporary':
        with pytest.raises(result_store.DataReadError): read_training_history(history)
    else:
        snapshot = read_training_history(history)
        assert snapshot['status'] == 'absent' and snapshot['excluded'][0]['status'] == 'invalid'


@pytest.mark.real
def test_dual_reads_completed_v1_without_current_profession_rule_library(
        tmp_path, monkeypatch, memory_result_center, unchanged_offspring):
    import burst
    import engine
    import result_store
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    from test_search import _fast_initialization
    from test_burst import page_task_boundary
    with _fast_initialization(), page_task_boundary(), patch.object(engine, 'check_report', REAL_CHECK_REPORT):
        template, rows = completed_training(tmp_path, 1, [([['death_coil']], [190., 200., 210.])])
        monkeypatch.setattr(engine, '_training_template', lambda manifest: template)
        monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(tmp_path / 'removed-rules.json'))
        state = dual_result(tmp_path, raw, candidate_limit=1)
    champion = state['scenes'][0]['training_champion_snapshot']
    assert champion['status'] == 'selected'
    assert champion['candidate_id'] == rows[0]['candidate_id']


def test_dual_seed_scope_is_exact_and_target_count_is_only_source_evidence():
    from task import _seed_programs
    from runtime import TaskRuntime
    from test_search import _fast_capabilities
    key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')
    rows = [dict(configuration_key=key, candidate_id=f'scope-{index}', condition='source-condition',
        class_name='deathknight', spec='unholy', targets=99,
        program=[['outbreak'], dict(kind='WaitClicks', clicks=index + 2), ['death_coil']],
        score=99999.) for index in range(5)]
    unknown = dict(rows[0], configuration_key=None, candidate_id='unknown')
    foreign = dict(rows[0], configuration_key=dict(key, hero_talent='other_hero'), candidate_id='other')
    original = deepcopy([unknown, foreign, *rows])
    character = __import__('task').parse_character(reviewed_fixture()[1])
    starts, decisions = _seed_programs([], [unknown, foreign, *rows], character=character, targets=1,
        configuration_key=key, capabilities=_fast_capabilities(), runtime=TaskRuntime(600))
    assert len(starts) == len(decisions) == 4
    assert [row['candidate_id'] for row in decisions] == ['scope-0', 'scope-1', 'scope-2', 'scope-3']
    assert all(row['status'] == 'accepted' for row in decisions)
    assert [unknown, foreign, *rows] == original
    aoe, _ = _seed_programs([], rows, character=character, targets=5,
        configuration_key=dict(key, target_type='aoe'), capabilities=_fast_capabilities(), runtime=TaskRuntime(600))
    assert aoe == []


@pytest.mark.parametrize('fault', ['source_rules', 'report_hero'])
def test_dual_rejects_unproved_training_hero_identity(monkeypatch, fault):
    from champion_evidence_fixture import training_history, read_training_history
    history = training_history(monkeypatch, [([['death_coil']], [200.] * 3)])
    if fault == 'source_rules':
        history['manifest']['rule_snapshot']['pack']['identity_mappings']['hero_talents']['rider_of_the_apocalypse'] = 999
        history['refresh']()
    else:
        for report in history['reports'].values():
            report['report']['sim']['players'][0]['sim2gse_static_snapshot']['hero_subtree_ids'] = [999]
    champion = read_training_history(history)
    assert champion['status'] == 'absent'
    assert champion['excluded'][0]['status'] == 'invalid'


@pytest.mark.parametrize('versions, expected', [([None], 1), ([1], 1), ([2] * 4, 2)])
def test_training_selected_snapshot_uses_explicit_contract_not_source_labels(versions, expected):
    import seed_training
    rows = [dict(contract_version=version, source_kind='ga') if version is not None else dict(source_kind='ga')
            for version in versions]
    assert seed_training.selected_contract_version(rows) == expected


@pytest.mark.parametrize('versions', [[2], [1, 2], [True], ['2'], [3]])
def test_training_selected_snapshot_rejects_mixed_unknown_or_incomplete_contracts(versions):
    import seed_training
    with pytest.raises(ValueError, match='契约版本|完整四条'):
        seed_training.selected_contract_version([dict(contract_version=version) for version in versions])
