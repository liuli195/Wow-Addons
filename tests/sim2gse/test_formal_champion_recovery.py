"""公开双场完整复测、来源核验及持久成果补发。"""
import json
import pytest
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, urlopen
from test_burst import page_task_engine, reviewed_fixture
from test_training_champion import unchanged_offspring, unchanged_champion_engine, champion_engine
from test_seed_training import memory_result_center


def final_export_compilations(compiled, destination):
    purposes = {destination / 'exports' / purpose: purpose
                for purpose in ('single_target', 'aoe', 'burst')}
    purposes[destination / 'collection'] = 'collection'
    return [(purposes[folder], enabled) for folder, enabled in compiled if folder in purposes]


def test_final_export_observer_excludes_candidate_and_other_task_compilations():
    destination = Path('/memory/tasks/current')
    expected = [('single_target', True), ('aoe', True), ('burst', True),
                ('burst', True), ('collection', True)]
    compiled = [(destination / 'exports' / purpose, enabled)
                for purpose, enabled in expected if purpose != 'collection']
    compiled.append((destination / 'collection', True))
    compiled.extend((folder, False) for folder in (
        destination / 'aoe' / 'exports' / 'sim2gse-search-behavior-v2-candidate',
        destination / 'aoe' / 'exports' / 'aoe',
        destination / 'aoe' / 'collection',
        destination.parent / 'other' / 'exports' / 'burst'))
    assert final_export_compilations(compiled, destination) == expected
    # Every real final invocation remains visible, including repeated burst exports.
    compiled.append((destination / 'exports' / 'burst', False))
    assert final_export_compilations(compiled, destination) == [*expected, ('burst', False)]


@contextmanager
def dual_page(root, raw, *, diagnostic_logging=False, resume_logging=False):
    from interface import create_server
    server = create_server(root / 'page', task_options=dict(
        search_config=dict(iterations=2, max_processes=1)))
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, value=None):
        body = json.dumps(value).encode() if value is not None else None
        with urlopen(Request(base + path, body, {'Content-Type': 'application/json'}), timeout=5) as response:
            return json.load(response)

    created = request('/api/tasks', dict(profile=raw, mode='dual', input_interval_ms=200,
                                       diagnostic_logging=diagnostic_logging))
    task_id = created['task_id']

    def read():
        server.tasks[task_id][1].join(30)
        return request('/api/tasks/' + task_id)

    def resume():
        request('/api/tasks/' + task_id + '/resume', dict(diagnostic_logging=resume_logging))
        return read()

    try:
        yield read, resume
    finally:
        for _, handle in server.tasks.values():
            if not handle.done:
                handle.cancel_event.set()
                handle.join(5)
        server.shutdown()
        server.server_close()
        worker.join(3)


@pytest.mark.real
def test_public_formal_search_naturally_retests_and_exports_one_champion_per_scene(
        tmp_path, monkeypatch, memory_result_center, unchanged_champion_engine):
    """真实页面生命周期保留，只在原生评分边界提供等分，促成自然早停。"""
    import burst
    import sequence
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    evaluate = sequence.evaluate

    def equal_native_scores(*args, **kwargs):
        return evaluate(*args, score=100., **kwargs)

    monkeypatch.setattr(sequence, 'evaluate', equal_native_scores)
    with dual_page(tmp_path, raw) as (read, _):
        result = read()
    assert result['status'] == 'completed', result
    assert result['stop_policy'] == dict(version=1, kind='natural_stagnation')
    assert result['total_budget_seconds'] is None
    assert set(result['exports']) == {'single_target', 'aoe', 'burst'}
    assert result['collection_ready']
    for scene in result['scenes']:
        assert scene['stop_policy'] == result['stop_policy']
        assert scene['total_budget_seconds'] is None
        assert scene['search_result']['dps'] == 100.
        assert scene['search_result']['samples'] == 381
        assert scene['search_result']['retest'] == dict(scenario='nominal', batches=3, requested_iterations=128)
        assert scene['formal_champion_publication']['status'] == 'published'


@pytest.mark.real
def test_public_formal_publication_failure_is_recoverable_without_rescoring_saved_scene(
        tmp_path, monkeypatch, memory_result_center, unchanged_champion_engine):
    import burst
    import result_store
    import sequence
    import codec
    import task
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    evaluate, publish = sequence.evaluate, result_store.publish_search_champion
    scored, logging, compiled = [], [], []
    fail_once = [True]
    compiler = codec.run_command

    def equal_native_scores(profile, candidate, folder, **kwargs):
        scored.append(str(folder))
        logging.append((str(folder), kwargs['runtime'].diagnostic_logging))
        return evaluate(profile, candidate, folder, score=100., **kwargs)

    def observed_compiler(command, *args, **kwargs):
        compiled.append((Path(kwargs['output_dir']), kwargs['runtime'].diagnostic_logging))
        return compiler(command, *args, **kwargs)

    def unavailable_publication(*args, **kwargs):
        if fail_once[0]:
            fail_once[0] = False
            raise OSError('constructed temporary champion publication failure')
        return publish(*args, **kwargs)

    monkeypatch.setattr(sequence, 'evaluate', equal_native_scores)
    monkeypatch.setattr(result_store, 'publish_search_champion', unavailable_publication)
    monkeypatch.setattr(codec, 'run_command', observed_compiler)
    with dual_page(tmp_path, raw, diagnostic_logging=False, resume_logging=True) as (read, resume):
        paused = read()
        assert paused['status'] == 'failed', paused
        assert paused['recoverable'] and not paused['collection_ready']
        assert '两个循环均已完成' not in paused['result_note']
        assert paused['scenes'][0]['formal_champion_publication']['status'] == 'pending'
        completed_scene_calls = [path for path in scored if 'single_target' in path]
        assert completed_scene_calls
        destination = next((tmp_path / 'page' / 'tasks').iterdir())
        assert not list(destination.glob('single_target/**/checked.log'))
        before = task.read_task(destination / 'single_target')
        assert before['config']['diagnostic_logging'] is False
        continued = resume()
    assert continued['status'] == 'completed', continued
    assert continued['collection_ready']
    assert [path for path in scored if 'single_target' in path] == completed_scene_calls
    assert continued['scenes'][0]['formal_champion_publication']['status'] == 'published'
    assert continued['scenes'][0]['search_result']['samples'] == 381
    assert all(enabled is False for path, enabled in logging if 'single_target' in path)
    assert any('aoe' in path for path, _ in logging)
    assert all(enabled is True for path, enabled in logging if 'aoe' in path)
    exported = final_export_compilations(compiled, destination)
    assert {purpose for purpose, _ in exported} == {'single_target', 'aoe', 'burst', 'collection'}
    assert all(enabled is True for _, enabled in exported)
    for purpose in ('single_target', 'aoe', 'burst'):
        assert (destination / 'exports' / purpose / 'checked.log').is_file()
    # 恢复可写本次导出日志，但不补写已完成场此前的编译日志。
    assert not list(destination.glob('single_target/**/checked.log'))


@pytest.mark.real
def test_public_failed_first_score_keeps_reference_readable_without_search_columns(
        tmp_path, monkeypatch, memory_result_center, unchanged_champion_engine):
    import burst
    import sequence
    import task
    from engine import NativeEvaluationError
    definition, raw = reviewed_fixture()
    burst.publish(definition)

    def unavailable_native_score(*args, **kwargs):
        raise NativeEvaluationError('constructed original first coarse failure')

    monkeypatch.setattr(sequence, 'evaluate', unavailable_native_score)
    with dual_page(tmp_path, raw) as (read, _):
        failed = read()
        assert failed['status'] == 'failed', failed
        folder = next((tmp_path / 'page' / 'tasks').glob('*/single_target'))
        saved = task.read_task(folder, include_search_records=True)
    assert saved['status'] == 'failed'
    assert 'constructed original first coarse failure' in saved['error']
    assert saved['search']['batch_keys'] == [saved['reference_data_key']]
    assert not saved['search'].get('records')


def test_public_formal_champion_rejects_a_truncated_finalist_cohort_before_scoring():
    from copy import deepcopy
    import result_store
    import task
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, _ = formal_cohort()
    task._validate_formal_source(record, state, character, run=run, candidate=candidate,
        verify_reports=False)
    truncated = deepcopy(record)
    removed = truncated['evaluation']['finalists'].pop(0)
    truncated['evaluation']['finalist_keys'].remove(removed['key'])
    removed_batches = {batch['data_key'] for batch in removed['batches']}
    truncated['batch_keys'] = [key for key in truncated['batch_keys'] if key not in removed_batches]
    with pytest.raises(result_store.InvalidRecordError, match='完整正式来源'):
        task._validate_formal_source(truncated, state, character, run=run,
            candidate=candidate, verify_reports=False)
    assert len(run['final_scenarios']['nominal']['finalists']) == 2


@pytest.mark.real
def test_public_formal_completed_save_failure_resumes_verified_winner_without_rescoring(
        tmp_path, monkeypatch, memory_result_center, unchanged_champion_engine):
    import burst
    import sequence
    import task
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    evaluate, store_run = sequence.evaluate, task._store_run
    fail_once, scored = [True], []

    def equal_native_scores(profile, candidate, folder, **kwargs):
        scored.append(str(folder))
        return evaluate(profile, candidate, folder, score=100., **kwargs)

    def unavailable_completed_save(destination, result, *, state=None):
        if Path(destination).name == 'single_target' and result.get('status') == 'completed' and fail_once[0]:
            fail_once[0] = False
            raise OSError('constructed complete intent before result save failure')
        return store_run(destination, result, state=state)

    monkeypatch.setattr(sequence, 'evaluate', equal_native_scores)
    monkeypatch.setattr(task, '_store_run', unavailable_completed_save)
    with dual_page(tmp_path, raw) as (read, resume):
        paused = read()
        assert paused['status'] == 'failed', paused
        assert paused['recoverable'] and not paused['collection_ready']
        previous_calls = [path for path in scored if 'single_target' in path]
        assert previous_calls
        continued = resume()
        assert continued['status'] == 'completed', continued
        folder = next((tmp_path / 'page' / 'tasks').glob('*/single_target'))
        saved = task.read_task(folder)
    assert [path for path in scored if 'single_target' in path] == previous_calls
    assert saved['candidate']['simulation'] == 'passed_native_model'
    assert saved['search']['formal_champion_publication']['status'] == 'published'
    assert saved['search_result']['samples'] == 381
    assert continued['collection_ready']
