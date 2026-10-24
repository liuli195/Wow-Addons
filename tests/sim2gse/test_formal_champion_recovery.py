"""公开双场取消后继续晋级及持久成果补发。"""
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
import pytest
from test_burst import page_task_engine, reviewed_fixture
from test_training_champion import champion_engine, completed_training, dual_result
from test_seed_training import memory_result_center


@contextmanager
def dual_page(root, raw):
    from interface import create_server
    server = create_server(root / 'page', task_options=dict(search_config=dict(
        candidate_limit=5, batch_targets=(2,), iterations=2, validation_batches=2,
        final_batches=1, final_iterations=2, scenarios=('nominal',))))
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, value=None):
        body = json.dumps(value).encode() if value is not None else None
        with urlopen(Request(base + path, body, {'Content-Type': 'application/json'}), timeout=5) as response:
            return json.load(response)

    created = request('/api/tasks', dict(profile=raw, mode='dual', input_interval_ms=200))
    task_id = created['task_id']

    def read():
        server.tasks[task_id][1].join(30)
        return request('/api/tasks/' + task_id)

    def resume():
        request('/api/tasks/' + task_id + '/resume', {})
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


def test_public_formal_search_naturally_retests_and_exports_one_champion_per_scene(
        tmp_path, monkeypatch, memory_result_center, champion_engine):
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


def test_public_formal_publication_failure_is_recoverable_without_rescoring_saved_scene(
        tmp_path, monkeypatch, memory_result_center, champion_engine):
    import burst
    import result_store
    import sequence
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    evaluate, publish = sequence.evaluate, result_store.publish_search_champion
    scored = []
    fail_once = [True]

    def equal_native_scores(profile, candidate, folder, **kwargs):
        scored.append(str(folder))
        return evaluate(profile, candidate, folder, score=100., **kwargs)

    def unavailable_publication(*args, **kwargs):
        if fail_once[0]:
            fail_once[0] = False
            raise OSError('constructed temporary champion publication failure')
        return publish(*args, **kwargs)

    monkeypatch.setattr(sequence, 'evaluate', equal_native_scores)
    monkeypatch.setattr(result_store, 'publish_search_champion', unavailable_publication)
    with dual_page(tmp_path, raw) as (read, resume):
        paused = read()
        assert paused['status'] == 'failed', paused
        assert paused['recoverable'] and not paused['collection_ready']
        assert paused['scenes'][0]['formal_champion_publication']['status'] == 'pending'
        completed_scene_calls = [path for path in scored if 'single_target' in path]
        assert completed_scene_calls
        continued = resume()
    assert continued['status'] == 'completed', continued
    assert continued['collection_ready']
    assert [path for path in scored if 'single_target' in path] == completed_scene_calls
    assert continued['scenes'][0]['formal_champion_publication']['status'] == 'published'
    assert continued['scenes'][0]['search_result']['samples'] == 381


def test_public_failed_first_score_keeps_reference_readable_without_search_columns(
        tmp_path, monkeypatch, memory_result_center, champion_engine):
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


def test_public_formal_champion_rejects_a_truncated_finalist_cohort_before_scoring(
        tmp_path, monkeypatch, memory_result_center, champion_engine):
    from copy import deepcopy
    import burst
    import result_store
    import sequence
    definition, raw = reviewed_fixture()
    burst.publish(definition)
    evaluate, scored = sequence.evaluate, []

    def equal_native_scores(profile, candidate, folder, **kwargs):
        scored.append(str(folder))
        return evaluate(profile, candidate, folder, score=100., **kwargs)

    monkeypatch.setattr(sequence, 'evaluate', equal_native_scores)
    with dual_page(tmp_path / 'source', raw) as (read, _):
        source = read()
    assert source['status'] == 'completed', source
    key = source['scenes'][0]['formal_champion_snapshot']['condition_key']
    original = result_store.read_search_champion(key)
    truncated = deepcopy(original)
    cohort = truncated['evaluation']['finalists']
    removed = next(row for row in cohort if row['key'] != truncated['behavior_identity'])
    truncated['evaluation']['finalists'] = [row for row in cohort if row['key'] != removed['key']]
    truncated['evaluation']['finalist_keys'].remove(removed['key'])
    removed_batches = {batch['data_key'] for batch in removed['batches']}
    truncated['batch_keys'] = [value for value in truncated['batch_keys'] if value not in removed_batches]
    result_store.write('search_champions', key, [truncated], schema=result_store.SEARCH_CHAMPION_SCHEMA)
    scored.clear()
    try:
        with dual_page(tmp_path / 'probe', raw) as (read, _):
            failed = read()
        assert failed['status'] == 'failed', failed
        assert failed['recoverable'] and not failed['collection_ready']
        assert not scored
        assert result_store.read_search_champion(key) == truncated
    finally:
        result_store.write('search_champions', key, [original], schema=result_store.SEARCH_CHAMPION_SCHEMA)


def test_public_formal_completed_save_failure_resumes_verified_winner_without_rescoring(
        tmp_path, monkeypatch, memory_result_center, champion_engine):
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


@pytest.mark.parametrize('fault', ['competition', 'crash_before_result'])
def test_public_cancelled_winner_can_advance_and_recover_without_invalidating_its_published_source(
        tmp_path, monkeypatch, memory_result_center, champion_engine, fault):
    import math
    from runtime import TaskCancelled
    from program import canonicalize_search_program
    import burst
    import engine
    import result_store
    import sequence
    import task
    from search import TaskStore
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    program = [['death_coil']] * 2 + [dict(kind='WaitClicks', clicks=2), ['outbreak']]
    template, _ = completed_training(tmp_path, 1, [(program, [200.] * 3)])
    monkeypatch.setattr(engine, '_training_template', lambda manifest: template)
    from test_search import _fast_capabilities
    stronger = [['death_coil']] * 3 + [dict(kind='WaitClicks', clicks=3), ['outbreak']]
    grades = {canonicalize_search_program(value, _fast_capabilities())['identity']: score
              for value, score in ((program, 200.), (stronger, 300.))}
    original_evaluate, store_run, api = sequence.evaluate, task._store_run, result_store._api()

    def evaluate(profile, candidate, folder, **kwargs):
        # Grade explicit behaviors, independent of the rule start's length or spell IDs.
        return original_evaluate(profile, candidate, folder,
            score=grades.get(sequence.behavior_key(candidate), 100.), **kwargs)

    cancel_once = [True]
    save_checkpoint = TaskStore.save
    baseline_probe = dict(root=None, expected=None, score=None, samples=None, folder=None)

    def save_probe_baseline(store, **changes):
        saved = save_checkpoint(store, **changes)
        root = baseline_probe['root']
        archive = store.state.get('archive', [])
        if root is not None and root in store.destination.parents and archive:
            assert len(archive) == 1
            row = archive[0]
            expected = baseline_probe['expected']
            assert store.state['formal_champion_snapshot']['behavior_identity'] == expected
            assert store.state['formal_champion_adaptation']['status'] == 'accepted'
            assert row['key'] == canonicalize_search_program(
                row['program'], store.state['capabilities'])['identity'] == expected
            assert math.isfinite(row['score']) and row['batches']
            assert all(batch['status'] == 'success' and batch['samples'] > 0
                       and batch['request']['condition'] == store.state['condition']
                       and batch['request']['behavior_identity'] == expected for batch in row['batches'])
            baseline_probe.update(root=None, score=row['score'],
                samples=sum(batch['samples'] for batch in row['batches']), folder=store.destination)
            raise TaskCancelled('auxiliary inheritance probe saved its complete current baseline')
        return saved

    def assert_probe(state, expected):
        scene = state['scenes'][0]
        assert scene['formal_champion_snapshot']['behavior_identity'] == expected['behavior_identity']
        assert scene['formal_champion_snapshot']['source_run_id'] == expected['source_run_id']
        assert scene['formal_champion_snapshot']['condition_key'] == expected['condition_key']
        assert scene['formal_champion_adaptation']['status'] == 'accepted'
        assert scene['formal_champion_adaptation']['current_score'] == baseline_probe['score']
        assert scene['search_result']['dps'] == baseline_probe['score']
        assert scene['search_result']['samples'] == baseline_probe['samples'] > 0
        saved = task.read_task(baseline_probe['folder'])
        assert saved['selected_candidate_key'] == saved['locked_candidate_key'] == expected['behavior_identity']
        assert scene['formal_champion_publication']['status'] == 'unchanged'
        assert result_store.read_search_champion(key) == expected

    def stop_after_complete_batch(*args, **kwargs):
        result = evaluate(*args, **kwargs)
        if cancel_once[0]:
            cancel_once[0] = False
            kwargs['runtime'].cancel()
        return result

    with patch.object(sequence, 'evaluate', side_effect=stop_after_complete_batch), \
         patch.object(TaskStore, 'save', save_probe_baseline), dual_page(tmp_path / 'original', raw) as (read, resume):
        first = read()
        assert first['status'] == 'cancelled'
        scene = first['scenes'][0]
        folder = next((tmp_path / 'original' / 'page' / 'tasks').glob('*/single_target'))
        saved_a = task.read_task(folder)
        key = scene['formal_champion_snapshot']['condition_key']
        champion_a = result_store.read_search_champion(key)
        assert champion_a['source_run_id'] == saved_a['run_id']
        assert champion_a['version'] == 1
        assert champion_a['behavior_identity'] not in grades
        assert champion_a['score'] == 100.
        expected_incumbent = champion_a
        if fault == 'competition':
            completed_training(tmp_path, 1, [(stronger, [300.] * 3)], name='newer')
            competing = dual_result(tmp_path / 'competing', raw, candidate_limit=5, validation_batches=2)
            expected_incumbent = result_store.read_search_champion(key)
            assert expected_incumbent['source_run_id'] == competing['scenes'][0]['formal_champion_publication']['source_run_id']
            assert expected_incumbent['behavior_identity'] != champion_a['behavior_identity']
        crash_once = [True]

        def save_result(destination, result, *, state=None):
            if (fault == 'crash_before_result' and crash_once[0] and Path(destination) == folder
                    and result.get('status') == 'completed'):
                crash_once[0] = False
                raise SystemExit('constructed process exit after completed checkpoint before result write')
            return store_run(destination, result, state=state)

        with patch.object(task, '_store_run', side_effect=save_result):
            continued = resume()
        store = TaskStore(folder)
        try:
            intent = store.state['formal_champion_publication_intent']['record']
            winner_b = intent['behavior_identity']
            assert winner_b != champion_a['behavior_identity']
            assert store.state['formal_champion_snapshot'] == scene['formal_champion_snapshot']
            expected_batches = store.state['completed_batches']
            if fault == 'crash_before_result':
                assert not crash_once[0]
                assert store.state['formal_champion_publication']['status'] == 'pending'
                old_result = result_store.read_records('runs', saved_a['run_id'])[0]
                assert old_result['status'] == 'cancelled'
                assert old_result['selected_candidate_key'] == champion_a['behavior_identity'] != winner_b
        finally:
            store.close()
        if fault == 'crash_before_result':
            def no_probe_publication(root, table, data_key, rows, **kwargs):
                if table == 'search_champions':
                    raise OSError('read-only incumbent inheritance probe')
                return api['write'](root, table, data_key, rows, **kwargs)
            baseline_probe.update(root=(tmp_path / 'while-pending').resolve(),
                expected=champion_a['behavior_identity'], score=None, samples=None, folder=None)
            try:
                with patch.object(result_store, '_api', return_value=dict(api, write=no_probe_publication)):
                    retained = dual_result(tmp_path / 'while-pending', raw, candidate_limit=5,
                        validation_batches=2, expected='cancelled')
            finally:
                baseline_probe['root'] = None
            assert_probe(retained, champion_a)
            def no_completed_scene_scoring(*args, **kwargs):
                if (kwargs.get('simulation_config') or {}).get('target_count', 1) == 1:
                    pytest.fail('已完成单场补成果或发布重复评分')
                return evaluate(*args, **kwargs)  # The untouched AOE scene may start normally.
            with patch.object(sequence, 'evaluate', side_effect=no_completed_scene_scoring):
                continued = resume()
            assert continued['scenes'][0]['search_result']['dps'] == intent['score']
            assert task.read_task(folder)['completed_batches'] == expected_batches
        final = task.read_task(folder)
        if fault == 'competition':
            assert final['search']['formal_champion_publication']['status'] == 'conflict'
            assert result_store.read_search_champion(key) == expected_incumbent
        else:
            assert continued['status'] == 'completed', continued
            assert final['status'] == 'completed'
            assert final['search']['formal_champion_publication']['status'] == 'published'
            incumbent = result_store.read_search_champion(key)
            assert incumbent['behavior_identity'] == winner_b
            assert incumbent['version'] == champion_a['version'] + 1
            assert incumbent['source_run_id'] == saved_a['run_id']
            expected_incumbent = incumbent
        if fault == 'competition':
            baseline_probe.update(root=(tmp_path / 'inherited').resolve(),
                expected=expected_incumbent['behavior_identity'], score=None, samples=None, folder=None)
            try:
                inherited = dual_result(tmp_path / 'inherited', raw, candidate_limit=5,
                    validation_batches=2, expected='cancelled')
            finally:
                baseline_probe['root'] = None
            assert_probe(inherited, expected_incumbent)
