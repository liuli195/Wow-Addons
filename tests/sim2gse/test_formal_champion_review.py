"""正式冠军独审发现的公开结果与恢复边界。"""
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
import pytest
from test_burst import page_task_engine, reviewed_fixture
from test_training_champion import champion_engine, dual_result
from test_seed_training import memory_result_center


@pytest.mark.parametrize('fault', ['database', 'publication_json'])
def test_public_saved_result_remains_readable_when_optional_checkpoint_metadata_is_broken(
        tmp_path, memory_result_center, champion_engine, fault):
    import burst
    import result_store
    import task
    definition, raw = reviewed_fixture()
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    burst.publish(definition)
    dual_result(tmp_path, raw, candidate_limit=1)
    folder = next((tmp_path / 'page' / 'tasks').glob('*/single_target'))
    before = task.read_task(folder)
    checkpoint = folder / 'task.sqlite3'
    if fault == 'database':
        checkpoint.write_bytes(b'constructed unreadable checkpoint')
    else:
        with sqlite3.connect(checkpoint) as database:
            database.execute("UPDATE state_fields SET value='{' WHERE key='formal_champion_publication'")
    after = task.read_task(folder)
    assert after['status'] == before['status'] == 'completed'
    assert after['candidate'] == before['candidate']
    assert after['search_result'] == before['search_result']
    assert after['search']['formal_champion_publication'] == before['search']['formal_champion_publication']
    with pytest.raises(task.TaskError):
        task.resume_task(folder)
    api = result_store._api()

    def unreadable_center(root, table, key, **kwargs):
        if table == 'runs':
            raise api['CorruptDataError']('constructed corrupt reliable center')
        return api['read_key'](root, table, key, **kwargs)

    with patch.object(result_store, '_api', return_value=dict(api, read_key=unreadable_center)):
        with pytest.raises(result_store.InvalidRecordError):
            task.read_task(folder)
