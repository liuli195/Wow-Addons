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


@pytest.mark.parametrize('fault', ['none', 'publication', 'competition', 'crash_before_result', 'result_write', 'checkpoint_after_cas',
    'saved_run_failed_checkpoint'])
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
    program = [['death_coil']] * 20 + [dict(kind='WaitClicks', clicks=17), ['outbreak']]
    template, _ = completed_training(tmp_path, 1, [(program, [200.] * 3)])
    monkeypatch.setattr(engine, '_training_template', lambda manifest: template)
    evaluate, store_run, write_json, api = sequence.evaluate, task._store_run, task._write_json, result_store._api()
    cancel_once, checkpoint_once = [True], [True]
    save_checkpoint = TaskStore.save
    baseline_probe = dict(root=None, expected=None, score=None, samples=None, folder=None)

    def crash_after_cas(store):
        if (fault == 'checkpoint_after_cas' and checkpoint_once[0]
                and store.state.get('formal_champion_publication', {}).get('status') == 'published'):
            checkpoint_once[0] = False
            raise SystemExit('constructed process exit after CAS before publication checkpoint')
        saved = save_checkpoint(store)
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
         patch.object(TaskStore, 'save', crash_after_cas), dual_page(tmp_path / 'original', raw) as (read, resume):
        first = read()
        assert first['status'] == ('failed' if fault == 'checkpoint_after_cas' else 'cancelled')
        scene = first['scenes'][0]
        folder = next((tmp_path / 'original' / 'page' / 'tasks').glob('*/single_target'))
        saved_a = task.read_task(folder)
        key = scene['formal_champion_snapshot']['condition_key']
        champion_a = result_store.read_search_champion(key)
        assert champion_a['source_run_id'] == saved_a['run_id']
        assert champion_a['version'] == 1
        if fault == 'checkpoint_after_cas':
            store = TaskStore(folder)
            try:
                assert not store.state.get('formal_champion_last_published')
                assert store.state['formal_champion_publication']['status'] == 'pending'
            finally:
                store.close()
        expected_incumbent = champion_a
        if fault == 'competition':
            stronger = [['death_coil']] * 30 + [dict(kind='WaitClicks', clicks=88), ['outbreak']]
            completed_training(tmp_path, 1, [(stronger, [300.] * 3)], name='newer')
            competing = dual_result(tmp_path / 'competing', raw, candidate_limit=5, validation_batches=2)
            expected_incumbent = result_store.read_search_champion(key)
            assert expected_incumbent['source_run_id'] == competing['scenes'][0]['formal_champion_publication']['source_run_id']
            assert expected_incumbent['behavior_identity'] != champion_a['behavior_identity']
        failing = [True]

        def save_result(destination, result, *, state=None):
            if (fault == 'crash_before_result' and failing[0] and Path(destination) == folder
                    and result.get('status') == 'completed'):
                failing[0] = False
                raise SystemExit('constructed process exit after completed checkpoint before result write')
            if (fault == 'saved_run_failed_checkpoint' and failing[0] and Path(destination) == folder
                    and result.get('status') == 'failed'):
                failing[0] = False
                raise OSError('constructed failed result replacement failure')
            return store_run(destination, result, state=state)

        def save_pointer(destination, value, **kwargs):
            if (fault == 'saved_run_failed_checkpoint' and failing[0]
                    and Path(destination) == folder / 'result.json' and value.get('status') == 'completed'):
                raise OSError('constructed completed result pointer failure')
            return write_json(destination, value, **kwargs)

        def save_center(root, table, data_key, rows, **kwargs):
            if failing[0] and table == 'search_champions' and fault == 'publication':
                if rows[0]['behavior_identity'] != champion_a['behavior_identity']:
                    raise OSError('constructed new winner publication failure')
            if (failing[0] and fault == 'result_write' and table == 'runs'
                    and data_key == saved_a['run_id'] and rows[0]['status'] == 'completed'):
                failing[0] = False
                raise OSError('constructed completed result write failure')
            return api['write'](root, table, data_key, rows, **kwargs)

        with patch.object(task, '_store_run', side_effect=save_result), \
             patch.object(task, '_write_json', side_effect=save_pointer), \
             patch.object(result_store, '_api', return_value=dict(api, write=save_center)):
            continued = resume()
        store = TaskStore(folder)
        try:
            intent = store.state['formal_champion_publication_intent']['record']
            winner_b = intent['behavior_identity']
            assert winner_b != champion_a['behavior_identity']
            assert store.state['formal_champion_snapshot'] == scene['formal_champion_snapshot']
            expected_batches = store.state['completed_batches']
            if fault == 'saved_run_failed_checkpoint':
                assert store.state['status'] == 'failed'
                assert result_store.read_records('runs', saved_a['run_id'])[0]['status'] == 'completed'
            if fault in ('result_write', 'saved_run_failed_checkpoint'):
                store.state['elapsed_seconds'] = 600.
                store.save()
        finally:
            store.close()
        if fault in ('publication', 'crash_before_result', 'result_write', 'saved_run_failed_checkpoint'):
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
        baseline_probe.update(root=(tmp_path / 'inherited').resolve(),
            expected=expected_incumbent['behavior_identity'], score=None, samples=None, folder=None)
        try:
            inherited = dual_result(tmp_path / 'inherited', raw, candidate_limit=5,
                validation_batches=2, expected='cancelled')
        finally:
            baseline_probe['root'] = None
        assert_probe(inherited, expected_incumbent)
