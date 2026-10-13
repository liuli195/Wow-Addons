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
    first = dual_result(tmp_path / 'first', raw, candidate_limit=4)
    assert [scene['formal_champion_publication']['status'] for scene in first['scenes']] == [
        'published', 'published']
    second = dual_result(tmp_path / 'second', raw, candidate_limit=4)
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
        state = dual_result(tmp_path, raw, candidate_limit=4, before_resume=restore)
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
    first = dual_result(tmp_path / 'first', raw, candidate_limit=4)
    inspect = engine.inspect

    def invalid_native(*args, **kwargs):
        capabilities = inspect(*args, **kwargs)
        capabilities['baseline_actions'] = capabilities['actions'] + [dict(kind='spell',
            spell_id=999999, simc_action='unmapped_native_action', name='unmapped', gcd_ms=1500)]
        return capabilities

    monkeypatch.setattr(engine, 'inspect', invalid_native)
    second = dual_result(tmp_path / 'second', raw, candidate_limit=4)
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
    third = dual_result(tmp_path / 'third', raw, candidate_limit=10, validation_batches=validation_batches)
    assert third['scenes'][0]['formal_champion_snapshot']['source_run_id'] == scene[
        'formal_champion_publication']['source_run_id']
    if publication == 'published':
        assert third['scenes'][0]['formal_champion_snapshot']['promotion_evidence'][0]['comparison']['ci95'][0] > 0
    else:
        assert any({source['source_kind'] for source in group} == {'native', 'formal_champion'}
                   for group in scene['start_sources'].values())


def test_management_import_rechecks_one_known_formal_source_without_history_scanning(tmp_path,
        monkeypatch, memory_result_center, champion_engine):
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

    with patch.object(result_store, '_api', return_value=dict(api, write=unavailable_champion_write)):
        historical = dual_result(tmp_path / 'old', raw, candidate_limit=4)
    source = historical['scenes'][0]['formal_champion_publication']['source_run_id']
    profile = tmp_path / 'current.simc'
    profile.write_text(raw, encoding='utf-8')
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
    with patch.object(result_store, '_api', return_value=dict(api, query=known_only)):
        task.import_formal_champion(profile, tmp_path / 'imported', [source, source], use_burst=True,
            search_config=dict(candidate_limit=4, batch_targets=(2,), iterations=2,
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
