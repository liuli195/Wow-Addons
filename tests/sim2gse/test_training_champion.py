"""网页双场通过真实任务和隔离中心消费最终训练冠军。"""
import copy
import hashlib
import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from test_burst import page_task_engine, reviewed_fixture
from test_seed_training import memory_result_center


def completed_training(tmp_path, targets, programs):
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
    template = tmp_path / 'standard.simc'
    template.write_text(raw, encoding='utf-8')
    inputs = seed_training._training_inputs(template, targets, use_burst=True)
    character = inputs['character']
    batch = tmp_path / 'custom-training' / str(targets)
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
        candidate_id = f'{targets:02d}{ordinal:062d}'
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


def dual_result(tmp_path, raw, candidate_limit=9):
    """走已批准的 POST 双场到 GET 公开结果接缝。"""
    from interface import create_server
    server = create_server(tmp_path / 'page', task_options=dict(search_config=dict(
        candidate_limit=candidate_limit, batch_targets=(2,), iterations=2,
        validation_batches=1, final_batches=1, final_iterations=2, scenarios=('nominal',))))
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(Request(base + '/api/tasks', json.dumps(dict(profile=raw, mode='dual')).encode(),
                             {'Content-Type': 'application/json'}), timeout=5) as response:
            created = json.load(response)
        server.tasks[created['task_id']][1].join(30)
        with urlopen(base + '/api/tasks/' + created['task_id'], timeout=5) as response:
            state = json.load(response)
        assert state['status'] == 'completed', state
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
