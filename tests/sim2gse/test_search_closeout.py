"""正式收尾通过公开任务入口冻结两个独立算法选择。"""
from pathlib import Path

import pytest

from task import run_task
from test_character_export import sample_profile


def test_task_rejects_non_boolean_exploration_flag(tmp_path):
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with pytest.raises(ValueError, match='rule_initialization_enabled.*布尔'):
        run_task(source, tmp_path / 'task', search_config={'rule_initialization_enabled': 1})


def test_task_reads_search_configuration_before_validating_input(tmp_path, monkeypatch):
    import simulation_config
    settings = tmp_path / 'config.toml'
    settings.write_text('[search]\nrule_initialization_enabled = 1\n', encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    with pytest.raises(ValueError, match='rule_initialization_enabled.*布尔'):
        run_task(tmp_path / 'absent.simc', tmp_path / 'task')


def test_default_task_keeps_old_starts_without_rule_generation(tmp_path, monkeypatch):
    from test_search import _fast_search_boundary
    from task import read_task
    import rule_initialization
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('OFF must not generate a rule start')
    monkeypatch.setattr(rule_initialization, 'generate', forbidden)
    with _fast_search_boundary():
        result = run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=2))
        saved = read_task(tmp_path / 'task')
    assert result['status'] == 'completed'
    assert saved['config']['rule_initialization_enabled'] is False
    assert saved['config']['adaptive_selector_enabled'] is False
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


@pytest.mark.parametrize('rules,selector', [(False, False), (True, False), (False, True), (True, True)])
def test_independent_exploration_combinations_complete_and_reload(tmp_path, rules, selector):
    from test_search import _guided_search_boundary
    from task import read_task
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _guided_search_boundary(tmp_path, [[['outbreak'], ['death_coil'], ['scourge_strike']]]):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            rule_initialization_enabled=rules, adaptive_selector_enabled=selector,
            input_interval_ms=200, candidate_limit=3, round_candidate_limit=1,
            batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task')
    assert result['status'] == saved['status'] == 'completed'
    assert bool(saved.get('rule_initialization')) is rules
    assert saved['config']['adaptive_selector_enabled'] is selector
    import json
    import sqlite3
    with sqlite3.connect(tmp_path / 'task/task.sqlite3') as database:
        raw, = database.execute("SELECT value FROM state_fields WHERE key='rule_context'").fetchone()
    assert 'rule_snapshot' not in json.loads(raw)


def test_enabled_selector_reports_missing_optional_dependencies(tmp_path, monkeypatch):
    import builtins
    from test_search import _fast_search_boundary
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == 'coba':
            raise ModuleNotFoundError('coba unavailable')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', missing)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary(), pytest.raises(ValueError, match='requirements-selector.txt'):
        run_task(source, tmp_path / 'task', search_config={'adaptive_selector_enabled': True})


def test_task_cli_explicit_false_overrides_enabled_config(tmp_path, monkeypatch, capsys):
    import simulation_config
    import rule_initialization
    from task import main, read_task
    from test_search import _fast_search_boundary
    settings = tmp_path / 'config.toml'
    settings.write_text('[search]\nrule_initialization_enabled = true\nadaptive_selector_enabled = true\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    def forbidden(*args, **kwargs):
        raise AssertionError('显式关闭应覆盖配置开启')
    monkeypatch.setattr(rule_initialization, 'generate', forbidden)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    import sequence
    def cancelled_score(*args, **kwargs):
        kwargs['runtime'].cancel()
        kwargs['runtime'].check()
    with _fast_search_boundary(), monkeypatch.context() as scoped:
        scoped.setattr(sequence, 'evaluate', cancelled_score)
        assert main([str(source), '--output', str(tmp_path / 'task'),
            '--no-rule-initialization-enabled', '--no-adaptive-selector-enabled']) == 0
        result = read_task(tmp_path / 'task')
    assert result['config']['rule_initialization_enabled'] is False
    assert result['config']['adaptive_selector_enabled'] is False


def test_old_task_without_frozen_modes_is_readable_but_cannot_resume(tmp_path):
    import json
    import sqlite3
    from task import read_task, resume_task, TaskError
    from test_search import _fast_search_boundary
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary():
        run_task(source, tmp_path / 'task', search_config=dict(
            candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        with sqlite3.connect(tmp_path / 'task/task.sqlite3') as database:
            raw, = database.execute("SELECT value FROM state_fields WHERE key='config'").fetchone()
            config = json.loads(raw)
            for key in ('rule_initialization_enabled', 'adaptive_selector_enabled', 'search_timeline'):
                config.pop(key)
            database.execute("UPDATE state_fields SET value=? WHERE key='config'", (json.dumps(config),))
        assert read_task(tmp_path / 'task')['status'] == 'completed'
        with pytest.raises(TaskError, match='旧任务未冻结搜索开关'):
            resume_task(tmp_path / 'task')


def test_rule_start_replaces_only_uniform_slot(tmp_path):
    from test_search import _fast_search_boundary
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _fast_search_boundary():
        results = [run_task(source, tmp_path / str(enabled), search_config=dict(
            rule_initialization_enabled=enabled, candidate_limit=4,
            batch_targets=(2,), iterations=2, validation_batches=1)) for enabled in (False, True)]
    old, new = (result['search']['starts'] for result in results)
    assert len(old) == len(new) == 4
    assert old[0] != new[0]
    assert old[1:] == new[1:]


def test_manual_diagnosis_of_selector_task_never_imports_model(tmp_path, monkeypatch):
    import builtins
    import sequence
    from task import resume_task
    from test_rule_diagnostics import (_configure_opener, _condition_pack, apl_pool_reference,
        _apl_task_boundary, _observed_evaluate, _fast_evaluate)
    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    native = apl_pool_reference()
    for row in native['static_snapshot']['actions']:
        row['gcd_ms'] = 200
    def scoring(*args, **kwargs):
        return (_observed_evaluate if kwargs.get('rule_observation_request') is not None
                else _fast_evaluate)(*args, **kwargs)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile(), encoding='utf-8')
    with _apl_task_boundary(native), monkeypatch.context() as scoped:
        scoped.setattr(sequence, 'evaluate', scoring)
        original = run_task(source, tmp_path / 'task', simulation_config=dict(scene='single_target'),
            search_config=dict(adaptive_selector_enabled=True, input_interval_ms=200,
                candidate_limit=1, batch_targets=(2,), iterations=2, validation_batches=1))
        original_import = builtins.__import__
        def forbidden(name, *args, **kwargs):
            if name in ('selector', 'numpy', 'coba'):
                raise AssertionError('Independent diagnosis must not import model: ' + name)
            return original_import(name, *args, **kwargs)
        scoped.setattr(builtins, '__import__', forbidden)
        diagnosed = resume_task(tmp_path / 'task', diagnostic_candidate_key=original['selected_candidate_key'],
            diagnostic_budget_seconds=10)
    assert diagnosed['search']['rule_diagnostic_status'] == 'complete'
    assert 'selection_context' not in diagnosed['search']['rule_diagnostics']
    assert diagnosed['config']['adaptive_selector_enabled'] is True


@pytest.mark.parametrize('selector', [False, True])
@pytest.mark.parametrize('promotion', ['route', 'global', 'rejected', 'none'])
def test_shared_early_stop_counts_only_verified_progress(tmp_path, selector, promotion):
    import json
    from test_search import _guided_search_boundary
    from test_rule_diagnostics import _observed_evaluate
    starts = [
        [['outbreak'], ['scourge_strike'], ['epidemic'], ['death_coil']],
        [['outbreak'], ['scourge_strike'], ['death_coil']],
    ]
    def scored(profile, candidate, folder, **kwargs):
        result = _observed_evaluate(profile, candidate, folder, **kwargs)
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
    with _guided_search_boundary(tmp_path, starts, evaluate=scored):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            adaptive_selector_enabled=selector, input_interval_ms=200,
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


@pytest.mark.parametrize('selector', [False, True])
@pytest.mark.parametrize('limit,improve,expected', [(2, False, 0), (5, False, 1), (5, True, 0)])
def test_shared_early_stop_initialization_and_partial_round(tmp_path, selector, limit, improve, expected):
    import json
    import sqlite3
    from test_search import _guided_search_boundary
    from test_rule_diagnostics import _observed_evaluate
    starts = [[['outbreak'], ['scourge_strike'], ['epidemic'], ['death_coil']],
              [['outbreak'], ['scourge_strike'], ['death_coil']]]
    scores = {json.dumps(starts[0]): 1000.0, json.dumps(starts[1]): 100.0}
    def scored(profile, candidate, folder, **kwargs):
        result = _observed_evaluate(profile, candidate, folder, **kwargs)
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
    with _guided_search_boundary(tmp_path, starts, evaluate=scored):
        result = run_task(source, tmp_path / 'task', search_config=dict(
            adaptive_selector_enabled=selector, input_interval_ms=200,
            candidate_limit=limit, round_candidate_limit=2, batch_targets=(2,),
            iterations=2, validation_batches=2, max_processes=1))
    with sqlite3.connect(tmp_path / 'task/task.sqlite3') as database:
        raw, = database.execute("SELECT value FROM state_fields WHERE key='no_improvement'").fetchone()
    assert json.loads(raw) == expected
    assert result['search']['rounds'] == (0 if limit == 2 else 2)
    assert result['search']['partial_round'] is (limit == 5)
    assert result['search_result']['dps'] == 1000.0
