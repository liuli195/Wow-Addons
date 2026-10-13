"""正式冠军通过公开双场入口、真实隔离持久中心保留。"""
from test_training_champion import champion_engine, dual_result
from test_burst import page_task_engine, reviewed_fixture


def test_dual_retains_each_scenes_formal_champion_across_new_tasks(tmp_path,
        champion_engine):
    import burst
    import result_store
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    assert [scene['formal_champion_publication']['status'] for scene in first['scenes']] == [
        'published', 'published']
    second = dual_result(tmp_path / 'second', raw, candidate_limit=1)
    for previous, scene in zip(first['scenes'], second['scenes']):
        snapshot = scene['formal_champion_snapshot']
        assert snapshot['status'] == 'selected'
        assert snapshot['source_run_id'] == previous['formal_champion_publication']['source_run_id']
        assert snapshot['target_count'] == scene['target_count']
        assert scene['formal_champion_adaptation']['current_score'] > 0
        assert scene['formal_champion_publication']['status'] == 'unchanged'
        sources = scene['start_sources'][snapshot['behavior_identity']]
        assert any(source['source_kind'] == 'formal_champion' for source in sources)


import pytest
from pathlib import Path
from unittest.mock import patch
from test_seed_training import memory_result_center
from test_training_champion import completed_training


@pytest.mark.parametrize('fault', ['champion_write', 'publication_pointer'])
def test_dual_saved_results_survive_publication_failure_and_resume_without_scoring(tmp_path,
        monkeypatch, champion_engine, fault):
    import burst
    import result_store
    import sequence
    import os
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    api = result_store._api()
    failing = [True]
    replace = os.replace

    def publish_write(root, table, key, rows, **kwargs):
        if table == 'search_champions' and failing[0] and fault == 'champion_write':
            raise OSError('constructed champion publication failure')
        return api['write'](root, table, key, rows, **kwargs)

    def pointer_replace(source, destination):
        destination = Path(destination)
        if fault == 'publication_pointer' and failing[0] and destination.name == 'result.json':
            payload = __import__('json').loads(Path(source).read_text(encoding='utf-8'))
            if payload.get('formal_champion_publication', {}).get('status') == 'published':
                raise OSError('constructed publication pointer failure')
        return replace(source, destination)

    def restore(saved):
        failing[0] = False
        assert all(scene['search_result']['samples'] > 0 for scene in saved['scenes'])
        monkeypatch.setattr(sequence, 'evaluate', lambda *args, **kwargs:
            pytest.fail('补发布重复启动评分'))

    with patch.object(result_store, '_api', return_value=dict(api, write=publish_write)), \
         patch.object(os, 'replace', side_effect=pointer_replace):
        state = dual_result(tmp_path, raw, candidate_limit=1, before_resume=restore)
    assert all(scene['formal_champion_publication']['status'] == 'published' for scene in state['scenes'])
    assert [scene['search_result'] for scene in state['scenes']] == [
        scene['search_result'] for scene in state['previous_state']['scenes']]
    assert [scene['elapsed_seconds'] for scene in state['scenes']] == [
        scene['elapsed_seconds'] for scene in state['previous_state']['scenes']]


def test_dual_keeps_a_valid_formal_baseline_when_one_native_start_is_invalid(tmp_path,
        monkeypatch, memory_result_center, champion_engine):
    import burst
    import result_store
    import engine
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    inspect = engine.inspect

    def invalid_native(*args, **kwargs):
        capabilities = inspect(*args, **kwargs)
        capabilities['baseline_actions'] = capabilities['actions'] + [dict(kind='spell',
            spell_id=999999, simc_action='unmapped_native_action', name='unmapped', gcd_ms=1500)]
        return capabilities

    monkeypatch.setattr(engine, 'inspect', invalid_native)
    second = dual_result(tmp_path / 'second', raw, candidate_limit=1)
    assert all(scene['formal_champion_adaptation']['status'] == 'accepted' for scene in second['scenes'])
    assert [scene['search_result']['dps'] for scene in second['scenes']] == [
        scene['search_result']['dps'] for scene in first['scenes']]
    assert all(scene['formal_champion_publication']['status'] == 'unchanged' for scene in second['scenes'])


@pytest.mark.parametrize('former_count,challenger_count,validation_batches,path_count,publication', [
    (6, 12, 1, 9, 'unchanged'), (20, 30, 2, 10, 'published')])
def test_dual_deduplicates_sources_and_replaces_only_after_trusted_promotion(tmp_path,
        monkeypatch, memory_result_center, champion_engine, former_count, challenger_count,
        validation_batches, path_count, publication):
    import burst
    import engine
    import result_store
    import seed_training
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

    monkeypatch.setattr(engine, 'reference', four_native_sources)
    former = [['death_coil']] * former_count + [dict(kind='WaitClicks', clicks=17), ['outbreak']]
    template, _ = completed_training(tmp_path, 1, [(former, [200.] * 3)])
    monkeypatch.setattr(engine, 'training_template', lambda: template)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=10, validation_batches=validation_batches)
    challenger = [['death_coil']] * challenger_count + [dict(kind='WaitClicks', clicks=88), ['outbreak']]
    _, rows = completed_training(tmp_path, 1, [(challenger, [300.] * 3)], name='later')
    engines = {mode: engine.identity(mode)[1] for mode in ('baseline', 'controlled')}
    selected = [dict(candidate_id='selected-' + str(index), condition=rows[0]['condition'],
        class_name='deathknight', spec='unholy', targets=1,
        program=[['outbreak'], dict(kind='WaitClicks', clicks=100 + index), ['death_coil']],
        family='family-' + str(index), score=100., scores=[100.] * 3,
        template_sha256='selected-template', engines=engines) for index in range(4)]
    result_store.write('seed_selected', 'deathknight-unholy-1-burst', selected,
                       schema=seed_training.SELECTED_SCHEMA)
    second = dual_result(tmp_path / 'second', raw, candidate_limit=10, validation_batches=validation_batches)
    scene = second['scenes'][0]
    assert len(scene['start_sources']) == path_count
    groups = [source for values in scene['start_sources'].values() for source in values]
    assert [sum(source['source_kind'] == kind for source in groups) for kind in
            ('native', 'seed_selected', 'training_champion', 'formal_champion')] == [4, 4, 1, 1]
    # Equal behaviors retain every source, with only successful distinct lanes counted.
    folders = list((tmp_path / 'second' / 'page' / 'tasks').glob('*/single_target'))
    saved = task.read_task(folders[0], include_search_records=True)
    assert len(saved['search']['chains']) == saved['search']['no_improvement_round_limit'] == path_count
    assert saved['config']['total_budget_seconds'] == 600
    assert scene['formal_champion_publication']['status'] == publication
    assert (scene['formal_champion_publication']['source_run_id'] != first['scenes'][0][
        'formal_champion_publication']['source_run_id']) == (publication == 'published')
    import math
    from search import TaskStore
    from runtime import TaskCancelled
    from program import canonicalize_search_program
    incumbent = result_store.read_search_champion(scene['formal_champion_snapshot']['condition_key'])
    third_root, cancel_once, save_checkpoint = (tmp_path / 'third').resolve(), [True], TaskStore.save

    def stop_after_saved_baseline(store):
        saved = save_checkpoint(store)
        if cancel_once[0] and third_root in store.destination.parents and store.state.get('archive'):
            cancel_once[0] = False
            assert len(store.state['archive']) == 1
            row = store.state['archive'][0]
            assert row['key'] == canonicalize_search_program(
                row['program'], store.state['capabilities'])['identity'] == incumbent['behavior_identity']
            assert store.state['formal_champion_snapshot']['condition_key'] == incumbent['condition_key']
            assert store.state['formal_champion_adaptation']['status'] == 'accepted'
            assert math.isfinite(row['score']) and row['batches']
            assert all(batch['status'] == 'success' and batch['samples'] > 0
                       and batch['request']['condition'] == store.state['condition']
                       and batch['request']['behavior_identity'] == row['key'] for batch in row['batches'])
            raise TaskCancelled('third-task probe saved its complete current champion baseline')
        return saved

    try:
        with patch.object(TaskStore, 'save', stop_after_saved_baseline):
            third = dual_result(third_root, raw, candidate_limit=10,
                validation_batches=validation_batches, expected='cancelled')
    finally:
        cancel_once[0] = False
    assert third['scenes'][0]['formal_champion_adaptation']['current_score'] == third['scenes'][0]['search_result']['dps']
    assert third['scenes'][0]['formal_champion_adaptation']['current_samples'] == third['scenes'][0]['search_result']['samples'] > 0
    assert third['scenes'][0]['formal_champion_publication']['status'] == 'unchanged'
    assert result_store.read_search_champion(incumbent['condition_key']) == incumbent
    assert third['scenes'][0]['formal_champion_snapshot']['source_run_id'] == scene[
        'formal_champion_publication']['source_run_id']
    if publication == 'published':
        assert third['scenes'][0]['formal_champion_snapshot']['promotion_evidence'][0]['comparison']['ci95'][0] > 0
    else:
        assert any({source['source_kind'] for source in group} == {'native', 'formal_champion'}
                   for group in scene['start_sources'].values())


@pytest.mark.parametrize('source_rules', ['old_rules', 'same_request'])
def test_management_import_rechecks_one_known_formal_source_without_history_scanning(tmp_path,
        monkeypatch, memory_result_center, champion_engine, source_rules):
    import burst
    import result_store
    import sequence
    import task
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    api = result_store._api()

    def unavailable_champion_write(root, table, key, rows, **kwargs):
        if table == 'search_champions':
            raise OSError('retain historical result without establishing a champion')
        return api['write'](root, table, key, rows, **kwargs)

    rules = task._rule_hashes()
    source_hashes = (dict(rules, **{str(Path(task.__file__).resolve()): 'f' * 64})
                     if source_rules == 'old_rules' else rules)
    with patch.object(result_store, '_api', return_value=dict(api, write=unavailable_champion_write)), \
         patch.object(task, '_rule_hashes', return_value=source_hashes):
        historical = dual_result(tmp_path / 'old', raw, candidate_limit=1)
    source = historical['scenes'][0]['formal_champion_publication']['source_run_id']
    original_source = result_store.read_records('runs', source)[0]
    profile = tmp_path / 'current.simc'
    profile.write_bytes(raw.encode('utf-8'))
    evaluate = sequence.evaluate

    def current_score(*args, **kwargs):
        result = evaluate(*args, **kwargs)
        result['summary']['dps'] = 50.
        report = result['report']['sim']
        report['statistics']['raid_dps']['mean'] = 50.
        report['players'][0]['collected_data']['dps']['mean'] = 50.
        return result

    def known_only(root, sql, parameters=None, *, tables):
        if {'runs', 'candidates'} & set(tables):
            raise AssertionError('历史导入扫描了全表')
        return api['query'](root, sql, parameters, tables=tables)

    monkeypatch.setattr(sequence, 'evaluate', current_score)
    if source_rules == 'same_request':
        with pytest.raises(task.TaskError, match='同请求可靠报告成绩冲突'):
            task.import_formal_champion(profile, tmp_path / 'conflict', [source], use_burst=True,
                search_config=__import__('json').loads(original_source['config'])
                    if isinstance(original_source['config'], str) else original_source['config'])
        assert result_store.read_records('runs', source)[0] == original_source
        rejected = task.read_task(tmp_path / 'conflict')
        assert rejected['status'] == 'failed'
        assert result_store.read_search_champion(
            rejected['search']['formal_champion_snapshot']['condition_key']) is None
        return
    with patch.object(result_store, '_api', return_value=dict(api, query=known_only)):
        task.import_formal_champion(profile, tmp_path / 'imported', [source, source], use_burst=True,
            search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2,
                validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',),
                input_interval_ms=200))
    saved = task.read_task(tmp_path / 'imported')
    snapshot = saved['search']['formal_champion_snapshot']
    assert snapshot['legacy_import_status'] == 'candidate_frozen'
    assert snapshot['source_run_id'] == source
    assert snapshot['source_scope'] == [source]
    assert saved['search_result']['dps'] == 50.
    assert saved['search']['formal_champion_publication']['status'] == 'published'
    assert snapshot['score'] == historical['scenes'][0]['search_result']['dps'] != 50.
    with pytest.raises(task.TaskError, match='已有正式冠军'):
        task.import_formal_champion(profile, tmp_path / 'must-not-replace', [source], use_burst=True,
            search_config=saved['config'])
    with pytest.raises(task.TaskError, match='64'):
        task.import_formal_champion(profile, tmp_path / 'too-many', [f'{index:032x}' for index in range(65)])


def test_dual_stale_task_cannot_replace_a_newly_published_distinct_champion(tmp_path,
        monkeypatch, memory_result_center, champion_engine):
    import burst
    import engine
    import json
    import result_store
    import threading
    from concurrent.futures import ThreadPoolExecutor
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    inspect = engine.inspect
    stale_ids = set()
    waiting, release = threading.Event(), threading.Event()
    api = result_store._api()

    def native_order(native, folder, **kwargs):
        capabilities = inspect(native, folder, **kwargs)
        folder = Path(folder)
        if 'fresh' in folder.parts:
            capabilities['actions'] = list(reversed(capabilities['actions']))
        if 'stale' in folder.parts:
            stale_ids.add(json.loads((folder.parent / 'profile.json').read_text(encoding='utf-8'))['run_id'])
        return capabilities

    def held_result_write(root, table, key, rows, **kwargs):
        if table == 'runs' and key in stale_ids and not release.is_set():
            waiting.set()
            if not release.wait(20):
                raise AssertionError('fresh task did not publish')
        return api['write'](root, table, key, rows, **kwargs)

    monkeypatch.setattr(engine, 'inspect', native_order)
    with patch.object(result_store, '_api', return_value=dict(api, write=held_result_write)), \
         ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(dual_result, tmp_path / 'stale', raw, 1)
        try:
            assert waiting.wait(20)
            fresh = dual_result(tmp_path / 'fresh', raw, candidate_limit=1)
        finally:
            release.set()
        stale = pending.result(20)
    assert stale['scenes'][0]['formal_champion_snapshot']['status'] == 'absent'
    assert stale['scenes'][0]['formal_champion_publication']['status'] == 'conflict'
    assert stale['scenes'][0]['search_result']['samples'] > 0
    inherited = dual_result(tmp_path / 'inherited', raw, candidate_limit=1)
    assert inherited['scenes'][0]['formal_champion_snapshot']['source_run_id'] == fresh['scenes'][0][
        'formal_champion_publication']['source_run_id']


@pytest.mark.parametrize('exhausted', [False, True])
def test_public_resume_publishes_a_saved_winner_before_completion_or_budget_early_return(tmp_path,
        monkeypatch, champion_engine, exhausted):
    import burst
    import result_store
    import sequence
    import task
    from search import TaskStore
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    api = result_store._api()

    def fail_champion(root, table, key, rows, **kwargs):
        if table == 'search_champions':
            raise OSError('saved winner awaiting publication')
        return api['write'](root, table, key, rows, **kwargs)

    with patch.object(result_store, '_api', return_value=dict(api, write=fail_champion)):
        state = dual_result(tmp_path / 'dual', raw, candidate_limit=1)
    folder = next((tmp_path / 'dual' / 'page' / 'tasks').glob('*/single_target'))
    previous = task.read_task(folder)
    if exhausted:
        store = TaskStore(folder)
        try:
            store.state['elapsed_seconds'] = 600.
            store.save()
        finally:
            store.close()
    monkeypatch.setattr(sequence, 'evaluate', lambda *args, **kwargs: pytest.fail('补发布重新评分'))
    resumed = task.resume_task(folder, simulation_config=previous['simulation_config'])
    assert resumed['search']['formal_champion_publication']['status'] == 'published'
    assert resumed['search_result'] == previous['search_result']
    assert resumed['completed_batches'] == previous['completed_batches']
    again = task.resume_task(folder, simulation_config=previous['simulation_config'])
    assert again['search']['formal_champion_publication'] == resumed['search']['formal_champion_publication']
    assert again['search']['formal_champion_snapshot'] == previous['search']['formal_champion_snapshot']


@pytest.mark.parametrize('change', ['name', 'equipment', 'cadence', 'engine'])
def test_dual_formal_champion_isolated_by_frozen_character_and_full_conditions(tmp_path,
        monkeypatch, memory_result_center, champion_engine, change):
    import burst
    import engine
    import result_store
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    interval = 200
    if change == 'name':
        raw = raw.replace('deathknight="', 'deathknight="Different ')
    elif change == 'equipment':
        raw = raw.replace('id=273795', 'id=273795,bonus_id=1')
    elif change == 'cadence':
        interval = 400
    else:
        identity = engine.identity
        monkeypatch.setattr(engine, 'identity', lambda *args, **kwargs:
            (lambda value: (value[0], dict(value[1], constructed_identity='different')))(identity(*args, **kwargs)))
    second = dual_result(tmp_path / 'second', raw, candidate_limit=1, interval_ms=interval)
    assert all(scene['formal_champion_snapshot']['status'] == 'absent' for scene in second['scenes'])
    assert [scene['formal_champion_snapshot']['condition_key'] for scene in first['scenes']] != [
        scene['formal_champion_snapshot']['condition_key'] for scene in second['scenes']]


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
    real_rules, inspect, evaluate = task._rule_hashes, engine.inspect, sequence.evaluate
    original = real_rules()
    monkeypatch.setattr(task, '_rule_hashes', lambda **kwargs: dict(original,
        **{str(Path(task.__file__).resolve()): 'f' * 64}))

    def source_catalogue(native, folder, **kwargs):
        capabilities = inspect(native, folder, **kwargs)
        if 'high' in Path(folder).parts:
            capabilities['actions'] = list(reversed(capabilities['actions']))
        return capabilities

    def source_scores(profile, candidate, folder, **kwargs):
        result = evaluate(profile, candidate, folder, **kwargs)
        score = 300. if 'high' in Path(profile).parts else 200.
        result['summary']['dps'] = score
        sim = result['report']['sim']
        sim['statistics']['raid_dps']['mean'] = sim['players'][0]['collected_data']['dps']['mean'] = score
        return result

    def no_initial_champion(root, table, key, rows, **kwargs):
        if table == 'search_champions':
            raise OSError('old source only')
        return api['write'](root, table, key, rows, **kwargs)

    with patch.object(result_store, '_api', return_value=dict(api, write=no_initial_champion)), \
         patch.object(engine, 'inspect', side_effect=source_catalogue), \
         patch.object(sequence, 'evaluate', side_effect=source_scores):
        low = dual_result(tmp_path / 'low', raw, candidate_limit=1)
        high = dual_result(tmp_path / 'high', raw, candidate_limit=1)
    monkeypatch.setattr(task, '_rule_hashes', real_rules)
    low_id, high_id = [state['scenes'][0]['formal_champion_publication']['source_run_id'] for state in (low, high)]
    def normalized(row):
        return {key: json.loads(value) if result_store.RUN_SCHEMA[key] == 'JSON'
                and isinstance(value, str) else value for key, value in row.items()}

    originals = {run_id: normalized(result_store.read_records('runs', run_id)[0])
                 for run_id in (low_id, high_id)}
    profile = tmp_path / 'current.simc'
    profile.write_bytes(raw.encode('utf-8'))
    options = dict(use_burst=True, search_config=dict(candidate_limit=1, batch_targets=(2,), iterations=2,
        validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',), input_interval_ms=200))
    for fault in ('engine', 'cadence', 'burst', 'profile', 'report',
                  'source_batch_missing', 'source_batch_forged', 'score', 'samples'):
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
                    case_api = dict(api, write=observed_write)
                    if fault in ('source_batch_missing', 'source_batch_forged', 'score', 'samples'):
                        if fault.startswith('source_batch_'):
                            locations = result_store.report_locations(run['batch_keys'])
                            groups = list(dict.fromkeys(locations.get(key) or key for key in run['batch_keys']))
                            source_batches = [row for row in result_store.read_many('batches', groups,
                                filters={'candidate_key': run['selected_candidate_key'], 'purpose': 'search'})
                                if row['batch_key'] in run['batch_keys']]
                            assert len(source_batches) == 1
                            run['batch_keys'].remove(source_batches[0]['batch_key'])
                            if fault == 'source_batch_forged':
                                foreign_id = high['scenes'][1]['formal_champion_publication']['source_run_id']
                                foreign = result_store.read_records('runs', foreign_id)[0]
                                locations = result_store.report_locations(foreign['batch_keys'])
                                groups = list(dict.fromkeys(locations.get(key) or key for key in foreign['batch_keys']))
                                foreign_batches = [row for row in result_store.read_many('batches', groups,
                                    filters={'candidate_key': run['selected_candidate_key'], 'purpose': 'search'})
                                    if row['batch_key'] in foreign['batch_keys']]
                                assert len(foreign_batches) == 1
                                run['batch_keys'].append(foreign_batches[0]['batch_key'])
                        else:
                            run['search_dps' if fault == 'score' else 'search_samples'] += 1
                        result_store.write('runs', high_id, [run], schema=result_store.RUN_SCHEMA)
                    if fault in ('engine', 'cadence', 'burst', 'profile'):
                        field = {'engine': 'engines', 'cadence': 'config', 'burst': 'burst', 'profile': 'profile'}[fault]
                        payload = run[field]
                        if fault == 'engine':
                            payload['controlled']['constructed_identity'] = 'foreign'
                        elif fault == 'cadence':
                            payload['input_interval_ms'] = 400
                        elif fault == 'burst':
                            payload['definition_id'] = 'foreign'
                        else:
                            payload['input_effective_sha256'] = 'foreign'
                        result_store.write('runs', high_id, [run], schema=result_store.RUN_SCHEMA)
                    if fault == 'report':
                        def missing_report(root, table, keys, **kwargs):
                            if table == 'batches':
                                raise api['MissingKeyError']('selected old source report')
                            return api['read_keys'](root, table, keys, **kwargs)
                        case_api['read_keys'] = missing_report
                    scoped.setattr(result_store, '_api', lambda: case_api)
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
    # Successful publication comes last, so it cannot bypass any preceding source rejection.
    with subtests.test(fault='none'):
        task.import_formal_champion(profile, tmp_path / 'imported', [low_id, high_id], **options)
        saved = task.read_task(tmp_path / 'imported')
        snapshot = saved['search']['formal_champion_snapshot']
        assert snapshot['source_run_id'] == high_id
        assert snapshot['score'] == 300.
        assert snapshot['source_condition_key'] != saved['search']['formal_champion_snapshot']['binding']['condition']
        assert saved['search_result']['dps'] != 300.
        assert saved['search']['formal_champion_publication']['status'] == 'published'
        assert {run_id: normalized(result_store.read_records('runs', run_id)[0])
                for run_id in (low_id, high_id)} == originals


@pytest.mark.parametrize('stage', ['complete_winner', 'partial_first_batch', 'crash_checkpoint'])
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
        if stage != 'partial_first_batch':
            assert previous['scenes'][0]['formal_champion_publication']['status'] == 'unchanged'
        else:
            assert 'search_result' not in previous['scenes'][0]
        if stage == 'crash_checkpoint':
            from search import TaskStore
            folder = next((tmp_path / 'cancelled' / 'page' / 'tasks').glob('*/single_target'))
            store = TaskStore(folder)
            try:
                store.state.update(status='running', inflight={})
                store.save()  # Reconstruct the durable state of a worker that exited.
            finally:
                store.close()
        record['version'] += 1
        result_store.write('search_champions', snapshot['condition_key'], [record],
                           schema=result_store.SEARCH_CHAMPION_SCHEMA)

    with patch.object(sequence, 'evaluate', side_effect=interrupt):
        resumed = dual_result(tmp_path / 'cancelled', raw, candidate_limit=1,
            expected='cancelled', before_resume=newer_version)
    assert resumed['scenes'][0]['formal_champion_snapshot'] == resumed['previous_state']['scenes'][0][
        'formal_champion_snapshot']
    assert resumed['scenes'][0]['formal_champion_publication']['status'] == 'unchanged'


@pytest.mark.parametrize('fault', ['corrupt_champion', 'temporary_read', 'corrupt_candidate',
    'temporary_candidate_read', 'source_program'])
def test_dual_formal_champion_read_errors_remain_visible_and_do_not_overwrite_the_incumbent(tmp_path,
        monkeypatch, memory_result_center, champion_engine, fault):
    import burst
    import result_store
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    first = dual_result(tmp_path / 'first', raw, candidate_limit=1)
    # Reuse the saved binding through the public next-task snapshot.
    inherited = dual_result(tmp_path / 'inherited', raw, candidate_limit=1)
    snapshot = inherited['scenes'][0]['formal_champion_snapshot']
    original = result_store.read_search_champion(snapshot['condition_key'])
    api = result_store._api()
    if fault == 'corrupt_champion':
        def unreadable(root, table, key, **kwargs):
            if table == 'search_champions':
                raise api['CorruptDataError']('constructed corrupt incumbent')
            return api['read_key'](root, table, key, **kwargs)
        monkeypatch.setattr(result_store, '_api', lambda: dict(api, read_key=unreadable))
    elif fault == 'temporary_read':
        def unavailable(root, table, key, **kwargs):
            if table == 'search_champions':
                raise OSError('constructed temporary champion read failure')
            return api['read_key'](root, table, key, **kwargs)
        monkeypatch.setattr(result_store, '_api', lambda: dict(api, read_key=unavailable))
    elif fault in ('corrupt_candidate', 'temporary_candidate_read'):
        def unreadable_candidate(root, table, key, **kwargs):
            if table == 'candidates':
                if fault == 'corrupt_candidate':
                    raise api['CorruptDataError']('constructed corrupt champion artifact')
                raise OSError('constructed temporary champion artifact read failure')
            return api['read_key'](root, table, key, **kwargs)
        monkeypatch.setattr(result_store, '_api', lambda: dict(api, read_key=unreadable_candidate))
    else:
        candidate = result_store.read_records('candidates', original['source_candidate_data_key'])[0]
        candidate['program'] = {}
        result_store.write('candidates', original['source_candidate_data_key'], [candidate],
                           schema=result_store.CANDIDATE_SCHEMA)
    failed = dual_result(tmp_path / 'failed', raw, candidate_limit=1, expected='failed')
    assert failed['error']
    monkeypatch.setattr(result_store, '_api', lambda: api)
    assert result_store.read_search_champion(snapshot['condition_key']) == original
