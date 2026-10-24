"""正式冠军通过公开双场入口、真实隔离持久中心保留。"""
import pytest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from test_burst import page_task_engine, reviewed_fixture
from test_seed_training import memory_result_center
from test_training_champion import champion_engine, completed_training, dual_result


def test_dual_inherits_each_scenes_formal_champion_after_publication(tmp_path,
        champion_engine):
    import burst
    import result_store
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    assert [scene['formal_champion_publication']['status'] for scene in first['scenes']] == [
        'published', 'published']
    for scene in first['scenes']:
        champion = result_store.read_search_champion(scene['formal_champion_snapshot']['condition_key'])
        assert champion['source_run_id'] == scene['formal_champion_publication']['source_run_id']
        assert scene['search_result']['samples'] > 0

    import engine
    inspect = engine.inspect

    def invalid_native(*args, **kwargs):
        capabilities = inspect(*args, **kwargs)
        capabilities['baseline_actions'] = capabilities['actions'] + [dict(kind='spell',
            spell_id=999999, simc_action='unmapped_native_action', name='unmapped', gcd_ms=1500)]
        return capabilities

    with patch.object(engine, 'inspect', invalid_native):
        second = dual_result(tmp_path / 'second', raw, candidate_limit=1)
    assert len(second['scenes']) == len(first['scenes'])
    for previous, scene in zip(first['scenes'], second['scenes']):
        snapshot = scene['formal_champion_snapshot']
        assert snapshot['status'] == 'selected'
        assert snapshot['source_run_id'] == previous['formal_champion_publication']['source_run_id']
        assert snapshot['target_count'] == scene['target_count']
        assert scene['formal_champion_adaptation']['status'] == 'accepted'
        assert scene['formal_champion_adaptation']['current_score'] > 0
        assert scene['search_result']['dps'] == previous['search_result']['dps']
        assert scene['formal_champion_publication']['status'] == 'unchanged'
        sources = scene['start_sources'][snapshot['behavior_identity']]
        assert any(source['source_kind'] == 'formal_champion' for source in sources)


def test_dual_preserves_legacy_ten_source_paths_and_replaces_champion_after_complete_retests(tmp_path,
        monkeypatch, memory_result_center, champion_engine):
    import burst
    import engine
    import result_store
    import seed_training
    import sequence
    import task
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    reference = engine.reference

    def four_native_sources(*args, **kwargs):
        native = reference(*args, **kwargs)
        native['action_sequence'] = [dict(name=name, queue_failed=False) for name in
            ['outbreak'] * 3 + ['death_coil'] * 2 + ['scourge_strike']]
        return native

    with patch.object(engine, 'reference', four_native_sources):
        former = [['death_coil']] * 6 + [dict(kind='WaitClicks', clicks=2), ['outbreak']]
        challenger = [['death_coil']] * 7 + [dict(kind='WaitClicks', clicks=3), ['outbreak']]
        from program import canonicalize_search_program
        from test_search import _fast_capabilities
        grades = {canonicalize_search_program(program, _fast_capabilities())['identity']: score
                  for program, score in ((former, 200.), (challenger, 300.))}
        evaluate = sequence.evaluate
        def source_scores(profile, candidate, folder, **kwargs):
            return evaluate(profile, candidate, folder,
                score=grades.get(sequence.behavior_key(candidate), 100.), **kwargs)
        monkeypatch.setattr(sequence, 'evaluate', source_scores)
        template, _ = completed_training(tmp_path, 1, [(former, [200.] * 3)])
        monkeypatch.setattr(engine, '_training_template', lambda manifest: template)
        first = dual_result(tmp_path / 'first', raw, candidate_limit=10, validation_batches=2)
        _, rows = completed_training(tmp_path, 1, [(challenger, [300.] * 3)], name='later')
        engines = {mode: engine.identity(mode)[1] for mode in ('baseline', 'controlled')}
        selected = [dict(configuration_key=rows[0]['configuration_key'], candidate_id='selected-' + str(index), condition=rows[0]['condition'],
            class_name='deathknight', spec='unholy', targets=1,
            program=[['outbreak'], dict(kind='WaitClicks', clicks=2 + index), ['death_coil']],
            family='family-' + str(index), score=100., scores=[100.] * 3,
            template_sha256='selected-template', engines=engines) for index in range(4)]
        result_store.write('seed_selected', seed_training.shared_scope(rows[0]['configuration_key']), selected,
                           schema=seed_training.SELECTED_SCHEMA)
        second = dual_result(tmp_path / 'second', raw, candidate_limit=10, validation_batches=2)
        scene = second['scenes'][0]
        assert len(scene['start_sources']) == 10
        groups = [source for values in scene['start_sources'].values() for source in values]
        assert [sum(source['source_kind'] == kind for source in groups) for kind in
                ('native', 'seed_selected', 'training_champion', 'formal_champion')] == [4, 4, 1, 1]
        # Legacy v1 has ten source paths; the shared GA uses the legal deduplicated pool.
        folder, = (tmp_path / 'second' / 'page' / 'tasks').glob('*/single_target')
        saved = task.read_task(folder, include_search_records=True)
        assert saved['search']['chains'] == []
        assert saved['search']['stop_reason'] == 'stagnation'
        assert saved['stop_policy'] == dict(version=1, kind='natural_stagnation')
        assert saved['search_result']['dps'] == 300.
        assert scene['formal_champion_publication']['status'] == 'published'
        assert scene['formal_champion_publication']['source_run_id'] != first['scenes'][0][
            'formal_champion_publication']['source_run_id']
        champion = result_store.read_search_champion(scene['formal_champion_snapshot']['condition_key'])
        assert champion['contract_version'] == 2
        assert champion['promotion_evidence'] == []
        assert champion['evaluation']['complete_generations'] >= 2
        assert all(len(row['batches']) == 3 and row['samples'] == 381
                   for row in champion['evaluation']['finalists'])


def test_dual_stale_task_cannot_replace_a_newly_published_distinct_champion(tmp_path,
        memory_result_center, champion_engine):
    import burst
    import engine
    import json
    import result_store
    import threading
    import task
    from concurrent.futures import ThreadPoolExecutor
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    profile = tmp_path / 'role.simc'
    profile.write_text(raw, encoding='utf-8', newline='')
    options = dict(use_burst=True, simulation_config=dict(target_count=1, scene='single_target'),
        search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1, final_batches=1, final_iterations=2,
            scenarios=('nominal',)))
    import search
    inspect, initial_programs = engine.inspect, search.initial_programs
    stale_ids = set()
    waiting, release = threading.Event(), threading.Event()
    api = result_store._api()

    def observe_stale_run(native, folder, **kwargs):
        capabilities = inspect(native, folder, **kwargs)
        folder = Path(folder)
        if 'stale' in folder.parts:
            stale_ids.add(json.loads((folder.parent / 'profile.json').read_text(encoding='utf-8'))['run_id'])
        return capabilities

    def another_native_start(capabilities, *args, **kwargs):
        from program import canonicalize_search_program
        starts = initial_programs(capabilities, *args, **kwargs)
        assert len(starts) > 1
        assert canonicalize_search_program(starts[0], capabilities)['identity'] != (
            canonicalize_search_program(starts[1], capabilities)['identity'])
        return starts[1:] + starts[:1]

    def held_result_write(root, table, key, rows, **kwargs):
        if table == 'runs' and key in stale_ids and not release.is_set():
            waiting.set()
            if not release.wait(20):
                raise AssertionError('fresh task did not publish')
        return api['write'](root, table, key, rows, **kwargs)

    with patch.object(engine, 'inspect', observe_stale_run), \
         patch.object(result_store, '_api', return_value=dict(api, write=held_result_write)), \
         ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(dual_result, tmp_path / 'stale', raw, 1)
        try:
            assert waiting.wait(20)
            with patch.object(search, 'initial_programs', side_effect=another_native_start):
                fresh = task.run_task(profile, tmp_path / 'fresh', **options)
                assert fresh['status'] == 'completed', fresh
        finally:
            release.set()
        stale = pending.result(20)
    assert stale['scenes'][0]['formal_champion_snapshot']['condition_key'] == fresh['search'][
        'formal_champion_snapshot']['condition_key']
    assert stale['scenes'][0]['formal_champion_snapshot']['status'] == 'absent'
    assert stale['scenes'][0]['formal_champion_publication']['status'] == 'conflict'
    assert stale['scenes'][0]['search_result']['samples'] > 0
    inherited = task.run_task(profile, tmp_path / 'inherited', **options)
    assert inherited['status'] == 'completed', inherited
    assert inherited['search']['formal_champion_snapshot']['condition_key'] == fresh['search'][
        'formal_champion_snapshot']['condition_key']
    assert inherited['search']['formal_champion_snapshot']['source_run_id'] == fresh['search'][
        'formal_champion_publication']['source_run_id']


def test_public_resume_publishes_a_saved_winner_before_completion_or_budget_early_return(tmp_path,
        champion_engine):
    import burst
    import result_store
    import sequence
    import task
    from search import TaskStore
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    api = result_store._api()
    profile = tmp_path / 'role.simc'
    profile.write_text(raw, encoding='utf-8')
    folder = tmp_path / 'single_target'

    def fail_champion(root, table, key, rows, **kwargs):
        if table == 'search_champions':
            raise OSError('saved winner awaiting publication')
        return api['write'](root, table, key, rows, **kwargs)

    with patch.object(result_store, '_api', return_value=dict(api, write=fail_champion)):
        task.run_task(profile, folder, use_burst=True,
            simulation_config=dict(target_count=1, scene='single_target'),
            search_config=dict(input_interval_ms=200, candidate_limit=1, batch_targets=(2,),
                iterations=2, validation_batches=1, final_batches=1, final_iterations=2,
                scenarios=('nominal',)))
    previous = task.read_task(folder)
    assert previous['status'] == 'completed'
    store = TaskStore(folder)
    try:
        store.state['elapsed_seconds'] = 600.
        store.save()
    finally:
        store.close()
    with patch.object(sequence, 'evaluate', lambda *args, **kwargs: pytest.fail('补发布重新评分')):
        resumed = task.resume_task(folder, simulation_config=previous['simulation_config'])
        assert resumed['search']['formal_champion_publication']['status'] == 'published'
        assert resumed['search_result'] == previous['search_result']
        assert resumed['completed_batches'] == previous['completed_batches']
        again = task.resume_task(folder, simulation_config=previous['simulation_config'])
        assert again['search']['formal_champion_publication'] == resumed['search']['formal_champion_publication']
        assert again['search']['formal_champion_snapshot'] == previous['search']['formal_champion_snapshot']


def test_dual_formal_champion_isolated_by_frozen_character_and_full_conditions(tmp_path,
        memory_result_center, champion_engine, subtests):
    import burst
    import engine
    import result_store
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    assert first['input_interval_ms'] == 200
    originals = {scene['formal_champion_snapshot']['condition_key']:
        result_store.read_search_champion(scene['formal_champion_snapshot']['condition_key'])
        for scene in first['scenes']}
    identity = engine.identity
    for change in ('equipment', 'cadence', 'engine'):
        with subtests.test(change=change):
            with ExitStack() as condition_patches:
                case_raw, interval = raw, 200
                if change == 'equipment':
                    case_raw = raw.replace('id=273795', 'id=273795,bonus_id=1')
                elif change == 'cadence':
                    # 250ms keeps the 1000ms fixture GCD and burst pause representable.
                    # 400ms would leave one empty input at 2800ms before the 4000ms resume.
                    interval = 250
                else:
                    condition_patches.enter_context(patch.object(engine, 'identity', lambda *args, **kwargs:
                        (lambda value: (value[0], dict(value[1], constructed_identity='different')))(identity(*args, **kwargs))))
                second = dual_result(tmp_path / ('second-' + change), case_raw,
                    candidate_limit=1, interval_ms=interval)
                assert second['input_interval_ms'] == interval
                assert all(scene['formal_champion_snapshot']['status'] == 'absent' for scene in second['scenes'])
                assert [scene['formal_champion_snapshot']['condition_key'] for scene in first['scenes']] != [
                    scene['formal_champion_snapshot']['condition_key'] for scene in second['scenes']]
            assert engine.identity is identity
            assert {key: result_store.read_search_champion(key) for key in originals} == originals


def _legacy_formal_source(folder, raw, program, score, *, targets=1):
    """只构造已完成旧 v1 来源及原请求报告，不执行或伪装新 GA。"""
    import json
    import uuid
    from dataclasses import replace
    import burst
    import engine
    import result_store
    import simulation_config
    import task
    from program import canonicalize_search_program, compile_program
    from runtime import TaskRuntime
    from sequence import compiled_identity
    from search import config_for, digest, input_times, STATS_VERSION
    from test_search import _fast_report
    folder.mkdir(parents=True)
    for name in ('input.original.simc', 'input.simc'):
        (folder / name).write_text(raw, encoding='utf-8')
    character = replace(task.parse_character(raw), spec_id=252)
    run_id = uuid.uuid4().hex
    config = config_for(dict(candidate_limit=1, batch_targets=(2,), iterations=2,
        validation_batches=1, final_batches=1, final_iterations=2,
        scenarios=('nominal',), input_interval_ms=200), legacy=True)
    simulation = simulation_config.config_for(dict(target_count=targets,
        scene='single_target' if targets == 1 else 'aoe'))
    runtime = TaskRuntime(600)
    native = engine.reference(folder / 'input.simc', folder / 'reference', character,
        runtime=runtime, simulation_config=simulation)
    _, capabilities, context = engine.prepare_loop(native, character, folder, runtime,
        definition=burst.load(252), interval_ms=200)
    canonical = canonicalize_search_program(program, capabilities)
    candidate = compile_program(canonical['program'], folder / 'export', identity=native['identity'],
        runtime=runtime, capabilities=capabilities)
    candidate['simulation'] = 'passed_native_model'
    condition = digest(dict(legacy='local-search-v1', source=run_id))
    seed = config['random_seed']
    times, sources = burst.combined_inputs(input_times('nominal', seed + 500000, 200), context, 200)
    request = dict(condition=condition, program=canonical['form'], behavior_identity=canonical['identity'],
        purpose='search', seed=seed, input_seed=seed + 500000, iterations=2,
        times=times, stats=STATS_VERSION, trace=False, reset_events=[])
    request['burst'] = dict(definition_id=context['definition_id'],
        program=compiled_identity(context['candidate']), plan=context['plan'], interval_ms=200, sources=sources)
    key = digest(request)
    report = _fast_report(character, score, 1)
    report['sim']['targets'] *= targets
    result_store.write('batches', key, [result_store.prepare_batch(dict(batch_key=key,
        run_id=run_id, condition_key=condition, candidate_key=canonical['identity'],
        program_identity=json.dumps(canonical['form'], ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        purpose='search', seed=seed, input_seed=seed + 500000, batch_index=0,
        scenario='nominal', stats_version=STATS_VERSION, times=times, trace=False,
        iterations=2, requested_iterations=2, dps=score, samples=1, variance=0., report=report))])
    (folder / 'profile.json').write_text(json.dumps(task._profile(character, raw, run_id=run_id)), encoding='utf-8')
    state = dict(condition=condition, config=config, simulation_config=simulation,
        engines={mode: engine.identity(mode)[1] for mode in ('baseline', 'controlled')}, burst=context)
    task._store_run(folder, dict(status='completed', phase='done', candidate=candidate,
        selected_candidate_key=canonical['identity'], locked_candidate_key=canonical['identity'],
        search_result=dict(dps=score, samples=1), search=dict(records=[dict(batches=[dict(data_key=key)])])), state=state)
    return run_id


def test_management_selects_the_highest_within_two_known_old_rule_sources_and_rejects_missing_proof(
        tmp_path, monkeypatch, memory_result_center, champion_engine, subtests):
    from copy import deepcopy
    import burst
    import engine
    import json
    import result_store
    import sequence
    import task
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    api = result_store._api()
    profile = tmp_path / 'current.simc'
    profile.write_bytes(raw.encode('utf-8'))
    options = dict(use_burst=True, simulation_config=dict(target_count=1, scene='single_target'),
        search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2,
        validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',), input_interval_ms=200))
    low_id = _legacy_formal_source(tmp_path / 'low', raw, [['outbreak'], ['death_coil']], 200.)
    high_id = _legacy_formal_source(tmp_path / 'high', raw, [['outbreak'], ['scourge_strike']], 300.)
    foreign_id = _legacy_formal_source(tmp_path / 'foreign', raw,
        [['outbreak'], ['scourge_strike']], 300., targets=5)
    def normalized(row):
        return {key: json.loads(value) if result_store.RUN_SCHEMA[key] == 'JSON'
                and isinstance(value, str) else value for key, value in row.items()}

    originals = {run_id: normalized(result_store.read_records('runs', run_id)[0])
                 for run_id in (low_id, high_id)}
    for fault in ('profile', 'source_batch_forged'):
        with subtests.test(fault=fault):
            run = deepcopy(originals[high_id])
            champion_writes = []

            def observed_write(root, table, key, rows, **kwargs):
                if table == 'search_champions':
                    champion_writes.append(key)
                    raise AssertionError('rejected history attempted champion publication')
                return api['write'](root, table, key, rows, **kwargs)

            try:
                with monkeypatch.context() as scoped:
                    if fault == 'profile':
                        run['profile']['input_effective_sha256'] = 'foreign'
                    else:
                        locations = result_store.report_locations(run['batch_keys'])
                        groups = list(dict.fromkeys(locations.get(key) or key for key in run['batch_keys']))
                        source_batches = [row for row in result_store.read_many('batches', groups,
                            filters={'candidate_key': run['selected_candidate_key'], 'purpose': 'search'})
                            if row['batch_key'] in run['batch_keys']]
                        assert len(source_batches) == 1
                        run['batch_keys'].remove(source_batches[0]['batch_key'])
                        foreign = result_store.read_records('runs', foreign_id)[0]
                        locations = result_store.report_locations(foreign['batch_keys'])
                        groups = list(dict.fromkeys(locations.get(key) or key for key in foreign['batch_keys']))
                        foreign_batches = [row for row in result_store.read_many('batches', groups,
                            filters={'candidate_key': run['selected_candidate_key'], 'purpose': 'search'})
                            if row['batch_key'] in foreign['batch_keys']]
                        assert len(foreign_batches) == 1
                        run['batch_keys'].append(foreign_batches[0]['batch_key'])
                    result_store.write('runs', high_id, [run], schema=result_store.RUN_SCHEMA)
                    scoped.setattr(result_store, '_api', lambda: dict(api, write=observed_write))
                    with pytest.raises(task.TaskError):
                        task.import_formal_champion(profile, tmp_path / ('rejected-' + fault),
                            [low_id, high_id], **options)
                    assert champion_writes == [], 'rejected history changed a formal champion'
                    assert normalized(result_store.read_records('runs', low_id)[0]) == originals[low_id]
                    assert normalized(result_store.read_records('runs', high_id)[0]) == run
            finally:
                for run_id, original_row in originals.items():
                    result_store.write('runs', run_id, [deepcopy(original_row)], schema=result_store.RUN_SCHEMA)
            assert result_store._api() is api
            assert {run_id: normalized(result_store.read_records('runs', run_id)[0])
                    for run_id in (low_id, high_id)} == originals
    def known_only(root, sql, parameters=None, *, tables):
        if {'runs', 'candidates'} & set(tables):
            raise AssertionError('历史导入扫描了全表')
        return api['query'](root, sql, parameters, tables=tables)

    # Successful publication comes last, so it cannot bypass any preceding source rejection.
    with subtests.test(fault='none'):
        with patch.object(result_store, '_api', return_value=dict(api, query=known_only)):
            task.import_formal_champion(profile, tmp_path / 'imported', [low_id, high_id, high_id], **options)
        saved = task.read_task(tmp_path / 'imported')
        snapshot = saved['search']['formal_champion_snapshot']
        assert snapshot['legacy_import_status'] == 'candidate_frozen'
        assert snapshot['source_run_id'] == high_id
        assert snapshot['source_scope'] == [low_id, high_id]
        assert snapshot['score'] == 300.
        assert snapshot['source_condition_key'] != snapshot['binding']['condition']
        assert saved['search_result']['dps'] != 300.
        assert saved['search']['formal_champion_publication']['status'] == 'published'
        champion = result_store.read_search_champion(snapshot['condition_key'])
        with pytest.raises(task.TaskError, match='已有正式冠军'):
            task.import_formal_champion(profile, tmp_path / 'must-not-replace', [high_id], **options)
        assert result_store.read_search_champion(snapshot['condition_key']) == champion
        with pytest.raises(task.TaskError, match='64'):
            task.import_formal_champion(profile, tmp_path / 'too-many', [f'{index:032x}' for index in range(65)])
        assert {run_id: normalized(result_store.read_records('runs', run_id)[0])
                for run_id in (low_id, high_id)} == originals


@pytest.mark.parametrize('stage', ['complete_winner', 'partial_first_batch'])
def test_dual_cancel_freezes_formal_champion_and_never_publishes_a_partial_batch(tmp_path,
        monkeypatch, memory_result_center, champion_engine, stage):
    import burst
    import result_store
    import sequence
    from runtime import TaskCancelled
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    key = first['scenes'][0]['formal_champion_snapshot']['condition_key']
    incumbent = result_store.read_search_champion(key)
    evaluate = sequence.evaluate
    cancelled = [False]

    def interrupt(*args, **kwargs):
        if not cancelled[0]:
            cancelled[0] = True
            if stage == 'partial_first_batch':
                raise TaskCancelled('constructed partial first batch')
            result = evaluate(*args, **kwargs)
            kwargs['runtime'].cancel()
            return result
        return evaluate(*args, **kwargs)

    def newer_version(previous):
        snapshot = previous['scenes'][0]['formal_champion_snapshot']
        record = result_store.read_search_champion(snapshot['condition_key'])
        assert record['source_run_id'] == first['scenes'][0]['formal_champion_publication']['source_run_id']
        assert record['version'] == snapshot['version']
        assert 'formal_champion_publication' not in previous['scenes'][0]
        assert record == incumbent
        if stage == 'partial_first_batch':
            assert 'search_result' not in previous['scenes'][0]
        record['version'] += 1
        result_store.write('search_champions', snapshot['condition_key'], [record],
                           schema=result_store.SEARCH_CHAMPION_SCHEMA)

    with patch.object(sequence, 'evaluate', side_effect=interrupt):
        resumed = dual_result(tmp_path / 'cancelled', raw, candidate_limit=1,
            expected='cancelled', before_resume=newer_version)
    assert resumed['scenes'][0]['formal_champion_snapshot'] == resumed['previous_state']['scenes'][0][
        'formal_champion_snapshot']
    assert resumed['scenes'][0]['formal_champion_publication']['status'] == 'unchanged'


def test_dual_formal_champion_read_errors_remain_visible_and_do_not_overwrite_the_incumbent(tmp_path,
        memory_result_center, champion_engine, subtests):
    import burst
    import json
    import result_store
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    snapshot = first['scenes'][0]['formal_champion_snapshot']
    original = result_store.read_search_champion(snapshot['condition_key'])
    candidate_key = original['source_candidate_data_key']
    original_candidate = result_store.read_records('candidates', candidate_key)[0]
    source_program = original_candidate['program']
    if isinstance(source_program, str):
        source_program = json.loads(source_program)
    api = result_store._api()
    for fault in ('corrupt_champion', 'temporary_read', 'corrupt_candidate',
                  'temporary_candidate_read', 'source_program'):
        with subtests.test(fault=fault):
            case_api = dict(api)
            try:
                if fault == 'corrupt_champion':
                    def unreadable(root, table, key, **kwargs):
                        if table == 'search_champions':
                            raise api['CorruptDataError']('constructed corrupt incumbent')
                        return api['read_key'](root, table, key, **kwargs)
                    case_api['read_key'] = unreadable
                elif fault == 'temporary_read':
                    def unavailable(root, table, key, **kwargs):
                        if table == 'search_champions':
                            raise OSError('constructed temporary champion read failure')
                        return api['read_key'](root, table, key, **kwargs)
                    case_api['read_key'] = unavailable
                elif fault in ('corrupt_candidate', 'temporary_candidate_read'):
                    def unreadable_candidate(root, table, key, **kwargs):
                        if table == 'candidates':
                            if fault == 'corrupt_candidate':
                                raise api['CorruptDataError']('constructed corrupt champion artifact')
                            raise OSError('constructed temporary champion artifact read failure')
                        return api['read_key'](root, table, key, **kwargs)
                    case_api['read_key'] = unreadable_candidate
                else:
                    result_store.write('candidates', candidate_key, [dict(original_candidate, program={})],
                                       schema=result_store.CANDIDATE_SCHEMA)
                with patch.object(result_store, '_api', return_value=case_api):
                    failed = dual_result(tmp_path / ('failed-' + fault), raw, candidate_limit=1, expected='failed')
                    assert failed['error']
            finally:
                if fault == 'source_program':
                    result_store.write('candidates', candidate_key, [dict(original_candidate, program=source_program)],
                                       schema=result_store.CANDIDATE_SCHEMA)
            assert result_store._api() is api
            assert result_store.read_search_champion(snapshot['condition_key']) == original
            assert result_store.read_records('candidates', candidate_key)[0] == original_candidate
