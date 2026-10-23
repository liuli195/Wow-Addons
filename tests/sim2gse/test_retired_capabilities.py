"""用户已移除两可选搜索能力；公开入口拒绝旧键而非静默关闭。"""
from pathlib import Path
import pytest


def test_public_formal_search_without_profession_rule_library_keeps_native_three_part_scope(
        tmp_path, monkeypatch):
    from unittest.mock import patch
    import engine
    from task import run_task, read_task, resume_task
    from test_search import _fast_search_boundary, _fast_reference, sample_profile
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(tmp_path / 'removed-rules.json'))
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile())
    def reference(*args, **kwargs):
        native = _fast_reference(*args, **kwargs)
        native['static_snapshot']['hero_subtree_ids'] = [32]
        return native
    with _fast_search_boundary(), patch.object(engine, 'reference', side_effect=reference):
        result = run_task(source, tmp_path / 'task', search_config=dict(candidate_limit=1,
            batch_targets=(2,), iterations=2, validation_batches=1))
        saved = read_task(tmp_path / 'task', include_search_records=True)
        assert saved['status'] == 'completed'
        assert saved['search']['configuration_key'] == dict(specialization_id=252,
            hero_talent='rider_of_the_apocalypse', target_type='single_target')
        assert len(result['search']['starts']) == 4
        assert all('rule_observations' not in row['request']
            for record in saved['search']['records'] for row in record['batches'])
        before = saved['search_result']
        assert resume_task(tmp_path / 'task')['status'] == 'completed'
        assert read_task(tmp_path / 'task')['search_result'] == before
    assert not (tmp_path / 'removed-rules.json').exists()


@pytest.mark.parametrize('key', ['adaptive_selector_enabled', 'rule_initialization_enabled', 'rule_diagnostics_policy'])
@pytest.mark.parametrize('value', [False, True])
def test_public_task_rejects_removed_capability_even_when_disabled(tmp_path, key, value):
    from task import run_task
    from test_search import _fast_search_boundary, sample_profile
    profile = tmp_path / 'role.simc'
    profile.write_text(sample_profile())
    with _fast_search_boundary(), pytest.raises(ValueError, match='已移除'):
        run_task(profile, tmp_path / 'task', search_config={key: value, 'candidate_limit': 1})


@pytest.mark.parametrize('key', ['adaptive_selector_enabled', 'rule_initialization_enabled', 'rule_diagnostics_policy'])
def test_public_task_rejects_removed_toml_before_reading_profile(tmp_path, monkeypatch, key):
    import simulation_config
    from task import run_task
    settings = tmp_path / 'settings.toml'
    settings.write_text('[search]\n' + key + ' = false\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    with pytest.raises(ValueError, match='已移除'):
        run_task(tmp_path / 'absent.simc', tmp_path / 'task')


@pytest.mark.parametrize('key', ['adaptive_selector_enabled', 'rule_initialization_enabled', 'rule_diagnostics_policy'])
def test_public_resume_rejects_removed_override_before_reading_old_task(tmp_path, key):
    from task import resume_task
    with pytest.raises(ValueError, match='已移除'):
        resume_task(tmp_path / 'absent', search_config={key: False})


@pytest.mark.parametrize('options', [{'rule_step': {}},
    {'diagnostic_candidate_key': 'old', 'diagnostic_budget_seconds': 1}])
def test_public_resume_rejects_retired_rule_edit_and_diagnosis_before_reading_task(tmp_path, options):
    from task import resume_task
    with pytest.raises(ValueError, match='已移除'):
        resume_task(tmp_path / 'absent', **options)


@pytest.mark.parametrize('command', ['rules-check', 'rules-save'])
def test_public_cli_rejects_retired_rule_editor(tmp_path, capsys, command):
    from task import main
    assert main([command, str(tmp_path / 'absent.json'), '--expected-digest', 'old']) == 2
    assert '已移除' in capsys.readouterr().err


def test_research_cli_rejects_retired_per_material_ab_execution_before_loading_materials(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(root / 'scripts/dev/sim2gse/population_ab.py'),
        '--materials', str(tmp_path / 'absent.json'), '--output', str(root / '.local/population-mvp/retired-mode'),
        '--check-only'], cwd=root, text=True, capture_output=True)
    assert result.returncode == 2
    assert '旧AB逐材料训练执行已移除' in result.stderr
    assert not (root / '.local/population-mvp/retired-mode').exists()


@pytest.mark.parametrize('command', ['task', 'seed_training'])
@pytest.mark.parametrize('flag', ['--adaptive-selector-enabled', '--no-adaptive-selector-enabled',
                                   '--rule-initialization-enabled', '--no-rule-initialization-enabled'])
def test_public_cli_rejects_removed_options_instead_of_silently_disabling(tmp_path, capsys, command, flag):
    from importlib import import_module
    args = (['--output', str(tmp_path / 'task')] if command == 'task' else
            ['--project', str(tmp_path), 'run'])
    with pytest.raises(SystemExit) as stopped:
        import_module(command).main([*args, flag])
    assert stopped.value.code == 2
    assert '已移除' in capsys.readouterr().err


@pytest.mark.parametrize('key', ['adaptive_selector_enabled', 'rule_initialization_enabled', 'rule_diagnostics_policy'])
def test_public_resume_refuses_incompatible_frozen_modes_without_rewriting_identity(tmp_path, key):
    from task import run_task, resume_task
    from search import TaskStore
    from test_search import _fast_search_boundary, sample_profile
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile())
    destination = tmp_path / 'task'
    with _fast_search_boundary():
        run_task(source, destination, search_config=dict(candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1))
        store = TaskStore(destination)
        try:
            store.state['config'][key] = False
            store.state['status'] = 'interrupted'
            store.save()
        finally:
            store.close()
        manifest = (destination / 'profile.json').read_bytes()
        with pytest.raises(ValueError, match='已移除.*身份不兼容'):
            resume_task(destination)
    assert (destination / 'profile.json').read_bytes() == manifest


def test_public_training_refuses_old_per_material_workspace_before_native(tmp_path, monkeypatch, installed_data_store):
    import shutil
    import result_store
    from seed_training import run_training
    from test_character_export import sample_profile
    from unittest.mock import patch
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    shutil.copytree(installed_data_store, tmp_path / '.local/skills/data-store')
    result_store.bind_project(tmp_path)
    source = tmp_path / 'role.simc'
    source.write_text(sample_profile())
    old = tmp_path / 'work/1/old-condition/identity.json'
    old.parent.mkdir(parents=True)
    old.write_text('{"format":1,"executions":[]}')
    before = old.read_bytes()
    with patch('engine.reference', side_effect=AssertionError('旧任务不允许进入新GA准备')):
        with pytest.raises(ValueError, match='旧逐材料.*不能.*恢复'):
            run_training(source, 1, tmp_path / 'work')
    assert old.read_bytes() == before


@pytest.fixture
def training_project(tmp_path, installed_data_store, monkeypatch):
    import shutil
    import result_store
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', None)
    shutil.copytree(installed_data_store, tmp_path / '.local/skills/data-store')
    result_store.bind_project(tmp_path)
    return tmp_path


from test_population_training import registered_six


def test_public_ga_without_profession_rule_library_publishes_native_scope(
        tmp_path, monkeypatch, training_project, registered_six):
    import engine
    from unittest.mock import patch
    from seed_training import run_training
    from test_seed_training import training_boundary
    from test_search import _fast_reference, sample_profile
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(tmp_path / 'removed-rules.json'))
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile())
    def reference(*args, **kwargs):
        native = _fast_reference(*args, **kwargs)
        native['static_snapshot']['hero_subtree_ids'] = [32]
        return native
    import simulation_config
    settings = tmp_path / 'config.toml'
    settings.write_text('[training]\ntop_k=4\ncrossover_probability=0.0\nmutation_probability=0.0\n')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    with training_boundary(), patch.object(engine, 'reference', side_effect=reference):
        result = run_training(template, 1, tmp_path / 'work')
    assert result['status'] == 'completed'
    assert result['configuration_key'] == dict(specialization_id=252,
        hero_talent='rider_of_the_apocalypse', target_type='single_target')
    assert result['selected'] == 4


def test_public_foreground_cancel_stops_both_active_ga_groups_and_keeps_old_publication(
        tmp_path, capsys, training_project, registered_six):
    import json
    import threading
    from unittest.mock import patch
    import sequence
    import result_store
    from seed_training import main, SELECTED_SCHEMA, shared_scope
    from seed_activity import foreground_search
    from test_seed_training import training_boundary
    from test_character_export import sample_profile
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile())
    previous = {}
    for target, scene in ((1, 'single_target'), (5, 'aoe')):
        key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type=scene)
        scope = shared_scope(key)
        row = dict(configuration_key=key, candidate_id='old', condition='old', class_name='deathknight',
            spec='unholy', targets=target, program=[['outbreak']], family='old', score=1., scores=[1.]*3,
            template_sha256='old', engines={})
        result_store.write('seed_selected', scope, [row], schema=SELECTED_SCHEMA)
        previous[scope] = result_store.read_records('seed_selected', scope)
    active, groups, lock, ready = [], set(), threading.Lock(), threading.Event()
    outcome = []
    def blocked(profile, candidate, folder, **options):
        scope = Path(folder).parts[Path(folder).parts.index('ga') + 1]
        with lock:
            active.append(scope)
            groups.add(scope)
            if len(groups) == 2: ready.set()
        try:
            assert options['runtime'].cancel_event.wait(8), '前台搜索须取消全部活跃组'
            options['runtime'].check()
        finally:
            with lock: active.remove(scope)
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1', '5',
        '--legacy', '--workspace', str(tmp_path / 'work'), '--max-trainings', '2', '--max-processes', '1']
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=blocked):
        worker = threading.Thread(target=lambda: outcome.append(main(args)))
        worker.start()
        try:
            assert ready.wait(8), '须真实同时进入两个GA组的原生边界'
            with foreground_search():
                worker.join(8)
        finally:
            worker.join(8)
    assert not worker.is_alive() and active == [] and len(groups) == 2
    assert outcome == [2]
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 2 and {row['status'] for row in output} == {'paused'}
    for scope, rows in previous.items():
        assert result_store.read_records('seed_selected', scope) == rows


def test_public_concurrent_prepare_uses_check_frozen_burst_identity_without_rediscovery(
        tmp_path, capsys, training_project, registered_six):
    import json
    import threading
    from unittest.mock import patch
    import burst
    import engine
    from seed_training import main
    from test_seed_training import training_boundary
    from test_character_export import sample_profile
    definition = json.loads(Path('projects/sim2gse/burst/unholy.json').read_text())
    definition['blocks'] = [[dict(kind='spell', simc_action='death_coil', name='死亡缠绕', spell_id=1002)]]
    definition['excluded_spell_ids'] = [1002]
    original = burst.publish(definition)
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile())
    barrier, changed = threading.Barrier(2), threading.Event()
    observed = []
    with training_boundary():
        reference, prepare = engine.reference, engine.prepare_loop
        def native(*args, **options):
            result = reference(*args, **options)
            result['identity']['data_version'] = original['data_version']
            barrier.wait(8)
            if options['simulation_config']['target_count'] == 1:
                burst.publish(dict(original, version=original['version'] + '-changed'))
                changed.set()
            assert changed.wait(8)
            return result
        def prepared(*args, **options):
            observed.append(options['definition']['definition_id'])
            return prepare(*args, **options)
        with patch.object(engine, 'reference', side_effect=native), \
                patch.object(engine, 'prepare_loop', side_effect=prepared), \
                patch.object(burst, 'select_definition', wraps=burst.select_definition) as discovery:
            status = main(['--project', str(tmp_path), 'prepare', '--template', str(template), '--targets', '1', '5',
                '--use-burst', '--workspace', str(tmp_path / 'work'), '--max-trainings', '2', '--max-processes', '1'])
    assert status == 0 and discovery.call_count == 1
    output = json.loads(capsys.readouterr().out)
    assert len(output) == 2 and {row['status'] for row in output} == {'prepared'}
    assert observed == [original['definition_id']] * 2
    assert burst.load(original['spec_id'])['definition_id'] != original['definition_id']


@pytest.mark.parametrize('options', [dict(diagnostics='full'),
    dict(search_observability='summary'), dict(search_observability='full')])
def test_public_pretraining_rejects_unsupported_observation_levels_before_any_work(tmp_path, monkeypatch, options):
    import engine
    from seed_training import run_training
    def forbidden(*args, **kwargs):
        raise AssertionError('不支持的预训练观测不得启动计算')
    monkeypatch.setattr(engine, 'reference', forbidden)
    with pytest.raises(ValueError, match='预训练仅支持基础性能日志和时间DPS曲线'):
        run_training(tmp_path / 'absent.simc', 1, tmp_path / 'work',
            diagnostic_logging=True, search_config=options)
    assert not (tmp_path / 'work').exists()
