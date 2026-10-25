"""正式默认起点及关闭的旧规则入口，直接运行现有GA/原SQL。"""
from test_population_training import memory_ga


def test_default_task_keeps_old_starts_without_rule_generation(memory_ga):
    from search import initial_programs
    from test_search import _fast_capabilities
    capabilities = _fast_capabilities()
    native = dict(action_sequence=[dict(name=name) for name in
        ('outbreak', 'death_coil', 'scourge_strike')])
    starts = initial_programs(capabilities, native)
    ga = memory_ga(formal=True, programs=starts)
    result = ga.run()
    assert result['status'] == 'completed'
    assert 'rule_initialization_enabled' not in ga.store.state['config']
    assert 'adaptive_selector_enabled' not in ga.store.state['config']
    assert not ga.store.state.get('rule_initialization')
    assert result['search']['starts'][0] == [
        ['outbreak'], ['death_coil'], ['scourge_strike'], ['dark_transformation'], ['use_item,slot=trinket1']]


def test_default_search_expands_without_selector_or_rule_diagnostics(memory_ga, monkeypatch):
    # DEAP's declared dependencies are prepared, not claimed optional/uninstalled.
    from deap import algorithms, base, creator, tools
    import builtins
    ga = memory_ga(formal=True)
    original_import = builtins.__import__
    def without_selector(name, *args, **kwargs):
        if name == 'selector':
            raise AssertionError('OFF must not import the selector')
        if name in ('numpy', 'coba'):
            raise ModuleNotFoundError('optional runtime import unavailable: ' + name)
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_selector)
    result = ga.run()
    assert result['status'] == 'completed'
    assert result['search']['candidate_count'] >= len(result['search']['starts'])
    assert result['search']['stop_reason'] == 'stagnation'
    assert result['search']['complete_generations'] >= 2
    assert result['independent_validation_complete']
    assert not any(row.get('rule_diagnostics') for row in result['search']['records'])
