"""正式默认起点与可选旧规则依赖保持原公开契约。"""
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
    assert result['search']['candidate_count'] >= len(result['search']['starts'])
    assert result['search']['stop_reason'] == 'stagnation'
    assert result['search']['complete_generations'] >= 2
    assert result['independent_validation_complete']
    assert not any(row.get('rule_diagnostics') for row in result['search']['records'])
