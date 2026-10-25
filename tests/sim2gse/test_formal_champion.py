"""正式冠军发布、竞争与恢复决策直接消费内存证据。"""
import pytest
from pathlib import Path
from unittest.mock import Mock
from test_population_training import memory_ga


def test_legacy_ten_sources_are_assembled_before_complete_formal_retests(memory_ga, monkeypatch):
    import task
    from program import canonicalize_search_program
    from runtime import TaskRuntime
    from search import initial_programs, digest
    from sequence import behavior_key

    former = [['death_coil']] * 6 + [dict(kind='WaitClicks', clicks=2), ['outbreak']]
    challenger = [['death_coil']] * 7 + [dict(kind='WaitClicks', clicks=3), ['outbreak']]
    case = memory_ga(formal=True, search_settings=dict(input_interval_ms=200),
        score_for=lambda candidate, options: grades.get(behavior_key(candidate), 100.))
    from burst import search_capabilities
    capabilities = search_capabilities(case.capabilities, [[case.capabilities['actions'][3]],
                                                          [case.capabilities['actions'][4]]])
    case.capabilities.update(capabilities)
    capabilities = case.capabilities
    state = case.store.state
    grades = {canonicalize_search_program(program, capabilities)['identity']: score
              for program, score in ((former, 200.), (challenger, 300.))}
    configuration = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse',
                         target_type='single_target')
    state.update(simulation_config=case.ready['simulation_config'], capabilities=capabilities, engines={})
    state['seed_selected_snapshot'] = [dict(configuration_key=configuration,
        candidate_id='selected-' + str(index), class_name='deathknight', spec='unholy',
        program=[['outbreak'], dict(kind='WaitClicks', clicks=2 + index), ['death_coil']])
        for index in range(4)]
    state['training_champion_snapshot'] = dict(configuration_key=configuration,
        candidate_id='training-winner', class_name='deathknight', spec='unholy',
        status='selected', program=challenger)
    binding = dict(condition=case.condition, input_effective_sha256='frozen-character',
        class_name=case.character.class_name, spec=case.character.spec, spec_id=252, target_count=1)
    state['formal_champion_snapshot'] = dict(status='selected', binding=binding,
        condition_key=digest(binding), program=former,
        behavior_identity=canonicalize_search_program(former, capabilities)['identity'],
        source_run_id='former-run', version=1)
    native = dict(action_sequence=[dict(name=name, queue_failed=False) for name in
        ['outbreak'] * 3 + ['death_coil'] * 2 + ['scourge_strike']])
    starts = initial_programs(capabilities, native, input_interval_ms=200)
    task._assemble_formal_starts(state, starts, character=case.character,
        configuration_key=configuration, capabilities=capabilities,
        runtime=TaskRuntime(float('inf')), use_burst=True)
    assert len(state['start_sources']) == 10
    assert len(state['starts']) == 10 and state['starts'][0] == former
    groups = [source for values in state['start_sources'].values() for source in values]
    assert [sum(source['source_kind'] == kind for source in groups) for kind in
        ('native', 'seed_selected', 'training_champion', 'formal_champion')] == [4, 4, 1, 1]
    assert state['formal_champion_adaptation']['status'] == 'accepted'
    result = case.run()
    assert 'chains' not in result['search']
    assert result['search']['stop_reason'] == 'stagnation'
    assert result['stop_policy'] == dict(version=1, kind='natural_stagnation')
    assert result['search_result']['dps'] == 300.
    task._prepare_formal_publication(case.store)
    record = state['formal_champion_publication_intent']['record']
    assert record['contract_version'] == 2
    assert record['promotion_evidence'] == []
    assert record['source_run_id'] != 'former-run'
    from contextlib import nullcontext
    from copy import deepcopy
    import result_store
    from champion_evidence_fixture import formal_cohort
    previous, *_ = formal_cohort(source_run_id='former-run', condition=case.condition,
        config=case.search_config, programs=[[['outbreak']], former])
    previous['evaluation']['engines'] = state['engines']
    current = [previous]
    monkeypatch.setattr(result_store, '_search_champion_lock', nullcontext)
    monkeypatch.setattr(result_store, 'read_search_champion', lambda key: deepcopy(current[0]))
    def save_replacement(table, key, rows, **kwargs):
        assert table == 'search_champions' and key == record['condition_key']
        current[0], = deepcopy(rows)
    monkeypatch.setattr(result_store, 'write', save_replacement)
    intent = state['formal_champion_publication_intent']
    publication = result_store.publish_search_champion(record, intent['expected_version'],
        expected_incumbent=intent['expected_incumbent'])
    assert publication['status'] == 'published'
    assert current[0]['source_run_id'] == state['run_id'] != previous['source_run_id']
    assert current[0]['score'] == 300. and previous['score'] == 200.
    assert current[0]['version'] == 2
    assert state['ga']['generation'] >= 2
    assert all(len(row['batches']) == 3 and row['samples'] == 381
               for row in state['formal_finalists'])


@pytest.mark.parametrize('targets', [1, 5])
def test_each_scene_freezes_inherits_and_preserves_its_published_champion(monkeypatch, memory_ga, targets):
    import sqlite3
    from copy import deepcopy
    from contextlib import nullcontext
    import engine
    import result_store
    import task
    from champion_evidence_fixture import formal_publication_inputs
    from runtime import TaskRuntime
    from search import TaskStore
    from sequence import behavior_key
    from test_search import _fast_report

    def score_inherited(profile, candidate, folder, **options):
        score = 200. if behavior_key(candidate) == snapshot['behavior_identity'] else 100.
        report = _fast_report(character, score, options['iterations'] - 1)
        report['sim']['targets'] *= targets
        return dict(report=report, summary=engine.check_report(report, character, options['iterations'],
            simulation_config=options['simulation_config'], allow_zero=True), trace=[])

    case = memory_ga(formal=True, programs=[], native=score_inherited,
                     search_settings=dict(input_interval_ms=200))
    from burst import search_capabilities
    case.capabilities.update(search_capabilities(case.capabilities, [[case.capabilities['actions'][3]],
                                                                  [case.capabilities['actions'][4]]]))
    case.ready['simulation_config'].update(target_count=targets, scene='single_target' if targets == 1 else 'aoe')
    first = formal_publication_inputs(target_count=targets, source_run_id='first-scene',
        condition=case.condition, config=case.search_config)
    original, state, character, run, candidate, reports = first
    current = [None]
    sources, artifacts = {run['run_id']: run}, {candidate['candidate_data_key']: candidate}
    destination = Path('/memory/scene')
    text = {destination / 'input.simc': character.raw_text, destination / 'result.json': '{}'}
    read_text = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda path, **kwargs:
        text[path] if path in text else read_text(path, **kwargs))
    monkeypatch.setattr(task, '_write_json', lambda path, value, **kwargs: None)
    monkeypatch.setattr(result_store, '_search_champion_lock', nullcontext)
    monkeypatch.setattr(result_store, 'read_search_champion', lambda key: deepcopy(current[0]))
    batches = result_store.one
    monkeypatch.setattr(result_store, 'one', lambda table, field, key, **kwargs:
        deepcopy(sources[key] if table == 'runs' else artifacts[key]) if table != 'batches'
        else batches(table, field, key, **kwargs))
    monkeypatch.setattr(result_store, 'read_many', lambda table, keys, **kwargs:
        deepcopy(reports) if keys == ['first-scene-reports'] else
        [deepcopy(case.reports[key]) for key in keys if key in case.reports])

    def save_champion(table, key, rows, **kwargs):
        if table == 'candidates':
            artifacts[key], = deepcopy(rows)
        else:
            assert table == 'search_champions' and key == original['condition_key']
            current[0], = deepcopy(rows)
    monkeypatch.setattr(result_store, 'write', save_champion)
    store = TaskStore(destination, connection=sqlite3.connect(':memory:'),
                      reusable_database=':memory:', report_locations={})
    try:
        state['formal_champion_snapshot'] = task._freeze_formal_champion(
            state, character, state['native'], state['capabilities'])
        store.state.update(state)
        task._prepare_formal_publication(store)
        task._publish_formal_champion(store, destination)
        assert store.state['formal_champion_publication']['status'] == 'published', store.state['formal_champion_publication']
        assert current[0]['source_run_id'] == 'first-scene'
        assert current[0]['samples'] > 0
        published = deepcopy(current[0])
        inherited = case.store.state
        inherited.update(run_id='next-scene', simulation_config=case.ready['simulation_config'],
            input_effective_sha256=state['input_effective_sha256'], native=state['native'],
            engines=state['engines'], capabilities=case.capabilities)
        snapshot = task._freeze_formal_champion(inherited, character, inherited['native'], case.capabilities)
        assert snapshot['status'] == 'selected'
        assert snapshot['source_run_id'] == 'first-scene'
        assert snapshot['target_count'] == targets
        inherited.update(formal_champion_snapshot=snapshot, seed_selected_snapshot=[],
            training_champion_snapshot=dict(status='not_applicable'))
        # 无效原生起点仍按原优化器拒绝；正式冠军由真实组装接线加入并实际重评分。
        task._assemble_formal_starts(inherited, [[['unmapped_native_action']]],
            character=character, configuration_key={}, capabilities=case.capabilities,
            runtime=TaskRuntime(float('inf')), use_burst=True)
        assert inherited['formal_champion_adaptation']['status'] == 'accepted'
        assert any(source['source_kind'] == 'formal_champion'
            for source in inherited['start_sources'][snapshot['behavior_identity']])
        result = case.run()
        assert result['search_result']['dps'] > 0
        assert result['search_result']['dps'] == published['score']
        task._prepare_formal_publication(case.store)
        intent = inherited['formal_champion_publication_intent']
        assert intent['expected_version'] == 1
        assert intent['expected_incumbent'] == dict(version=1, source_run_id='first-scene',
            behavior_identity=snapshot['behavior_identity'])
        record = intent['record']
        # 外部持久化响应来自本次真实GA结果；不预设完成赢家或发布状态。
        sources['next-scene'] = dict(run_id='next-scene', status=result['status'], profile=run['profile'],
            condition_key=case.condition, selected_candidate_key=result['selected_candidate_key'],
            locked_candidate_key=result['locked_candidate_key'], candidate_key=record['source_candidate_key'],
            candidate_data_key=record['source_candidate_data_key'], search_dps=result['search_result']['dps'],
            search_samples=result['search_result']['samples'], batch_keys=record['batch_keys'],
            final_scenarios=result['final']['scenarios'])
        artifacts[record['source_candidate_data_key']] = dict(run_id='next-scene',
            candidate_key=record['source_candidate_key'], program=result['candidate']['program'],
            simulation=result['candidate']['simulation'], export_text=result['candidate']['text'], source='search')
        publish = Mock(wraps=result_store.publish_search_champion)
        monkeypatch.setattr(result_store, 'publish_search_champion', publish)
        task._publish_formal_champion(case.store, destination)
        assert publish.call_count == 1
        assert publish.call_args.args[0] is record and publish.call_args.args[1] == 1
        assert publish.call_args.kwargs == dict(expected_incumbent=dict(
            version=1, source_run_id='first-scene', behavior_identity=snapshot['behavior_identity']))
        assert inherited['formal_champion_publication']['status'] == 'unchanged', inherited['formal_champion_publication']
        assert current[0] == published
    finally:
        store.close()


@pytest.mark.parametrize('race', ['version', 'incumbent'])
def test_formal_publication_rejects_stale_version_or_incumbent_without_writing(monkeypatch, race):
    from contextlib import nullcontext
    import result_store
    from champion_evidence_fixture import formal_cohort
    current, *_ = formal_cohort(source_run_id='fresh-run')
    stale, *_ = formal_cohort(source_run_id='stale-run',
        programs=[[['scourge_strike']], [['dark_transformation']]])
    monkeypatch.setattr(result_store, '_search_champion_lock', nullcontext)
    monkeypatch.setattr(result_store, 'read_search_champion', lambda key: current)
    write = Mock(side_effect=AssertionError('stale publication must not write'))
    monkeypatch.setattr(result_store, 'write', write)
    expected = (None if race == 'version' else dict(version=1, source_run_id='older-run',
        behavior_identity=current['behavior_identity']))
    result = result_store.publish_search_champion(stale, 0 if race == 'version' else 1,
                                                   expected_incumbent=expected)
    assert result['status'] == 'conflict'
    assert result['source_run_id'] == 'fresh-run' and result['version'] == 1
    write.assert_not_called()


@pytest.mark.parametrize('change', ['equipment', 'cadence', 'engine', 'targets'])
def test_dual_formal_champion_isolated_by_frozen_character_and_full_conditions(monkeypatch, change):
    import result_store
    import task
    from champion_evidence_fixture import formal_cohort
    from search import digest
    record, state, character, run, candidate, _ = formal_cohort()
    native = dict(identity=dict(spec_id=252, race=character.race))
    read = Mock(return_value=None)
    monkeypatch.setattr(result_store, 'read_search_champion', read)
    original = task._freeze_formal_champion(state, character, native, state['capabilities'])
    from copy import deepcopy
    changed = deepcopy(state)
    if change == 'equipment':
        changed['input_effective_sha256'] = 'different-equipment'
    elif change == 'targets':
        changed['simulation_config']['target_count'] = 5
        changed['condition'] = digest(dict(targets=5))
    else:
        # 正式condition已包含完整配置/引擎；冻结不得退化为只按职业查冠军。
        changed['condition'] = digest(dict(**state, **{change: 'different'}))
    second = task._freeze_formal_champion(changed, character, native, changed['capabilities'])
    assert original['status'] == second['status'] == 'absent'
    assert original['condition_key'] != second['condition_key']
    assert original['binding']['input_effective_sha256'] == 'frozen-character'
    assert second['target_count'] == (5 if change == 'targets' else 1)
    assert read.call_args.args == (second['condition_key'],)


@pytest.mark.parametrize('fault', ['none', 'profile', 'source_batch_forged'])
def test_management_checks_explicit_v1_sources_before_selecting_highest(monkeypatch, fault):
    from copy import deepcopy
    import result_store
    import task
    from champion_evidence_fixture import legacy_formal_inputs
    state, character, runs, candidates, reports = legacy_formal_inputs()
    low, high, foreign = runs
    originals = deepcopy(runs)
    state['formal_history_scope'] = [low['run_id'], high['run_id']]
    if fault == 'profile':
        high['profile']['input_effective_sha256'] = 'foreign'
    elif fault == 'source_batch_forged':
        high['batch_keys'] = list(foreign['batch_keys'])
    before = deepcopy(runs)
    calls = []
    def known_sources(table, keys, **kwargs):
        calls.append((table, list(keys)))
        if table == 'runs':
            assert keys == [low['run_id'], high['run_id']]
            return [low, high]
        if table == 'candidates':
            return candidates[:2]
        assert table == 'batches'
        return [row for row in reports if row['batch_key'] in keys]
    monkeypatch.setattr(result_store, 'read_many', known_sources)
    monkeypatch.setattr(result_store, 'report_locations', lambda keys: {})
    monkeypatch.setattr(result_store, 'read_search_champion', lambda key: None)
    write = Mock(side_effect=AssertionError('history selection must not publish'))
    query = Mock(side_effect=AssertionError('history selection must not scan tables'))
    monkeypatch.setattr(result_store, 'write', write)
    monkeypatch.setattr(result_store, 'query', query)
    native = dict(identity=dict(spec_id=252, race=character.race))
    snapshot = task._freeze_formal_champion(state, character, native, state['capabilities'])
    if fault == 'none':
        selected = task._historical_formal_champion(state, character, native, state['capabilities'], snapshot)
        assert selected['legacy_import_status'] == 'candidate_frozen'
        assert selected['source_scope'] == [low['run_id'], high['run_id']]
        assert selected['source_run_id'] == high['run_id']
        assert selected['score'] == 300.
        assert selected['source_condition_key'] != selected['binding']['condition']
        with pytest.raises(task.TaskError, match='已有正式冠军'):
            task._historical_formal_champion(state, character, native, state['capabilities'], selected)
        assert runs == originals
    else:
        with pytest.raises((task.TaskError, ValueError)):
            task._historical_formal_champion(state, character, native, state['capabilities'], snapshot)
    assert runs == before
    write.assert_not_called()
    query.assert_not_called()


def test_management_import_deduplicates_explicit_scope_and_rejects_65_sources(monkeypatch):
    from contextlib import nullcontext
    import seed_activity
    import task
    execute = Mock(return_value='accepted')
    monkeypatch.setattr(seed_activity, 'foreground_search', nullcontext)
    monkeypatch.setattr(task, '_run_task', execute)
    assert task.import_formal_champion('input', 'output', ['a' * 32, 'b' * 32, 'b' * 32]) == 'accepted'
    assert execute.call_args.kwargs['_formal_source_run_ids'] == ['a' * 32, 'b' * 32]
    execute.reset_mock()
    with pytest.raises(task.TaskError, match='64'):
        task.import_formal_champion('input', 'output', [f'{index:032x}' for index in range(65)])
    execute.assert_not_called()


@pytest.mark.parametrize('fault', ['corrupt_champion', 'temporary_read', 'corrupt_candidate',
    'temporary_candidate_read', 'source_program'])
def test_dual_formal_champion_read_errors_remain_visible_and_do_not_overwrite_the_incumbent(monkeypatch, fault):
    from copy import deepcopy
    from unittest.mock import Mock
    import result_store
    import task
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, _ = formal_cohort()
    original = deepcopy(record)
    read = Mock(return_value=record)
    one = Mock(side_effect=[run, candidate])
    if fault in ('corrupt_champion', 'temporary_read'):
        read.side_effect = (result_store.InvalidRecordError('corrupt incumbent') if fault == 'corrupt_champion'
                            else result_store.DataReadError('temporarily unreadable incumbent'))
    elif fault == 'corrupt_candidate':
        one.side_effect = [run, result_store.InvalidRecordError('corrupt candidate')]
    elif fault == 'temporary_candidate_read':
        one.side_effect = [run, result_store.DataReadError('temporarily unreadable candidate')]
    else:
        candidate['program'] = {}
    monkeypatch.setattr(result_store, 'read_search_champion', read)
    monkeypatch.setattr(result_store, 'one', one)
    write = Mock(side_effect=AssertionError('只读冻结不得改写冠军'))
    monkeypatch.setattr(result_store, 'write', write)
    with pytest.raises((result_store.DataReadError, ValueError)):
        task._freeze_formal_champion(state, character,
            dict(identity=dict(spec_id=252, race=character.race)), state['capabilities'])
    assert record == original
    write.assert_not_called()


@pytest.mark.parametrize('version', [None, 1, 2])
def test_formal_source_consumes_only_supported_explicit_contracts(version):
    import task
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, _ = formal_cohort()
    if version is None:
        record.pop('contract_version')
    else:
        record['contract_version'] = version
    evidence = task._validate_formal_source(record, state, character, run=run,
        candidate=candidate, verify_reports=False)
    assert evidence['status'] == 'completed'


@pytest.mark.parametrize('version', [True, 0, 3, '2'])
def test_formal_source_rejects_unknown_or_noninteger_contract_versions(version):
    import task
    import result_store
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, _ = formal_cohort()
    record['contract_version'] = version
    with pytest.raises(result_store.InvalidRecordError, match='契约版本'):
        task._validate_formal_source(record, state, character, run=run,
            candidate=candidate, verify_reports=False)


@pytest.mark.parametrize('fault', ['winner', 'samples', 'batch_key', 'request', 'score',
    'report_missing', 'report_duplicate', 'report_identity', 'report_score', 'source_profile', 'source_program'])
def test_formal_champion_requires_complete_request_reports_and_matching_source(monkeypatch, fault):
    import result_store
    import task
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, reports = formal_cohort()
    if fault == 'winner': record['behavior_identity'] = record['evaluation']['finalists'][0]['key']
    elif fault == 'samples': record['samples'] = 380
    elif fault == 'batch_key': record['batch_keys'].pop()
    elif fault == 'request': record['evaluation']['finalists'][0]['batches'][0]['request']['iterations'] = 127
    elif fault == 'score': record['evaluation']['finalists'][0]['score'] = 999.
    elif fault == 'report_missing': reports.pop()
    elif fault == 'report_duplicate': reports.append(reports[0])
    elif fault == 'report_identity': reports[0]['input_seed'] += 1
    elif fault == 'report_score': reports[0]['report']['sim']['players'][0]['collected_data']['dps']['mean'] = 999.
    elif fault == 'source_profile': run['profile']['input_effective_sha256'] = 'foreign'
    else: candidate['program'] = {}
    monkeypatch.setattr(result_store, 'report_locations', lambda keys: {})
    monkeypatch.setattr(result_store, 'read_many', lambda *args, **kwargs: reports)
    with pytest.raises((result_store.InvalidRecordError, ValueError)):
        task._validate_formal_source(record, state, character, run=run, candidate=candidate)


def test_formal_champion_validates_all_six_original_reports_without_a_center(monkeypatch):
    import result_store
    import task
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, reports = formal_cohort()
    monkeypatch.setattr(result_store, 'report_locations', lambda keys: {})
    monkeypatch.setattr(result_store, 'read_many', lambda *args, **kwargs: reports)
    assert task._validate_formal_source(record, state, character, run=run,
        candidate=candidate)['status'] == 'completed'
    assert record['score'] == 200. and record['samples'] == 381
    assert len(reports) == 6


def test_formal_snapshot_freezes_the_verified_published_version_without_rewriting_it(monkeypatch):
    from copy import deepcopy
    import result_store
    import task
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, _ = formal_cohort()
    before = deepcopy(record)
    monkeypatch.setattr(result_store, 'read_search_champion', Mock(return_value=record))
    monkeypatch.setattr(result_store, 'one', Mock(side_effect=[run, candidate]))
    write = Mock(side_effect=AssertionError('冻结来源不能发布或修改记录'))
    monkeypatch.setattr(result_store, 'write', write)
    snapshot = task._freeze_formal_champion(state, character,
        dict(identity=dict(spec_id=252, race=character.race)), state['capabilities'])
    assert snapshot['status'] == 'selected'
    assert snapshot['version'] == 1 and snapshot['source_run_id'] == 'source-run'
    assert snapshot['score'] == 200. and snapshot['samples'] == 381
    assert snapshot['evaluation']['finalist_keys'] == record['evaluation']['finalist_keys']
    assert record == before
    write.assert_not_called()


@pytest.mark.parametrize('fault', ['search_version', 'failure_policy_version', 'engines', 'generations',
    'stagnant', 'promotion', 'duplicate_finalist', 'retest_count', 'sample_type', 'nonfinite_score'])
def test_formal_champion_rejects_changed_algorithm_or_incomplete_retest_contract(fault):
    import formal_search
    import result_store
    from champion_evidence_fixture import formal_cohort
    record, state, character, _, _, _ = formal_cohort()
    evaluation = record['evaluation']
    if fault == 'search_version': evaluation['search']['version'] = True
    elif fault == 'failure_policy_version': evaluation['search']['coarse_failure_policy']['version'] = True
    elif fault == 'engines': evaluation['engines'] = {'controlled': 'foreign'}
    elif fault == 'generations': evaluation['complete_generations'] = 1
    elif fault == 'stagnant': evaluation['stagnant'] = 1
    elif fault == 'promotion': record['promotion_evidence'] = ['old-ci-promotion']
    elif fault == 'duplicate_finalist': evaluation['finalists'].append(evaluation['finalists'][0])
    elif fault == 'retest_count': evaluation['finalists'][0]['batches'].pop()
    elif fault == 'sample_type': evaluation['finalists'][0]['batches'][0]['samples'] = True
    else: evaluation['finalists'][0]['batches'][0]['dps'] = float('nan')
    with pytest.raises(result_store.InvalidRecordError):
        formal_search.validate_evidence(record, state, character, verify_reports=False)
