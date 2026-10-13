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
        candidate_limit=10, batch_targets=(2,), iterations=2, validation_batches=2,
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


@pytest.mark.parametrize('fault', ['none', 'publication', 'competition', 'crash_before_result', 'result_write', 'checkpoint_after_cas'])
def test_public_cancelled_winner_can_advance_and_recover_without_invalidating_its_published_source(
        tmp_path, monkeypatch, memory_result_center, champion_engine, fault):
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
    monkeypatch.setattr(engine, 'training_template', lambda: template)
    evaluate, store_run, api = sequence.evaluate, task._store_run, result_store._api()
    cancel_once, checkpoint_once = [True], [True]
    save_checkpoint = TaskStore.save

    def crash_after_cas(store):
        if (fault == 'checkpoint_after_cas' and checkpoint_once[0]
                and store.state.get('formal_champion_publication', {}).get('status') == 'published'):
            checkpoint_once[0] = False
            raise SystemExit('constructed process exit after CAS before publication checkpoint')
        return save_checkpoint(store)

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
            competing = dual_result(tmp_path / 'competing', raw, candidate_limit=10, validation_batches=2)
            expected_incumbent = result_store.read_search_champion(key)
            assert expected_incumbent['source_run_id'] == competing['scenes'][0]['formal_champion_publication']['source_run_id']
            assert expected_incumbent['behavior_identity'] != champion_a['behavior_identity']
        failing = [True]

        def save_result(destination, result, *, state=None):
            if (fault == 'crash_before_result' and failing[0] and Path(destination) == folder
                    and result.get('status') == 'completed'):
                failing[0] = False
                raise SystemExit('constructed process exit after completed checkpoint before result write')
            return store_run(destination, result, state=state)

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
             patch.object(result_store, '_api', return_value=dict(api, write=save_center)):
            continued = resume()
        store = TaskStore(folder)
        try:
            intent = store.state['formal_champion_publication_intent']['record']
            winner_b = intent['behavior_identity']
            assert winner_b != champion_a['behavior_identity']
            assert store.state['formal_champion_snapshot'] == scene['formal_champion_snapshot']
            if fault == 'result_write':
                store.state['elapsed_seconds'] = 600.
                store.save()
        finally:
            store.close()
        if fault in ('publication', 'crash_before_result', 'result_write'):
            def no_probe_publication(root, table, data_key, rows, **kwargs):
                if table == 'search_champions':
                    raise OSError('read-only incumbent inheritance probe')
                return api['write'](root, table, data_key, rows, **kwargs)
            with patch.object(result_store, '_api', return_value=dict(api, write=no_probe_publication)):
                retained = dual_result(tmp_path / 'while-pending', raw, candidate_limit=10, validation_batches=2)
            assert retained['scenes'][0]['formal_champion_snapshot']['behavior_identity'] == champion_a['behavior_identity']
            before_retry = task.read_task(folder)
            with patch.object(sequence, 'evaluate', side_effect=lambda *args, **kwargs: pytest.fail('补成果或发布重复评分')):
                continued = resume()
            assert continued['scenes'][0]['search_result']['dps'] == intent['score']
            assert task.read_task(folder)['completed_batches'] == before_retry['completed_batches']
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
        inherited = dual_result(tmp_path / 'inherited', raw, candidate_limit=10, validation_batches=2)
        assert inherited['scenes'][0]['formal_champion_snapshot']['behavior_identity'] == expected_incumbent['behavior_identity']
