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
