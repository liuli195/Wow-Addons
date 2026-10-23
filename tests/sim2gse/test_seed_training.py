"""Manual training command uses the existing installed data center."""
import json
from pathlib import Path
import subprocess
import shutil
import sys
import sqlite3
from contextlib import closing, contextmanager


@contextmanager
def training_boundary(damage_for=lambda candidate: 100.):
    from test_search import _fast_search_boundary, _fast_evaluate
    from unittest.mock import patch
    import sequence

    def evaluate(profile, candidate, folder, **kwargs):
        kwargs.pop('input_sources', None)
        kwargs.pop('burst_candidate', None)
        return _fast_evaluate(profile, candidate, folder, score=damage_for(candidate), **kwargs)

    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        yield





import pytest


@pytest.fixture(autouse=True)
def training_center(tmp_path, installed_data_store, monkeypatch):
    import result_store
    (tmp_path / 'data').mkdir(exist_ok=True)
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', None)
    # 业务检查使用隔离安装副本；官方 connect/Junction 由 test_data_store_connection 专项验证。
    shutil.copytree(installed_data_store, tmp_path / '.local/skills/data-store',
                    ignore=shutil.ignore_patterns('__pycache__'))


@pytest.fixture
def memory_result_center(installed_data_store_api, monkeypatch):
    """纯逻辑检查的中心IO；TaskStore/报告位置清单仍真实，不证明Parquet耐久性。"""
    import duckdb
    import threading
    import result_store

    groups = {}
    lock = threading.RLock()
    with duckdb.connect(':memory:', config={'threads': 1}) as database, monkeypatch.context() as scoped:
        def write(root, table, key, rows, *, schema=None, binary=False):
            table = installed_data_store_api['_name'](table, table=True)
            key = installed_data_store_api['_name'](key)
            group = f'"_memory_{table}_{key}"'
            with lock, database.cursor() as cursor:
                if binary:
                    records = installed_data_store_api['_binary_records'](cursor, rows, schema)
                    try:
                        records.create_view('_binary_records_view', replace=True)
                        cursor.execute(f'CREATE OR REPLACE TABLE {group} AS SELECT * FROM _binary_records_view')
                    finally:
                        cursor.execute('DROP VIEW IF EXISTS _binary_records_view')
                else:
                    payload = json.dumps(rows, ensure_ascii=False, allow_nan=False)
                    structure = (json.dumps([schema]) if schema is not None else
                                 cursor.execute('SELECT json_structure(?)', [payload]).fetchone()[0])
                    if schema is None and installed_data_store_api['_opaque'](json.loads(structure)):
                        raise ValueError('无法推断有类型的记录，请明确提供字段类型')
                    transform = 'from_json_strict' if schema is not None else 'from_json'
                    cursor.execute(f'CREATE OR REPLACE TABLE {group} AS SELECT record.* FROM '
                                   f'(SELECT unnest({transform}(?, ?)) AS record)', [payload, structure])
                groups.setdefault(table, {})[key] = group
                sources = ' UNION ALL BY NAME '.join(f'SELECT * FROM {name}'
                                                    for name in groups[table].values())
                cursor.execute(f'CREATE OR REPLACE VIEW "{table}" AS {sources}')
            return len(rows)

        def query(root, sql, parameters=None, *, tables):
            if not isinstance(tables, (list, tuple)) or not tables:
                raise ValueError('tables 必须是非空逻辑表名列表')
            for table in tables:
                installed_data_store_api['_name'](table, table=True)
            with lock:
                cursor = database.cursor()
                try:
                    return cursor.execute(sql, parameters if parameters is not None else [])
                except BaseException:
                    cursor.close()
                    raise

        def read_key(root, table, key, *, columns=None, filters=None):
            return read_keys(root, table, [key], columns=columns, filters=filters)

        def read_keys(root, table, keys, *, columns=None, filters=None):
            table = installed_data_store_api['_name'](table, table=True)
            if not isinstance(keys, (list, tuple)) or not keys:
                raise ValueError('记录键必须是非空列表')
            keys = list(dict.fromkeys(installed_data_store_api['_name'](key) for key in keys))
            with lock:
                for key in keys:
                    if key not in groups.get(table, {}):
                        raise installed_data_store_api['MissingKeyError'](key)
                projection = ','.join('"' + name.replace('"', '""') + '"' for name in columns) if columns else '*'
                predicate = (' WHERE ' + ' AND '.join('"' + name.replace('"', '""') +
                             '" IS NOT DISTINCT FROM ?' for name in filters)) if filters else ''
                selected = ' UNION ALL BY NAME '.join(
                    f'SELECT * FROM {groups[table][key]}' for key in keys)
                return query(root, f'SELECT {projection} FROM ({selected}) AS records{predicate}',
                             list(filters.values()) if filters else [], tables=[table])

        api = dict(write=write, query=query, read_key=read_key, read_keys=read_keys,
                   DATA_STORE_CAPABILITIES=installed_data_store_api.get('DATA_STORE_CAPABILITIES', ()),
                   **{name: installed_data_store_api[name] for name in ('MissingKeyError', 'CorruptDataError')})
        scoped.setattr(result_store, '_api', lambda: api)
        yield


@pytest.fixture
def memory_training_center(training_center, memory_result_center):
    yield




def command(tmp_path, args):
    from seed_training import main
    # 仅关闭独立爆发；prepare/run均使用唯一GA实现。
    if args[0] in ('run', 'prepare', 'list') and '--use-burst' not in args:
        args = [*args, '--legacy']
    if args[0] == 'list' and '--state' in args and args[args.index('--state') + 1] in ('selected', 'processed') and '--specialization-id' not in args:
        count = int(args[args.index('--targets') + 1]) if '--targets' in args else 1
        args = [*args, '--specialization-id', '252', '--hero-talent', 'rider_of_the_apocalypse',
                '--target-type', 'single_target' if count == 1 else 'aoe']
    return main(['--project', str(tmp_path), *args])


def test_training_check_locates_current_template_without_starting_compute(tmp_path, capsys, monkeypatch):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('只读训练检查不能启动计算进程')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    import engine
    from test_search import _fast_identity, _fast_training_template
    monkeypatch.setattr(engine, "identity", _fast_identity)
    monkeypatch.setattr(engine, "_training_template", _fast_training_template)
    assert main(['--project', str(tmp_path), 'check', '--legacy']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'ready'
    assert '/.tools/sim2gse/build/baseline/' in result['template'].replace('\\', '/')
    assert result['engines']['baseline']['upstream_commit'] == result['engines']['controlled']['upstream_commit']
    assert not (tmp_path / 'work').exists()


@pytest.mark.parametrize('entry', ['run'])
def test_training_entry_refuses_missing_definition_before_starting_compute(tmp_path, capsys, monkeypatch, entry):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('缺少审核定义时不能启动计算进程')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    import engine
    from test_search import _fast_identity, _fast_training_template
    monkeypatch.setattr(engine, 'identity', _fast_identity)
    monkeypatch.setattr(engine, '_training_template', _fast_training_template)
    assert main(['--project', str(tmp_path), entry,
                 '--workspace', str(tmp_path / 'work')]) == 2
    assert '已审核' in capsys.readouterr().err


@pytest.mark.parametrize('entry', ['run', 'prepare'])
def test_training_cli_override_repairs_partial_config_without_precheck_losing_it(
        tmp_path, capsys, monkeypatch, memory_training_center, entry):
    from itertools import permutations
    from seed_training import main
    from test_character_export import sample_profile
    import simulation_config

    config = tmp_path / 'training.toml'
    config.write_text('[training]\nmax_trainings=10\ntop_k=4\n'
                      'crossover_probability=0.0\nmutation_probability=0.0\n', encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    material = tmp_path / 'material.json'
    for index, actions in enumerate(list(permutations(('outbreak', 'death_coil', 'scourge_strike')))[:4]):
        material.write_text(json.dumps(dict(label=str(index), class_name='deathknight', spec='unholy',
            source='fixture', original='fixture', instructions='repeat', semantic='preserved', changes=[],
            family='fixture', core=[], program=[[action] for action in actions])), encoding='utf-8')
        assert command(tmp_path, ['register', str(material)]) == 0
    capsys.readouterr()
    with training_boundary():
        assert command(tmp_path, [entry, '--template', str(template), '--targets', '1', '--max-processes', '2',
                                 '--workspace', str(tmp_path / 'work')]) == 0
    outcome = json.loads(capsys.readouterr().out)[0]
    assert outcome['status'] == ('completed' if entry == 'run' else 'prepared')
    if entry == 'run':
        assert outcome['training_config']['max_trainings'] == 10
        assert outcome['training_config']['max_processes'] == 2
    # 独立check仍校验文件本身，不继承上一条CLI调用的覆盖值。
    with training_boundary():
        assert main(['--project', str(tmp_path), 'check', '--template', str(template), '--legacy']) == 2
    assert '乘积不得超过20' in capsys.readouterr().err


@pytest.mark.parametrize(('settings', 'expected'), [
    ('', ('8候选', '120请求批', '15360请求迭代')),
    ('top_k=4\nretest_batches=2\nretest_iterations=7\n', ('4候选', '40请求批', '280请求迭代')),
])
def test_training_run_shows_requested_retest_maximum_before_compute_and_keeps_it_on_resume(
        tmp_path, capsys, monkeypatch, memory_training_center, settings, expected):
    from itertools import permutations
    from unittest.mock import patch
    from test_character_export import sample_profile
    from test_search import _fast_evaluate
    from runtime import TaskCancelled
    import engine
    import sequence
    import simulation_config

    config = tmp_path / 'training.toml'
    config.write_text('[training]\nmax_trainings=1\nmax_processes=1\n'
                      'crossover_probability=0.0\nmutation_probability=0.0\n' + settings, encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    material = tmp_path / 'material.json'
    for index, actions in enumerate(list(permutations(('outbreak', 'death_coil', 'scourge_strike')))[:4]):
        material.write_text(json.dumps(dict(label=str(index), class_name='deathknight', spec='unholy',
            source='fixture', original='fixture', instructions='repeat', semantic='preserved', changes=[],
            family='fixture', core=[], program=[[action] for action in actions])), encoding='utf-8')
        assert command(tmp_path, ['register', str(material)]) == 0
    capsys.readouterr()
    options = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    for resume in (False, True):
        checked = []

        def check_startup():
            if not checked:
                message = capsys.readouterr()
                assert all(value in message.err for value in expected)
                assert '五场景复测' in message.err and '非实际有效样本' in message.err
                assert message.out == ''
                checked.append(True)

        def evaluate(profile, candidate, folder, **kwargs):
            check_startup()
            if not resume:
                raise TaskCancelled('fixture pause after startup')
            return _fast_evaluate(profile, candidate, folder, score=100., **kwargs)

        with training_boundary():
            reference = engine.reference

            def checked_reference(*args, **kwargs):
                check_startup()
                return reference(*args, **kwargs)

            with patch.object(engine, 'reference', side_effect=checked_reference), \
                    patch.object(sequence, 'evaluate', side_effect=evaluate):
                assert command(tmp_path, options) == (0 if resume else 2)
        assert checked
        outcome = json.loads(capsys.readouterr().out)[0]
        assert outcome['status'] == ('completed' if resume else 'paused')
        # 下一新任务参数不可改写恢复摘要，恢复仍沿初次冻结请求量。
        config.write_text('[training]\ntop_k=12\nretest_batches=1\nretest_iterations=2\n', encoding='utf-8')


def test_training_list_defaults_to_burst_and_preserves_legacy_results(tmp_path, capsys):
    from seed_training import main, SELECTED_SCHEMA
    import result_store

    row = dict(configuration_key=None, candidate_id='legacy-only', condition='fixture', class_name='deathknight', spec='unholy',
               targets=1, program=[['death_coil']], family='fixture', score=1., scores=[1.],
               template_sha256='fixture', engines={})
    result_store.write('seed_selected', 'deathknight-unholy-1', [row], schema=SELECTED_SCHEMA)
    assert main(['--project', str(tmp_path), 'list', '--state', 'selected']) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert main(['--project', str(tmp_path), 'list', '--state', 'selected', '--legacy']) == 0
    assert json.loads(capsys.readouterr().out)[0]['candidate_id'] == 'legacy-only'


def test_cleaned_candidate_registration_is_reusable_and_rejects_missing_provenance(tmp_path, capsys):
    from seed_training import main
    import result_store

    source = tmp_path / 'cleaned.json'
    source.write_text(json.dumps(dict(label='ABC-C', spec='unholy', class_name='deathknight',
        source='plugin:Smolbreather', original='15 ordered spell ids',
        instructions='continuous unmodified key', semantic='rewritten',
        changes=['remove movement'], family='plugin-opener', core=[['putrefy'], ['death_coil']],
        program=[['outbreak'], ['putrefy'], ['death_coil']])), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    assert command(tmp_path, ['register', str(source)]) == 0
    assert command(tmp_path, ['list', '--state', 'pending']) == 0
    lines = capsys.readouterr().out.splitlines()
    candidates = json.loads(lines[-1])
    assert len(candidates) == 1
    assert candidates[0]['label'] == 'ABC-C'
    assert result_store.DATA_ROOT.joinpath('seed_candidates').is_dir()
    invalid = json.loads(source.read_text())
    invalid.pop('changes')
    source.write_text(json.dumps(invalid), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) != 0
    assert command(tmp_path, ['list', '--state', 'pending']) == 0
    assert len(json.loads(capsys.readouterr().out.splitlines()[-1])) == 1











def test_training_condition_excludes_only_execution_and_keeps_real_inputs():
    from copy import deepcopy
    from search import config_for
    from seed_training import RETEST_SEEDS, TRAINING_VERSION, semantic_condition, semantic_versions
    payload = dict(version=TRAINING_VERSION, template='original-role',
        engines={'baseline': 'original-engine'},
        config=config_for(dict(diagnostic_logging=True, no_improvement_rounds=2)),
        simulation=dict(target_count=1, enable_omnium_talents=True), retest=RETEST_SEEDS,
        effective_options=['threads=1'], rule_config_digest='original-rules',
        rules={'projects/sim2gse/seed_training.py': 'original-source'})
    versions = semantic_versions()
    expected = semantic_condition(payload, versions)
    execution = deepcopy(payload)
    execution['config']['max_processes'] = 16
    execution['config'].update(diagnostic_logging=False, diagnostics='full', search_observability='full')
    execution['rules']['projects/sim2gse/seed_training.py'] = 'logging-only-source-change'
    assert semantic_condition(execution, versions) == expected
    for field, value in [('template', 'new-role'), ('engines', {'baseline': 'new-engine'}),
                         ('retest', [20261011]), ('effective_options', ['threads=2']), ('rule_config_digest', 'new-rules')]:
        assert semantic_condition(dict(payload, **{field: value}), versions) != expected
    for key in ('random_seed', 'iterations', 'no_improvement_rounds', 'input_interval_ms'):
        changed = deepcopy(payload)
        changed['config'][key] += 1
        assert semantic_condition(changed, versions) != expected
    assert semantic_condition(payload, dict(versions, search='new-search')) != expected










def test_training_entry_rejects_an_active_foreground_search(tmp_path, monkeypatch):
    from seed_activity import foreground_search
    import seed_training

    calls = []
    template = tmp_path / 'standard.simc'
    template.write_text('unused by the training stub', encoding='utf-8')
    monkeypatch.setattr(seed_training, '_run_training',
                        lambda *args, **kwargs: calls.append((args, kwargs)))
    with foreground_search():
        result = seed_training.main(['--project', str(tmp_path), 'run', '--template', str(template),
                                     '--targets', '1', '--workspace', str(tmp_path / 'work')])

    assert result == 2
    assert calls == []




def test_missing_project_and_unreadable_center_are_not_silently_empty(tmp_path, monkeypatch):
    from seed_training import main
    import result_store
    import runpy
    with pytest.raises(SystemExit):
        main(['list'])
    real_loader = runpy.run_path
    def unreadable_loader(path):
        api = real_loader(path)
        def unreadable(*args, **kwargs):
            raise PermissionError('数据中心暂时不可读')
        api['read_key'] = unreadable
        return api
    monkeypatch.setattr(runpy, 'run_path', unreadable_loader)
    assert command(tmp_path, ['list']) == 2


def test_unconnected_public_search_does_not_create_data_root(tmp_path, monkeypatch):
    from test_character_export import sample_profile
    from task import run_task
    import result_store

    data_root = tmp_path / 'unconnected' / 'data'
    monkeypatch.setattr(result_store, 'DATA_ROOT', data_root)
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', None)
    monkeypatch.setattr(result_store, '_SKILL_API', None)
    monkeypatch.setattr(result_store, '_skill_root', lambda: tmp_path / 'missing-skill')
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile(), encoding='utf-8')

    with pytest.raises(RuntimeError, match='数据中心尚未接入本项目'):
        run_task(template, tmp_path / 'unconnected-task')

    assert not data_root.exists()




@pytest.mark.parametrize('illegal_program', [
    [['death_coil'] * 16],
    [dict(kind='CastSequence', members=['death_coil'] * 32)],
])
def test_prepare_rejects_oversize_macro_without_losing_legal_materials(
        tmp_path, capsys, memory_training_center, illegal_program):
    from test_character_export import sample_profile

    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    material = tmp_path / 'material.json'
    for label, program in [('oversize', illegal_program), ('legal', [['outbreak']])]:
        material.write_text(json.dumps(dict(label=label, class_name='deathknight', spec='unholy',
            source='fixture', original='fixture', instructions='repeat', semantic='preserved', changes=[],
            family='fixture', core=[], program=program)), encoding='utf-8')
        assert command(tmp_path, ['register', str(material)]) == 0
    capsys.readouterr()
    with training_boundary():
        assert command(tmp_path, ['prepare', '--template', str(template), '--targets', '1',
                                 '--workspace', str(tmp_path / 'work')]) == 0
    prepared = json.loads(capsys.readouterr().out)[0]
    assert prepared['preparation']['unique_inputs'] == 1
    assert prepared['preparation']['rejected'] == 1
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', prepared['config_key']]) == 0
    sources = {row['label']: row for row in json.loads(capsys.readouterr().out) if row['kind'] == 'source'}
    assert sources['oversize']['status'] == 'rejected'
    assert '255 字节' in sources['oversize']['reason']
    assert sources['legal']['status'] == 'ready'


@pytest.mark.parametrize('boundary', ['load_targeting', 'run_command'])
def test_prepare_keeps_tool_failure_explicit_instead_of_rejecting_material(
        tmp_path, capsys, memory_training_center, boundary):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import codec

    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    material = tmp_path / 'material.json'
    material.write_text(json.dumps(dict(label='legal', class_name='deathknight', spec='unholy',
        source='fixture', original='fixture', instructions='repeat', semantic='preserved', changes=[],
        family='fixture', core=[], program=[['outbreak']])), encoding='utf-8')
    assert command(tmp_path, ['register', str(material)]) == 0
    capsys.readouterr()
    with training_boundary(), patch.object(codec, boundary, side_effect=ValueError('受检编译工具或目标资料故障')):
        assert command(tmp_path, ['prepare', '--template', str(template), '--targets', '1',
                                 '--workspace', str(tmp_path / 'work')]) == 2
    output = capsys.readouterr()
    assert '受检编译工具或目标资料故障' in output.err
    assert json.loads(output.out)[0]['status'] == 'paused'


def test_prepare_reuses_context_and_only_rebuilds_changed_sources(tmp_path, capsys, memory_training_center):
    from test_character_export import sample_profile
    import result_store
    import sequence
    from unittest.mock import patch

    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    source = tmp_path / 'material.json'
    row = dict(label='first', class_name='deathknight', spec='unholy', source='fixture', source_id='fixture-1',
               original='fixture', instructions='repeat', semantic='preserved', changes=[], family='fixture',
               core=[['death_coil']], program=[['death_coil']])
    for source_id, program in [('fixture-1', [['death_coil']]), ('fixture-2', [['outbreak']])]:
        source.write_text(json.dumps(dict(row, source_id=source_id, program=program)), encoding='utf-8')
        assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    options = ['--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    with training_boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    first = json.loads(capsys.readouterr().out)[0]
    assert first['preparation']['sources_rebuilt'] == 2
    assert first['preparation']['context_rebuilt'] is True
    with training_boundary():
        assert command(tmp_path, ['prepare', *options, '--diagnostic-logging']) == 0
    logged = json.loads(capsys.readouterr().out)[0]
    assert logged['preparation']['sources_rebuilt'] == 0
    assert logged['config_key'] == first['config_key']
    row['label'] = 'metadata revision'
    source.write_text(json.dumps(row), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    with training_boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    metadata = json.loads(capsys.readouterr().out)[0]
    assert metadata['preparation']['sources_rebuilt'] == 0
    row['program'] = [['death_coil'], ['outbreak']]
    source.write_text(json.dumps(row), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    with training_boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    changed = json.loads(capsys.readouterr().out)[0]
    assert changed['preparation']['sources_rebuilt'] == 1
    assert changed['preparation']['context_rebuilt'] is False
    template.write_text(sample_profile() + '\n# new role revision\n', encoding='utf-8')
    with training_boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    changed_context = json.loads(capsys.readouterr().out)[0]
    assert changed_context['preparation']['context_rebuilt'] is True
    assert changed_context['preparation']['sources_rebuilt'] == 2

    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', changed_context['config_key']]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    snapshot[0]['version'] = 'unknown-cache-version'
    result_store.write('seed_prepared', changed_context['config_key'], snapshot, schema=__import__('seed_training').PREPARED_SCHEMA)
    with training_boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    rebuilt = json.loads(capsys.readouterr().out)[0]
    assert rebuilt['preparation']['context_rebuilt'] is True and rebuilt['preparation']['sources_rebuilt'] == 2
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', rebuilt['config_key']]) == 0
    before_failure = json.loads(capsys.readouterr().out)
    source.write_text(json.dumps(dict(row, program=[['outbreak'], ['scourge_strike']])), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    write = result_store.write
    def fail_snapshot(table, *args, **kwargs):
        if table == 'seed_prepared':
            raise OSError('快照保存故障')
        return write(table, *args, **kwargs)
    with training_boundary(), patch.object(result_store, 'write', side_effect=fail_snapshot), \
         patch.object(sequence, 'evaluate', side_effect=AssertionError('准备失败不得派发训练')):
        assert command(tmp_path, ['prepare', *options]) == 2
    assert '快照保存故障' in capsys.readouterr().err
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', rebuilt['config_key']]) == 0
    assert json.loads(capsys.readouterr().out) == before_failure








@pytest.mark.parametrize('changed', [True])
def test_training_prepare_freezes_burst_across_scenes_and_checks_current_definition(tmp_path, capsys, monkeypatch,
                                                                                 changed):
    import burst
    import engine
    import result_store
    from test_character_export import sample_profile

    result_store.bind_project(tmp_path)
    definition = json.loads(Path('projects/sim2gse/burst/unholy.json').read_text(encoding='utf-8'))
    definition['version'] += '-fixture'
    definition['blocks'] = [[dict(kind='spell', simc_action='death_coil', name='死亡缠绕', spell_id=1002)]]
    definition['excluded_spell_ids'] = [1002]
    burst.publish(definition)
    material = tmp_path / 'material.json'
    material.write_text(json.dumps(dict(label='ordinary-loop', class_name='deathknight', spec='unholy',
        source='fixture', original='fixture', instructions='repeat', semantic='preserved', changes=[],
        family='plain', core=[], program=[['outbreak']])), encoding='utf-8')
    assert command(tmp_path, ['register', str(material)]) == 0
    capsys.readouterr()
    api = result_store._api()
    query = api['query']
    discovery_queries = references = 0

    def one_discovery(root, sql, parameters=None, **options):
        nonlocal discovery_queries
        if options.get('tables') == ['burst_definitions']:
            discovery_queries += 1
        return query(root, sql, parameters, **options)

    monkeypatch.setattr(result_store, '_api', lambda: api)
    monkeypatch.setitem(api, 'query', one_discovery)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    with training_boundary(), monkeypatch.context() as scoped:
        reference = engine.reference

        def fixed_native(*args, **options):
            nonlocal references
            references += 1
            native = reference(*args, **options)
            native['identity']['data_version'] = definition['data_version']
            if references == 1:
                replacement = dict(definition, version=definition['version'] + '-changed', instructions='changed')
                burst.publish(replacement)
            return native

        scoped.setattr(engine, 'reference', fixed_native)
        status = command(tmp_path, ['prepare', '--template', str(template), '--targets', '1', '5',
            '--use-burst', '--max-trainings', '1', '--workspace', str(tmp_path / 'work')])
    assert status == 2
    assert '爆发定义已变化' in capsys.readouterr().err
    assert references == 1
    assert not (tmp_path / 'work/5').exists()
    assert discovery_queries == 2  # 每模板check的两条发现SQL；各组只按冻结键读取。


@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'unreadable'])
def test_training_prepare_keeps_history_missing_and_read_failure_semantics(tmp_path, capsys, monkeypatch, failure):
    import result_store
    from test_character_export import sample_profile

    source = tmp_path / 'material.json'
    source.write_text(json.dumps(dict(label='registered', class_name='deathknight', spec='unholy', source='fixture',
        original='fixture', instructions='repeat', semantic='preserved', changes=[], family='plain', core=[],
        program=[['outbreak']])), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    before = json.loads(capsys.readouterr().out)
    assert command(tmp_path, ['list']) == 0
    registry_before = json.loads(capsys.readouterr().out)
    for run_id in ('valid', 'affected'):
        result_store.write('runs', run_id, [dict(dict.fromkeys(result_store.RUN_SCHEMA),
            run_id=run_id, status='completed', profile={'identity': {'class': 'deathknight', 'spec': 'unholy'}},
            candidate_key='winner', candidate_data_key=run_id + '_candidate', search_dps=0.)],
            schema=result_store.RUN_SCHEMA)
        row = dict(dict.fromkeys(result_store.CANDIDATE_SCHEMA), run_id=run_id, candidate_key='winner',
                   candidate_data_key=run_id + '_candidate', program=[['death_coil']])
        if run_id == 'affected' and failure == 'missing':
            continue
        records = [row]
        result_store.write('candidates', run_id + '_candidate', records, schema=result_store.CANDIDATE_SCHEMA)
    if failure == 'corrupt':
        (result_store.DATA_ROOT / 'candidates/affected_candidate.parquet').write_bytes(b'broken known candidate')
    api = result_store._api()
    read_keys, read_key = api['read_keys'], api['read_key']
    fallback_keys = []

    def candidate_groups(root, table, keys, **options):
        if table == 'candidates' and failure == 'unreadable':
            raise PermissionError('临时历史读取失败')
        return read_keys(root, table, keys, **options)

    def known_single(root, table, key, **options):
        if table == 'candidates':
            fallback_keys.append(key)
        return read_key(root, table, key, **options)

    monkeypatch.setattr(result_store, '_api', lambda: api)
    monkeypatch.setitem(api, 'read_keys', candidate_groups)
    monkeypatch.setitem(api, 'read_key', known_single)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    with training_boundary():
        status = command(tmp_path, ['prepare', '--template', str(template), '--targets', '1',
                                  '--workspace', str(tmp_path / 'work')])
    if failure in ('corrupt', 'unreadable'):
        assert status == 2
        assert ('损坏' if failure == 'corrupt' else '临时历史读取失败') in capsys.readouterr().err
        assert not (tmp_path / 'work').exists()
        assert command(tmp_path, ['list']) == 0
        assert json.loads(capsys.readouterr().out) == registry_before
        assert fallback_keys == []
    else:
        assert status == 0
        capsys.readouterr()
        assert command(tmp_path, ['list', '--state', 'unsupported']) == 0
        inactive = json.loads(capsys.readouterr().out)
        assert len(inactive) == 1 and inactive[0]['source_id'] == 'history:affected'
        assert '候选记录缺失' in inactive[0]['unavailable_reason']
        assert command(tmp_path, ['list']) == 0
        active = json.loads(capsys.readouterr().out)
        assert {row['source_id'] for row in active} == {before['candidate_id'], 'history:valid'}
        assert set(fallback_keys) == {'valid_candidate', 'affected_candidate'}


def test_training_prepare_keeps_formal_burst_through_public_cli(tmp_path, monkeypatch, capsys):
    import burst
    from test_burst import reviewed_fixture,character_seed_boundary
    definition,raw=reviewed_fixture()
    published=burst.publish(definition)
    material=tmp_path/'material.json'
    material.write_text(json.dumps(dict(label='ordinary',class_name='deathknight',spec='unholy',source='fixture',
        original='fixture',instructions='repeat',semantic='preserved',changes=[],family='plain',core=[],
        program=[['scourge_strike']])),encoding='utf-8')
    assert command(tmp_path,['register',str(material)])==0
    capsys.readouterr()
    template=tmp_path/'standard.simc';template.write_text(raw,encoding='utf-8')
    with character_seed_boundary() as engines:
        assert command(tmp_path,['prepare','--template',str(template),'--targets','1',
            '--workspace',str(tmp_path/'work'),'--use-burst'])==0
    prepared=json.loads(capsys.readouterr().out)[0]
    assert command(tmp_path,['list','--state','prepared','--config-key',prepared['config_key'],'--use-burst'])==0
    rows=json.loads(capsys.readouterr().out)
    context=next(row['context'] for row in rows if row['kind']=='context')
    context=json.loads(context) if isinstance(context,str) else context
    assert context['burst']['plan']==published['plan']
    assert 'rule_initialization' not in context
    assert context['preparation_input']['simulation']['scene']=='single_target'
    assert 'rule_snapshot' not in context
    assert burst.load(252)==published
    from test_training_champion import completed_training
    from seed_training import training_champion
    import engine
    with character_seed_boundary():
        champion_template,completed=completed_training(tmp_path,1,[([['scourge_strike']],[110.,120.,130.])],
            prepared_context=context)
        monkeypatch.setattr(engine,'_training_template',lambda manifest:champion_template)
        champion=training_champion('deathknight','unholy',context['preparation_input']['simulation'],
            engines=engines,input_interval_ms=200,use_burst=True,
            burst_identity=dict(spec_id=252,definition_id=published['definition_id']),
            configuration_key=context['configuration_key'])
    assert champion['status']=='selected',champion
    assert champion['candidate_id']==completed[0]['candidate_id']
    assert champion['condition_input']['burst']['plan']==published['plan']
