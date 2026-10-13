"""网页双场通过真实任务和隔离中心消费最终训练冠军。"""
import copy
import json
import threading
import sqlite3
import pytest
from unittest.mock import patch
from pathlib import Path
from urllib.request import Request, urlopen

from test_burst import page_task_engine, reviewed_fixture
from test_seed_training import memory_result_center


def completed_training(tmp_path, targets, programs, *, name='current'):
    """构造完整最终成绩凭据，不启动训练或原生计算。"""
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
    inputs = seed_training._training_inputs(template, targets, use_burst=True)
    character = inputs['character']
    batch = tmp_path / 'custom-training' / str(targets) / name
    batch.mkdir(parents=True)
    native = engine.reference(template, batch / 'reference', character,
                              simulation_config=inputs['simulation_config'])
    _, capabilities, context = engine.prepare_loop(native, character, batch, TaskRuntime(600),
        definition=inputs['definition'], interval_ms=200)
    payload = seed_training.training_condition_input(inputs['template_sha'], inputs['engines'],
        inputs['config'], inputs['simulation_config'], burst_context=context)
    condition = seed_training.semantic_condition(payload, seed_training.semantic_versions())
    manifest = dict(format=1, condition=condition, condition_input=payload,
        input_sha256=digest(payload), semantic_versions=seed_training.semantic_versions(),
        semantic_condition=condition, executions=[])
    (batch / 'standard.simc').write_text(raw, encoding='utf-8')
    (batch / 'condition.txt').write_text(condition, encoding='ascii')
    (batch / 'identity.json').write_text(json.dumps(manifest), encoding='utf-8')
    times, _ = burst.combined_inputs(list(range(0, 180000, 200)), context, 200)
    rows = []
    for ordinal, (program, scores) in enumerate(programs):
        candidate_id = f'{targets:02d}{ordinal:010d}' + '0' * 52
        folder = batch / candidate_id[:12]
        folder.mkdir()
        store = TaskStore(folder)
        store.state.update(run_id=candidate_id, training_condition=condition,
            training_candidate_id=candidate_id, config=inputs['config'], capabilities=capabilities,
            native=native, burst=context, phase='done')
        form = canonicalize_search_program(program, capabilities)['form']
        for index, (seed, score) in enumerate(zip(seed_training.RETEST_SEEDS, scores)):
            key = digest(dict(folder=str(folder / 'retest-final'), seed=seed))
            request = dict(condition=condition, program=form, behavior_identity=digest(form),
                purpose='seed_retest', seed=seed, input_seed=seed, iterations=128, times=times,
                stats=STATS_VERSION, trace=False, reset_events=[])
            receipt = dict(status='success', request=request, dps=score, samples=127,
                           variance=0., requested_iterations=128, data_key=key)
            report = _fast_report(character, score, 127)
            report['sim']['targets'] *= targets
            result_store.write_batch(key, dict(batch_key=key, run_id=candidate_id,
                purpose='seed_retest', seed=seed, input_seed=seed, iterations=128,
                requested_iterations=128, samples=127, dps=score, variance=0.,
                engines=inputs['engines'], condition_key=condition, candidate_key=digest(form),
                program_identity=json.dumps(form, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                batch_index=index, scenario='nominal', stats_version=STATS_VERSION,
                times=times, trace=False, report=report))
            store.put_batch(key, receipt)
        store.save()
        store.close()
        rows.append(dict(candidate_id=candidate_id, condition=condition, status='completed', error='',
            initial_program=program, program=program, family='plain', core_retained=False,
            rounds=2, stop_reason='no_improvement', elapsed_seconds=1., scores=scores,
            initial_scores=[99999.] * 3, comparison={}, task_path=str(folder),
            native_batch_starts=0, batch_requests=0, cache_hits=0))
    result_store.write('seed_processed', inputs['scope'], rows, schema=seed_training.PROCESSED_SCHEMA)
    return template, rows


def dual_result(tmp_path, raw, candidate_limit=9, *, expected='completed', interval_ms=200):
    """走已批准的 POST 双场到 GET 公开结果接缝。"""
    from interface import create_server
    server = create_server(tmp_path / 'page', task_options=dict(search_config=dict(
        candidate_limit=candidate_limit, batch_targets=(2,), iterations=2,
        validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',))))
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
        return state
    finally:
        for _, handle in server.tasks.values():
            if not handle.done:
                handle.cancel_event.set()
                handle.join(5)
        server.shutdown()
        server.server_close()
        thread.join(3)


def test_dual_reads_each_scenes_final_training_champion(tmp_path, monkeypatch,
        memory_result_center, page_task_engine):
    import burst
    import engine
    import result_store
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    single = [['outbreak'], ['death_coil'], ['outbreak']]
    aoe = [['death_coil'], ['outbreak'], ['death_coil']]
    template, single_rows = completed_training(tmp_path, 1, [(single, [190., 200., 210.])])
    _, aoe_rows = completed_training(tmp_path, 5, [(aoe, [290., 300., 310.])])
    monkeypatch.setattr(engine, 'training_template', lambda: template)
    state = dual_result(tmp_path, raw)
    assert [scene['training_champion_snapshot']['candidate_id'] for scene in state['scenes']] == [
        single_rows[0]['candidate_id'], aoe_rows[0]['candidate_id']]
    assert [scene['training_champion_snapshot']['scores'] for scene in state['scenes']] == [
        [190., 200., 210.], [290., 300., 310.]]


def test_dual_chooses_all_67_final_results_and_keeps_four_selected_sources(tmp_path, monkeypatch,
        memory_result_center, page_task_engine):
    import burst
    import engine
    import result_store
    import seed_training
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    winning_program = [['outbreak'], dict(kind='WaitClicks', clicks=72), ['death_coil']]
    entries = [([['outbreak'], dict(kind='WaitClicks', clicks=index + 2), ['death_coil']],
                [100., 100., 100.]) for index in range(65)]
    entries += [(winning_program, [199., 200., 201.]), (winning_program, [190., 200., 210.])]
    template, rows = completed_training(tmp_path, 1, entries)
    monkeypatch.setattr(engine, 'training_template', lambda: template)
    selected = [dict(candidate_id='selected-' + str(index), condition=rows[0]['condition'],
        class_name='deathknight', spec='unholy', targets=1,
        program=[['death_coil'], dict(kind='WaitClicks', clicks=100 + index), ['outbreak']],
        family='family-' + str(index), score=99999., scores=[99999.] * 3,
        template_sha256='selected-template', engines=engine.identity('baseline')[1]) for index in range(4)]
    engines = {mode: engine.identity(mode)[1] for mode in ('baseline', 'controlled')}
    for row in selected:
        row['engines'] = engines
    result_store.write('seed_selected', 'deathknight-unholy-1-burst', selected,
                       schema=seed_training.SELECTED_SCHEMA)
    before = {table: result_store.read_records(table, 'deathknight-unholy-1-burst')
              for table in ('seed_processed', 'seed_selected')}
    api = result_store._api()
    def read_only_training(root, table, key, values, **kwargs):
        if table.startswith('seed_'):
            raise AssertionError('正式搜索写入了训练存储')
        return api['write'](root, table, key, values, **kwargs)
    with patch.object(result_store, '_api', return_value=dict(api, write=read_only_training)):
        state = dual_result(tmp_path, raw)
    scene = state['scenes'][0]
    champion = scene['training_champion_snapshot']
    assert champion['candidate_id'] == rows[65]['candidate_id']
    assert champion['program'] == winning_program
    assert champion['phase'] == 'final' and champion['score'] == 200.
    assert scene['training_champion_adaptation']['current_score'] != 200.
    sources = [source for group in scene['start_sources'].values() for source in group]
    assert {source['candidate_id'] for source in sources if source['source_kind'] == 'seed_selected'} == {
        'selected-0', 'selected-1', 'selected-2', 'selected-3'}
    assert any(source['source_kind'] == 'native' for source in sources)
    assert len([source for source in sources if source['source_kind'] == 'training_champion']) == 1
    assert {table: result_store.read_records(table, 'deathknight-unholy-1-burst') for table in before} == before
    assert state['scenes'][1]['training_champion_snapshot']['status'] == 'absent'


@pytest.mark.parametrize('fault', ['scores_missing', 'receipt_missing', 'wrong_program', 'wrong_condition',
    'wrong_seed', 'wrong_iterations', 'report_missing', 'report_corrupt', 'temporary_error',
    'foreign_template', 'foreign_engine', 'foreign_targets', 'foreign_cadence', 'foreign_version',
    'legacy_unapproved_hash'])
def test_dual_rejects_invalid_final_evidence_and_reports_temporary_storage_errors(tmp_path, monkeypatch,
        memory_result_center, page_task_engine, fault):
    import burst
    import engine
    import result_store
    import seed_training
    from search import digest
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    template, rows = completed_training(tmp_path, 1, [
        ([['outbreak'], ['death_coil'], ['outbreak']], [100.] * 3),
        ([['death_coil'], ['outbreak'], ['death_coil']], [200.] * 3)])
    monkeypatch.setattr(engine, 'training_template', lambda: template)
    high = rows[1]
    folder = Path(high['task_path'])
    key = digest(dict(folder=str(folder / 'retest-final'), seed=seed_training.RETEST_SEEDS[0]))
    if fault == 'scores_missing':
        high['scores'] = [200., 200.]
        result_store.write('seed_processed', 'deathknight-unholy-1-burst', rows,
                           schema=seed_training.PROCESSED_SCHEMA)
    if fault in ('receipt_missing', 'wrong_program', 'wrong_condition', 'wrong_seed', 'wrong_iterations'):
        with sqlite3.connect(folder / 'task.sqlite3') as database:
            if fault == 'receipt_missing':
                database.execute('DELETE FROM batches WHERE key=?', (key,))
            else:
                receipt = json.loads(database.execute('SELECT value FROM batches WHERE key=?', (key,)).fetchone()[0])
                field, value = {'wrong_program': ('program', {}), 'wrong_condition': ('condition', 'foreign'),
                                'wrong_seed': ('seed', 1), 'wrong_iterations': ('iterations', 127)}[fault]
                receipt['request'][field] = value
                database.execute('UPDATE batches SET value=? WHERE key=?', (json.dumps(receipt), key))
    if fault.startswith('foreign_') or fault == 'legacy_unapproved_hash':
        batch = folder.parent
        manifest = json.loads((batch / 'identity.json').read_text(encoding='utf-8'))
        payload = manifest['condition_input']
        if fault == 'foreign_template':
            payload['template'] = 'different-template'
        elif fault == 'foreign_engine':
            payload['engines'] = dict(payload['engines'], controlled={'mode': 'foreign'})
        elif fault == 'foreign_targets':
            payload['simulation']['target_count'] = 5
        elif fault == 'foreign_cadence':
            payload['config']['input_interval_ms'] = 400
        elif fault == 'foreign_version':
            manifest['semantic_versions']['statistics'] = 'foreign-statistics'
        else:
            payload['rules'].update({name: hashes[0] for name, hashes in
                                     seed_training.LEGACY_EXECUTION_RULES.items()})
            payload['rules']['projects/sim2gse/task.py'] = 'unapproved-task-hash'
            manifest['legacy_source_commit'] = seed_training.LEGACY_SOURCE_COMMIT
        manifest['semantic_condition'] = seed_training.semantic_condition(payload, manifest['semantic_versions'])
        manifest['input_sha256'] = digest(payload)
        manifest['condition'] = digest(payload) if fault == 'legacy_unapproved_hash' else manifest['semantic_condition']
        (batch / 'condition.txt').write_text(manifest['condition'], encoding='ascii')
        (batch / 'identity.json').write_text(json.dumps(manifest), encoding='utf-8')
        for row in rows:
            row['condition'] = manifest['condition']
        result_store.write('seed_processed', 'deathknight-unholy-1-burst', rows,
                           schema=seed_training.PROCESSED_SCHEMA)
    api = result_store._api()
    def read_key(root, table, group, **kwargs):
        if table == 'batches' and group == key:
            if fault == 'report_missing':
                raise api['MissingKeyError'](key)
            if fault == 'report_corrupt':
                raise api['CorruptDataError'](key)
            if fault == 'temporary_error':
                raise OSError('temporary isolated storage failure')
        return api['read_key'](root, table, group, **kwargs)
    with patch.object(result_store, '_api', return_value=dict(api, read_key=read_key)):
        state = dual_result(tmp_path, raw, expected='failed' if fault == 'temporary_error' else 'completed')
    if fault == 'temporary_error':
        assert '不可读' in state['error']
        return
    champion = state['scenes'][0]['training_champion_snapshot']
    if fault.startswith('foreign_') or fault == 'legacy_unapproved_hash':
        assert champion['status'] == 'absent'
        assert champion['excluded']
        if fault == 'legacy_unapproved_hash':
            assert any('旧训练源码凭据不兼容' in excluded['reason'] for excluded in champion['excluded'])
    else:
        assert champion['candidate_id'] == rows[0]['candidate_id']
        excluded = next(row for row in champion['excluded'] if row['candidate_id'] == high['candidate_id'])
        assert excluded['status'] == ('missing' if fault in ('receipt_missing', 'report_missing') else 'invalid')


def test_dual_keeps_legal_native_starts_when_another_cannot_be_mapped(tmp_path, monkeypatch,
        memory_result_center, page_task_engine):
    import burst
    import engine
    import result_store
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    inspect = engine.inspect
    def native_catalogue(*args, **kwargs):
        capabilities = inspect(*args, **kwargs)
        capabilities['baseline_actions'] = capabilities['actions'] + [dict(kind='spell',
            spell_id=999999, simc_action='unmapped_native_action', name='unmapped', gcd_ms=1500)]
        return capabilities
    monkeypatch.setattr(engine, 'inspect', native_catalogue)
    state = dual_result(tmp_path, raw)
    assert all(scene['search_result']['dps'] > 0 for scene in state['scenes'])
    assert all(any(source['source_kind'] == 'native' for group in scene['start_sources'].values()
                   for source in group) for scene in state['scenes'])
