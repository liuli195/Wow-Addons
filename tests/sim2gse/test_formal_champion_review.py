"""正式冠军独审发现的公开结果与恢复边界。"""
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
import pytest
from test_burst import page_task_engine, reviewed_fixture
from test_training_champion import champion_engine, dual_result
from test_seed_training import memory_result_center


def test_public_saved_result_remains_readable_when_optional_checkpoint_metadata_is_broken(
        tmp_path, memory_result_center, champion_engine, subtests):
    from contextlib import closing
    import shutil
    import burst
    import result_store
    import task
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    dual_result(tmp_path / 'original', raw, candidate_limit=1)
    source = next((tmp_path / 'original' / 'page' / 'tasks').glob('*/single_target'))
    before = task.read_task(source)
    # The HTTP worker has joined and every TaskStore is closed; fold any committed WAL into the DB.
    with closing(sqlite3.connect(source / 'task.sqlite3')) as database:
        assert database.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0
    checkpoint_bytes = (source / 'task.sqlite3').read_bytes()
    api = result_store._api()
    for fault in ('database', 'publication_json', 'publication_list', 'publication_null',
                  'publication_string', 'publication_status'):
        with subtests.test(fault=fault):
            folder = tmp_path / 'faults' / fault / 'single_target'
            shutil.copytree(source, folder, ignore=shutil.ignore_patterns('*-wal', '*-shm'))
            checkpoint = folder / 'task.sqlite3'
            if fault == 'database':
                checkpoint.write_bytes(b'constructed unreadable checkpoint')
            else:
                with closing(sqlite3.connect(checkpoint)) as database, database:
                    value = {'publication_json': '{', 'publication_list': '[]', 'publication_null': 'null',
                             'publication_string': '"bad"', 'publication_status': '{"status":"unsupported"}'}[fault]
                    updated = database.execute(
                        "UPDATE state_fields SET value=? WHERE key='formal_champion_publication'", [value])
                    assert updated.rowcount == 1
            after = task.read_task(folder)
            assert after['status'] == before['status'] == 'completed'
            assert after['candidate'] == before['candidate']
            assert after['search_result'] == before['search_result']
            assert after['search']['formal_champion_publication'] == before['search']['formal_champion_publication']
            verification = after['search']['formal_champion_publication_verification']
            assert verification['status'] == 'unknown'
            assert verification['reason']
            with pytest.raises((task.TaskError, sqlite3.Error, ValueError)):
                task.resume_task(folder)

            def unreadable_center(root, table, key, **kwargs):
                if table == 'runs':
                    raise api['CorruptDataError']('constructed corrupt reliable center')
                return api['read_key'](root, table, key, **kwargs)

            with patch.object(result_store, '_api', return_value=dict(api, read_key=unreadable_center)):
                with pytest.raises(task.TaskError, match='结果中心目标记录损坏'):
                    task.read_task(folder)
            assert result_store._api() is api
            assert (source / 'task.sqlite3').read_bytes() == checkpoint_bytes
            assert task.read_task(source)['search']['formal_champion_publication'] == before['search']['formal_champion_publication']
