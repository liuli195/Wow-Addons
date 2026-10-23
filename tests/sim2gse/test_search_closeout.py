"""正式收尾通过公开任务入口冻结两个独立算法选择。"""
from pathlib import Path

import pytest

from task import run_task
from test_character_export import sample_profile






def test_default_task_keeps_old_starts_without_rule_generation(tmp_path, monkeypatch):
    from test_search import _fast_search_boundary
    from task import read_task
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=2))
        saved = read_task(tmp_path / 'task')
    assert result['status'] == 'completed'
    assert 'rule_initialization_enabled' not in saved['config']
    assert 'adaptive_selector_enabled' not in saved['config']
    assert not saved.get('rule_initialization')
    assert result['search']['starts'][0] == [
        ['outbreak'], ['death_coil'], ['scourge_strike'], ['dark_transformation'], ['use_item,slot=trinket1']]


def test_default_search_expands_without_selector_or_rule_diagnostics(tmp_path, monkeypatch):
    from test_search import _fast_search_boundary
    import builtins
    original_import = builtins.__import__
    def without_selector(name, *args, **kwargs):
        if name == 'selector':
            raise AssertionError('OFF must not import the selector')
        if name in ('numpy', 'coba'):
            raise ModuleNotFoundError('optional dependency unavailable: ' + name)
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_selector)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=6, round_candidate_limit=2, batch_targets=(2,), iterations=2, validation_batches=2))
    assert result['status'] == 'completed'
    assert result['search']['candidate_count'] == 6
    assert not any(row.get('rule_diagnostics') for row in result['search']['records'])














@pytest.mark.parametrize('promotion', ['route', 'global', 'rejected', 'none'])
def test_shared_early_stop_counts_only_verified_progress(tmp_path, promotion):
    import json
    from test_search import _prepared_search_boundary
    from test_search import _fast_evaluate
    starts = [
        [['outbreak'], ['scourge_strike'], ['epidemic'], ['death_coil']],
        [['outbreak'], ['scourge_strike'], ['death_coil']],
    ]
    def scored(profile, candidate, folder, **kwargs):
        result = _fast_evaluate(profile, candidate, folder, **kwargs)
        blocks = result['blocks']
        damage = (1000.0 if blocks == starts[0] else 100.0 if blocks == starts[1]
                  else 2000.0 if promotion == 'global' else 200.0)
        if promotion == 'none' or (promotion == 'rejected' and 20360912 <= kwargs['seed'] < 20460912):
            damage = 1000.0 if blocks == starts[0] else 100.0
        result['summary']['dps'] = damage
        result['report']['sim']['statistics']['raid_dps']['mean'] = damage
        result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
        (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _prepared_search_boundary(tmp_path, starts, evaluate=scored):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200,
            candidate_limit=16, round_candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=2, max_processes=1))
    assert result['status'] == 'completed'
    assert result['search']['stop_reason'] == 'no_improvement'
    assert result['search']['no_improvement_round_limit'] == 2
    if promotion == 'global':
        assert result['search']['rounds'] >= 3
    else:
        assert result['search']['rounds'] == (4 if promotion == 'route' else 2)
    assert result['search_result']['dps'] == (2000.0 if promotion == 'global' else 1000.0)


@pytest.mark.parametrize('limit,improve,expected', [(2, False, 0), (5, False, 1), (5, True, 0)])
def test_shared_early_stop_initialization_and_partial_round(tmp_path, limit, improve, expected):
    import json
    import sqlite3
    from test_search import _prepared_search_boundary
    from test_search import _fast_evaluate
    starts = [[['outbreak'], ['scourge_strike'], ['epidemic'], ['death_coil']],
              [['outbreak'], ['scourge_strike'], ['death_coil']]]
    scores = {json.dumps(starts[0]): 1000.0, json.dumps(starts[1]): 100.0}
    def scored(profile, candidate, folder, **kwargs):
        result = _fast_evaluate(profile, candidate, folder, **kwargs)
        key = json.dumps(result['blocks'])
        if key not in scores:
            scores[key] = 200.0 if improve and len(scores) >= 4 else 100.0
        damage = scores[key]
        result['summary']['dps'] = damage
        result['report']['sim']['statistics']['raid_dps']['mean'] = damage
        result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
        (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _prepared_search_boundary(tmp_path, starts, evaluate=scored):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            input_interval_ms=200,
            candidate_limit=limit, round_candidate_limit=2, batch_targets=(2,),
            iterations=2, validation_batches=2, max_processes=1))
    with sqlite3.connect(tmp_path / 'task/task.sqlite3') as database:
        raw, = database.execute("SELECT value FROM state_fields WHERE key='no_improvement'").fetchone()
    assert json.loads(raw) == expected
    assert result['search']['rounds'] == (0 if limit == 2 else 2)
    assert result['search']['partial_round'] is (limit == 5)
    assert result['search_result']['dps'] == 1000.0
