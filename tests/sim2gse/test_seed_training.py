"""Manual training command uses the existing installed data center."""
import json
from pathlib import Path
import subprocess
import shutil
import sys
import sqlite3
from contextlib import contextmanager


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


@contextmanager
def guided_training_boundary(directory, damage_for, *, known_inputs=None, insert_only=False,
                             move_to_front=False, all_actions=False):
    """迁移旧算子替身：真实配置、诊断/全池/Coba，仅构造原外部评分事实。"""
    import os
    from unittest.mock import patch
    import sequence
    from test_rule_diagnostics import _condition_pack, _observed_evaluate

    pack = _condition_pack()
    actions = {'first': 'outbreak', 'consumer': 'death_coil', 'filler': 'scourge_strike'}
    if all_actions:
        import copy
        objects = pack['object_sets']['sample']
        objects['filler'] = dict(kind='action', native_action='scourge_strike',
            base_button='scourge_strike', native_forms=['scourge_strike'])
        priority = pack['configurations'][0]['states']['only']['priority']
        binding = priority[0]
        priority[:] = [dict(copy.deepcopy(binding), name=f'available {name}',
            arguments=dict(binding['arguments'], action=name)) for name in actions]
    if insert_only:
        template = pack['general']['templates']['renamed-template']
        template['edits'] = [edit for edit in template['edits'] if edit['operation'] == 'insert']
    if move_to_front:
        template = pack['general']['templates']['renamed-template']
        move, = [edit for edit in template['edits'] if edit['operation'] == 'move']
        move['destination'] = dict(op='filter', args=[move['destination'],
            dict(op='eq', args=[{'var': 'gap.source_position'}, [0]])], **{'as': 'gap'})
        template['edits'] = [move]
    path = directory / 'guided-rules.json'
    path.write_text(json.dumps(pack), encoding='utf-8')

    def observed(*args, **kwargs):
        program = [[action['simc_action'] for action in block] for block in args[1]['blocks']]
        kwargs.pop('input_sources', None)
        kwargs.pop('burst_candidate', None)
        kwargs['score'] = damage_for(args[1])
        result = _observed_evaluate(*args, **kwargs)
        payload = result['report']['sim']['players'][0]['sim2gse_rule_observations']
        if all_actions:
            payload['action_observations'] = [dict(row, object=name, actual_form=action,
                base_button=action) for row in payload['action_observations']
                for name, action in actions.items()]
        for name in ('inputs', 'action_observations', 'state_observations'):
            for row in payload[name]:
                row['source_step'] = row['input_index'] % len(program)
        count = known_inputs(program) if known_inputs else 1
        for row in payload['state_observations']:
            row['value'] = int(row['input_index'] < count)
        return result

    with patch.dict(os.environ, SIM2GSE_RULE_CONFIG=str(path)), training_boundary(), \
            patch.object(sequence, 'evaluate', side_effect=observed):
        yield


def training_round_boundary(directory, damage_for=lambda candidate: 100.):
    """提供各源位置的三动作机会，轮次、并发及停止仍由真实训练入口执行。"""
    return guided_training_boundary(directory, damage_for, known_inputs=len, all_actions=True)

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
        def write(root, table, key, rows, *, schema=None):
            table = installed_data_store_api['_name'](table, table=True)
            key = installed_data_store_api['_name'](key)
            payload = json.dumps(rows, ensure_ascii=False, allow_nan=False)
            group = f'"_memory_{table}_{key}"'
            with lock, database.cursor() as cursor:
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
                   **{name: installed_data_store_api[name] for name in ('MissingKeyError', 'CorruptDataError')})
        scoped.setattr(result_store, '_api', lambda: api)
        yield


@pytest.fixture
def memory_training_center(training_center, memory_result_center):
    yield


@pytest.fixture
def single_candidate_training_rounds(monkeypatch):
    """每轮只选一个真实子候选；两轮停止与初/终三种子复测保持原义。"""
    import seed_training
    config_for = seed_training.config_for
    assert config_for(training=True)['round_candidate_limit'] == 16
    assert config_for({'max_processes': 16}, training=True)['max_processes'] == 16

    def small_rounds(values=None, *, training=False):
        return config_for(dict(values or {}, round_candidate_limit=1), training=training)

    with monkeypatch.context() as scoped:
        scoped.setattr(seed_training, 'config_for', small_rounds)
        yield
    assert config_for(training=True)['round_candidate_limit'] == 16
    assert config_for({'max_processes': 16}, training=True)['max_processes'] == 16


def command(tmp_path, args):
    from seed_training import main
    # These existing cases exercise the explicitly retained legacy training mode.
    if args[0] in ('run', 'prepare', 'list') and '--use-burst' not in args:
        args = [*args, '--legacy']
    return main(['--project', str(tmp_path), *args])


def test_training_check_locates_current_template_without_starting_compute(tmp_path, capsys, monkeypatch):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('只读训练检查不能启动计算进程')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
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
    assert main(['--project', str(tmp_path), entry,
                 *(['--workspace', str(tmp_path / 'work')] if entry == 'run' else [])]) == 2
    assert '已审核' in capsys.readouterr().err


def test_training_list_defaults_to_burst_and_preserves_legacy_results(tmp_path, capsys):
    from seed_training import main, SELECTED_SCHEMA
    import result_store

    row = dict(candidate_id='legacy-only', condition='fixture', class_name='deathknight', spec='unholy',
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


def test_training_command_diagnoses_only_parents_and_reuses_on_demand_reports(
        tmp_path, capsys, monkeypatch):
    from unittest.mock import patch
    from test_character_export import sample_profile
    from test_rule_diagnostics import _condition_pack, _observed_evaluate
    from test_search import _fast_evaluate
    from test_rule_initialization import _configure_opener
    import result_store
    import sequence
    import selector
    from search import TaskStore

    _configure_opener(tmp_path, monkeypatch, _condition_pack())
    starts = [[['outbreak'], ['death_coil']], [['death_coil'], ['outbreak']]]
    for index, program in enumerate(starts):
        source = tmp_path / f'source-{index}.json'
        source.write_text(json.dumps(dict(label=str(index), source_id=str(index),
            class_name='deathknight', spec='unholy', source='constructed-boundary',
            original='preserved input', instructions='repeat', semantic='preserved',
            changes=[], family=str(index), core=program[:1], program=program)), encoding='utf-8')
        assert command(tmp_path, ['register', str(source)]) == 0
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    args = ['run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work')]
    requests = []

    def observed(*args, **kwargs):
        if kwargs.get('rule_observation_request') is not None:
            requests.append(kwargs['rule_observation_request'])
        kwargs.pop('input_sources', None)
        kwargs.pop('burst_candidate', None)
        kwargs['score'] = 100.0  # Equal real boundary scores keep this finite; no learner stub.
        return (_observed_evaluate if kwargs.get('rule_observation_request') is not None
                else _fast_evaluate)(*args, **kwargs)

    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=observed):
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    processed = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len(processed) == 2 and all(row['status'] == 'completed' for row in processed)
    assert sorted(json.loads(row['initial_program']) for row in processed) == sorted(starts)
    batches = list(result_store.iter_rows(
        "SELECT batch_key,candidate_key,source_scoring_batch_key FROM batches WHERE purpose='diagnostic'",
        tables=['batches']))
    assert len(batches) == len(requests) >= len(starts)
    scores = list(result_store.iter_rows(
        "SELECT batch_key,rule_observations FROM batches WHERE purpose='search' AND batch_index=0",
        tables=['batches']))
    assert len(scores) > len(batches)
    assert all(row['rule_observations'] is None for row in scores)
    diagnostics = []
    for batch in batches:
        saved = result_store.one('batches', 'batch_key', batch['batch_key'])
        diagnostic = json.loads(saved['rule_diagnostics'])
        assert 'costs' not in diagnostic
        assert diagnostic['evidence']['batch_key'] == batch['batch_key']
        assert diagnostic['evidence']['kind'] == 'on_demand_replay'
        assert diagnostic['evidence']['source_scoring_batch_key'] == batch['source_scoring_batch_key']
        original = result_store.one('batches', 'batch_key', batch['source_scoring_batch_key'])
        assert original['purpose'] == 'search'
        assert all(saved[name] == original[name] for name in ('dps', 'samples', 'variance'))
        assert diagnostic['parent']['behavior_identity'] == batch['candidate_key']
        assert [row['name'] for row in diagnostic['rules']] == [
            'supported opportunity', 'inactive condition']
        assert diagnostic['pool']['complete'] is True
        assert len(diagnostic['selection_context']['values']) == 50
        diagnostics.append(diagnostic)
    assert len({row['parent_identity'] for row in diagnostics}) == len(batches)
    learned = []
    for material in processed:
        store = TaskStore(Path(material['task_path']))
        try:
            assert store.state['starts'] == [json.loads(material['initial_program'])]
            assert store.state['config']['diagnostic_logging'] is False
            assert store.state['config']['rule_diagnostics_policy'] == 'on_demand'
            assert any(row.get('rule_diagnostic_status') == 'not_diagnosed'
                       for row in store.state['archive'])
            choices = [row['selection'] for row in store.state['rule_steps'].values()]
            assert choices
            assert all(row['feedback']['status'] == 'learned' and row['feedback']['reward'] == 0
                       for row in choices)
            learned.extend(choices)
        finally:
            store.close()
    model = result_store.read_search_learner(selector.MODEL_KEY)
    assert model['reservations'] == []
    assert sum(model['settled'].values()) == len(learned)
    assert len(model['settled']) == len(starts)
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, args) == 0
    assert [json.loads(result_store.one('batches', 'batch_key', row['batch_key'])['rule_diagnostics'])
            for row in batches] == diagnostics
    assert result_store.read_search_learner(selector.MODEL_KEY) == model



def training_batch_fixture(tmp_path, *, mutate_input=lambda payload: None, burst_context=None, legacy=True):
    """构造完整条件/检查点/成绩证据；旧版本不伪造新的配置摘要。"""
    import hashlib
    import result_store
    from engine import identity
    from search import TaskStore, config_for, digest
    from seed_training import (training_condition_input, LEGACY_EXECUTION_RULES,
                               LEGACY_SOURCE_COMMIT, LEGACY_SEMANTIC_VERSIONS, PROCESSED_SCHEMA)
    from test_character_export import sample_profile
    from test_search import _fast_capabilities
    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='legacy', class_name='deathknight', spec='unholy',
        source='constructed-legacy', original='three actions', instructions='repeat', semantic='preserved',
        changes=[], family='plain', core=[], program=[['outbreak'], ['death_coil'], ['scourge_strike']])),
        encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    candidate = result_store.read_records('seed_candidates', 'registry')[0]
    candidate['program'] = json.loads(candidate['program'])
    template = tmp_path / 'standard.simc'
    text = sample_profile()
    template.write_text(text, encoding='utf-8')
    config = config_for(dict(diagnostic_logging=True, diagnostics='summary', no_improvement_rounds=2,
                             **({'input_interval_ms': 200} if burst_context else {})))
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    payload = training_condition_input(hashlib.sha256(text.encode()).hexdigest(), engines, config,
                                       dict(target_count=1, enable_omnium_talents=True), burst_context=burst_context)
    if legacy:
        payload.pop('rule_config_digest')  # 旧提交从未读取两库配置，不制造兼容证据。
        payload['rules'].update({key: values[0] for key, values in LEGACY_EXECUTION_RULES.items()})
    payload = json.loads(json.dumps(payload))
    mutate_input(payload)
    from seed_training import semantic_condition, semantic_versions
    condition = digest(payload) if legacy else semantic_condition(payload, semantic_versions())
    batch = tmp_path / 'work' / '1' / condition[:12]
    folder = batch / candidate['candidate_id'][:12]
    folder.mkdir(parents=True)
    (batch / 'standard.simc').write_text(text, encoding='utf-8')
    (batch / 'condition.txt').write_text(condition, encoding='ascii')
    if not legacy:
        manifest = dict(format=1, condition=condition, condition_input=payload, input_sha256=digest(payload),
            semantic_versions=semantic_versions(), semantic_condition=condition, executions=[])
        (batch / 'identity.json').write_text(json.dumps(manifest), encoding='utf-8')
    store = TaskStore(folder)
    store.state.update(training_condition=condition, training_candidate_id=candidate['candidate_id'],
                       config=payload['config'], capabilities=_fast_capabilities(), phase='done',
                       rounds=2, elapsed_seconds=7., native_batch_starts=10,
                       batch_requests=11, batch_cache_hits=1,
                       **({'burst': burst_context} if burst_context else {}))
    store.save()
    store.close()
    row = dict(candidate_id=candidate['candidate_id'], condition=condition, status='completed', error='',
        initial_program=candidate['program'], program=candidate['program'], family='plain', core_retained=True,
        rounds=2, stop_reason='no_improvement', elapsed_seconds=7., scores=[100.] * 3,
        initial_scores=[100.] * 3, comparison={}, task_path=str(folder), native_batch_starts=10,
        batch_requests=11, cache_hits=1)
    result_store.write('seed_processed', 'deathknight-unholy-1' + ('-burst' if burst_context else ''),
                       [row], schema=PROCESSED_SCHEMA)
    evidence = dict(condition_input=payload, semantic_versions=(LEGACY_SEMANTIC_VERSIONS if legacy else semantic_versions()),
                    **({'source_commit': LEGACY_SOURCE_COMMIT} if legacy else {}))
    return template, batch, evidence


@pytest.fixture
def legacy_engine_boundary(monkeypatch):
    with training_boundary(), monkeypatch.context() as scoped:
        yield scoped


def test_training_entry_keeps_real_legacy_history_without_claiming_current_rule_identity(
        tmp_path, monkeypatch, capsys, legacy_engine_boundary):
    import result_store
    import sequence
    from seed_training import adopt_legacy_condition
    template, batch, evidence = training_batch_fixture(tmp_path)
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    checkpoint = Path(processed[0]['task_path']) / 'task.sqlite3'
    before = checkpoint.read_bytes()
    assert 'rule_config_digest' not in evidence['condition_input']
    legacy_engine_boundary.setattr(sequence, 'evaluate', lambda *a, **kw: pytest.fail('身份不兼容不能自动重训'))
    # 新合同：旧源码凭据真实，也不能证明它使用过当前可编辑规则。
    evidence['condition_input']['config']['batch_targets'] = tuple(evidence['condition_input']['config']['batch_targets'])
    with pytest.raises(ValueError, match='语义身份'):
        adopt_legacy_condition(batch, evidence, processed=processed, selected=[])
    assert command(tmp_path, ['run', '--template', str(template), '--targets', '1',
        '--workspace', str(tmp_path / 'work'), '--max-processes', '4']) == 2
    assert '缺少完整身份凭据' in capsys.readouterr().err
    assert not (batch / 'identity.json').exists()
    assert checkpoint.read_bytes() == before
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == processed


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


@pytest.mark.parametrize('grouped', [True])
def test_upgrade_postcheck_checks_current_rule_identity_and_retest_keys(tmp_path, legacy_engine_boundary,
                                                                            grouped):
    import result_store
    import runpy
    from search import digest
    from program import canonicalize_search_program
    from seed_training import RETEST_SEEDS, PROCESSED_SCHEMA
    from test_search import _fast_capabilities
    _, batch, evidence = training_batch_fixture(tmp_path, burst_context={'definition_id': 'test-definition'}, legacy=False)
    scope = 'deathknight-unholy-1-burst'
    rows = result_store.read_records('seed_processed', scope)
    row = rows[0]
    # 当前配置身份另立；保留原六次复测和组键核验，不借用旧commit名义。
    rows.append(dict(row, candidate_id='rejected-a', status='rejected', error='explicit rejection'))
    for item in rows:
        for field in ('initial_program', 'program', 'comparison'):
            item[field] = json.loads(item[field])
    result_store.write('seed_processed', scope, rows, schema=PROCESSED_SCHEMA)
    scripts = Path(__file__).resolve().parents[2] / '.agents/skills/sim2gse-upgrade/scripts'
    sys.path.insert(0, str(scripts))
    try:
        postcheck = runpy.run_path(str(scripts / 'postcheck.py'))
    finally:
        sys.path.remove(str(scripts))
    payload = evidence['condition_input']
    ready = dict(template_sha256=payload['template'], engines=payload['engines'],
                 burst_definition_id='test-definition')
    scene = dict(targets=1, run_id='page-fixture', training_condition=row['condition'],
                 processed=[row['candidate_id'], 'rejected-a'])
    result_store.write('runs', 'page-fixture', [dict(dict.fromkeys(result_store.RUN_SCHEMA),
        run_id='page-fixture', engines=payload['engines'])], schema=result_store.RUN_SCHEMA)
    schema = dict(batch_key='VARCHAR', purpose='VARCHAR', seed='UBIGINT', samples='UBIGINT', dps='DOUBLE',
                  engines='JSON', condition_key='VARCHAR', requested_iterations='UBIGINT', program_identity='JSON')
    groups = {}
    keys = []
    with sqlite3.connect(Path(row['task_path']) / 'task.sqlite3') as database:
        for name in ('retest-initial', 'retest-final'):
            for seed in RETEST_SEEDS:
                key = digest(dict(folder=str(Path(row['task_path']) / name), seed=seed))
                group = name.replace('-', '_') if grouped else key
                keys.append((key, group))
                groups.setdefault(group, []).append(dict(batch_key=key, purpose='seed_retest', seed=seed,
                    samples=127, dps=100., engines=payload['engines'], condition_key=row['condition'],
                    requested_iterations=128,
                    program_identity=canonicalize_search_program(row['program'], _fast_capabilities())['form']))
                if grouped:
                    database.execute('INSERT OR REPLACE INTO batches VALUES (?,?)',
                        (key, json.dumps(dict(status='success', storage_group_key=group))))
    for group, records in groups.items():
        result_store.write('batches', group, records, schema=schema)
    if grouped:
        # The business key really is absent; only the stored group can locate these rows.
        assert result_store.read_records('batches', keys[0][0]) == []
    # This existing scenario intentionally has one successful material, after all six real retests.
    with pytest.raises(ValueError, match='缺少两类成功材料'):
        postcheck['check_scene'](scene, ready)
    key, group = keys[0]
    groups[group][0]['condition_key'] = 'foreign-condition'
    result_store.write('batches', group, groups[group], schema=schema)
    with pytest.raises(ValueError, match='独立复测引擎、条件或程序身份不一致'):
        postcheck['check_scene'](scene, ready)


@pytest.mark.parametrize(('arguments', 'parse_failure'), [(['--max-processes', '0'], True), (['--max-trainings', '3', '--max-processes', '6'], False)])
def test_training_command_rejects_invalid_parallelism_before_compute(tmp_path, monkeypatch, arguments, parse_failure):
    from seed_training import main
    def forbidden_process(*args, **kwargs):
        raise AssertionError('非法并发参数不能启动计算进程')
    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    if parse_failure:
        with pytest.raises(SystemExit) as stopped:
            main(['--project', str(tmp_path), 'run', *arguments])
        assert stopped.value.code == 2
    else:
        assert main(['--project', str(tmp_path), 'run', *arguments]) == 2


@pytest.mark.parametrize('max_processes', [2])
def test_training_budget_stop_keeps_progress_and_previous_selected_snapshot(
        tmp_path, max_processes, memory_training_center, single_candidate_training_rounds):
    from test_character_export import sample_profile
    from unittest.mock import patch
    from runtime import BudgetExceeded
    import result_store
    import sequence
    from seed_training import SELECTED_SCHEMA

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='budget', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three actions', instructions='repeat',
        semantic='preserved', changes=[], family='plain', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work'),
            '--max-processes', str(max_processes)]
    old = dict(candidate_id='old', condition='previous', class_name='deathknight', spec='unholy',
               targets=1, program=[['death_coil']], family='old', score=100., scores=[100.] * 3,
               template_sha256='previous', engines={})
    result_store.write('seed_selected', 'deathknight-unholy-1', [old], schema=SELECTED_SCHEMA)
    previous = result_store.read_records('seed_selected', 'deathknight-unholy-1')
    assert previous
    template.write_text(sample_profile() + '\n# changed template\n', encoding='utf-8')
    def budget_on_first_round(*args, **kwargs):
        program = [[action['simc_action'] for action in block] for block in args[1]['blocks']]
        if program != [['outbreak'], ['death_coil'], ['scourge_strike']]:
            raise BudgetExceeded('训练预算耗尽')
        return native(*args, **kwargs)

    with training_round_boundary(tmp_path):
        native = sequence.evaluate
        with patch.object(sequence, 'evaluate', side_effect=budget_on_first_round):
            assert command(tmp_path, args) == 2
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == previous
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    failed = next(row for row in processed if row['status'] == 'failed')
    assert failed['stop_reason'] == 'search_deadline'
    assert '未收敛' in failed['error']
    assert Path(failed['task_path'], 'task.sqlite3').exists()


@pytest.mark.parametrize('historic_dps', [90.0])
def test_history_candidate_is_retested_and_changed_template_is_not_reused(
        tmp_path, capsys, historic_dps, memory_training_center):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import sequence
    import result_store
    import search
    from seed_training import CANDIDATE_SCHEMA as SOURCE_SCHEMA, decode

    assert search.config_for(training=True)['round_candidate_limit'] == 16
    # Existing public center schemas, not a substitute history reader.
    result_store.write('runs', 'historic-1', [dict(dict.fromkeys(result_store.RUN_SCHEMA),
        run_id='historic-1', status='completed',
        profile={'identity': {'class': 'deathknight', 'spec': 'unholy'}},
        candidate_data_key='historic-candidate', search_dps=historic_dps, search_samples=1)], schema=result_store.RUN_SCHEMA)
    shared = {'adapter': 'search', 'metadata': {}, 'nodes': [
        {'kind': 'Action', 'commands': [{'kind': 'spell', 'simc_action': name}]}
        for name in ('outbreak', 'death_coil', 'scourge_strike')]}
    result_store.write('candidates', 'historic-candidate', [dict(dict.fromkeys(result_store.CANDIDATE_SCHEMA),
        run_id='historic-1',
        candidate_key='historic-key', candidate_data_key='historic-candidate', source='search',
        program=shared)], schema=result_store.CANDIDATE_SCHEMA)
    history_before = result_store.read_records('runs', 'historic-1')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    with training_round_boundary(tmp_path), patch.dict(search.DEFAULT_CONFIG, round_candidate_limit=2):
        assert command(tmp_path, ['prepare', *args[1:]]) == 0
    # Reproduce the inactive derived source left by the previous score-quality gate.
    source = result_store.read_records('seed_candidates', 'registry')[0]
    source.update(active=False, semantic='unsupported', program=[], core=decode(source['core']),
                  changes=['历史缺少可靠最佳候选或有效成绩'], unavailable_reason='历史缺少可靠最佳候选或有效成绩')
    result_store.write('seed_candidates', 'registry', [source], schema=SOURCE_SCHEMA)
    real_write = result_store.write
    def failing_publish(table, key, rows, **kwargs):
        if table == 'seed_selected':
            raise PermissionError('发布目标暂时不可写')
        return real_write(table, key, rows, **kwargs)
    with training_round_boundary(tmp_path), patch.dict(search.DEFAULT_CONFIG, round_candidate_limit=2), \
            patch.object(result_store, 'write', side_effect=failing_publish):
        assert command(tmp_path, args) == 2
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1')
    source = next(row for row in result_store.read_records('seed_candidates', 'registry')
                  if row['source_id'] == 'history:historic-1')
    assert source['active'] and source['semantic'] == 'preserved'
    assert source['unavailable_reason'] == '' and source['changes'] == []
    assert json.loads(source['program']) == [['outbreak'], ['death_coil'], ['scourge_strike']]
    args += ['--candidate-id', source['candidate_id']]
    assert result_store.read_records('runs', 'historic-1') == history_before
    assert search.config_for(training=True)['round_candidate_limit'] == 16
    if historic_dps != 90.:
        return
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    processed = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len(processed) == 1
    first = processed[0]
    assert json.loads(first['initial_program']) == [['outbreak'], ['death_coil'], ['scourge_strike']]
    assert first['status'] == 'completed' and first['rounds'] == 2
    assert first['stop_reason'] == 'no_improvement'
    assert len(first['initial_scores']) == len(first['scores']) == 3
    assert all(score > 90. for score in [*first['initial_scores'], *first['scores']])
    retests = list(result_store.iter_rows("SELECT * FROM batches WHERE purpose='seed_retest'", tables=['batches']))
    assert len(retests) == 6 and all(row['iterations'] == 128 for row in retests)
    assert {row['seed'] for row in retests} == {20261008, 20261009, 20261010}
    before = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    with training_round_boundary(tmp_path), patch.dict(search.DEFAULT_CONFIG, round_candidate_limit=2), \
            patch.object(sequence, 'evaluate', side_effect=AssertionError('可靠完整路径不能重训')):
        assert command(tmp_path, args) == 0
        assert command(tmp_path, ['list', '--state', 'selected', '--targets', '1']) == 0
        assert json.loads(capsys.readouterr().out.splitlines()[-1])
        assert command(tmp_path, args) == 0
    assert result_store.read_records('seed_processed', 'deathknight-unholy-1') == before
    template.write_text(sample_profile() + '\n# new template revision\n', encoding='utf-8')
    with training_round_boundary(tmp_path), patch.dict(search.DEFAULT_CONFIG, round_candidate_limit=2), \
            patch.object(sequence, 'evaluate', side_effect=ValueError('新条件重新计算')):
        assert command(tmp_path, args) == 2
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    rows = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len({row['condition'] for row in rows}) == 2
    assert any(row['status'] == 'failed' for row in rows)
    assert search.config_for(training=True)['round_candidate_limit'] == 16


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


@pytest.mark.parametrize('interruption', ['foreground'])
def test_foreground_search_does_not_wait_for_training_and_stops_it(
        tmp_path, capsys, interruption, memory_training_center, single_candidate_training_rounds):
    import os
    import time
    import threading
    import sequence
    import seed_activity
    import result_store
    from test_character_export import sample_profile
    from unittest.mock import patch
    from seed_training import SELECTED_SCHEMA
    old = dict(candidate_id='old', condition='previous', class_name='deathknight', spec='unholy',
               targets=1, program=[['death_coil']], family='old', score=100., scores=[100.] * 3,
               template_sha256='previous', engines={})
    result_store.write('seed_selected', 'deathknight-unholy-1', [old], schema=SELECTED_SCHEMA)
    previous = result_store.read_records('seed_selected', 'deathknight-unholy-1')
    programs = [[['outbreak'], ['death_coil'], ['scourge_strike']],
                [['death_coil'], ['scourge_strike'], ['outbreak']],
                [['scourge_strike'], ['outbreak'], ['death_coil']]]
    ids = []
    for index, program in enumerate(programs):
        source = tmp_path / f'source-{index}.json'
        source.write_text(json.dumps(dict(label=str(index), source_id=str(index), class_name='deathknight',
            spec='unholy', source='fixture', original='fixture', instructions='repeat', semantic='preserved',
            changes=[], family='plain', core=[], program=program)), encoding='utf-8')
        assert command(tmp_path, ['register', str(source)]) == 0
        ids.append(result_store.read_records('seed_candidates', 'registry')[-1]['candidate_id'][:12])
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    if interruption == 'inactive_failed':
        from runtime import BudgetExceeded
        registry = result_store.read_records('seed_candidates', 'registry')
        failed_id = next(row['candidate_id'] for row in registry if row['source_id'] == '0')
        current_id = next(row['candidate_id'] for row in registry if row['source_id'] == '1')
        def stop_search(*args, **kwargs):
            program = [[action['simc_action'] for action in block] for block in args[1]['blocks']]
            if program != programs[0]:
                raise BudgetExceeded('原A路径未收敛')
            return native(*args, **kwargs)
        with training_round_boundary(tmp_path):
            native = sequence.evaluate
            with patch.object(sequence, 'evaluate', side_effect=stop_search):
                assert command(tmp_path, args + ['--candidate-id', failed_id]) == 2
        failed = next(row for row in result_store.read_records('seed_processed', 'deathknight-unholy-1')
                      if row['candidate_id'] == failed_id)
        assert failed['status'] == 'failed'
        assert failed['stop_reason'] == 'search_deadline'
        path = tmp_path / 'source-0.json'
        path.write_text(json.dumps(dict(json.loads(path.read_text()), active=False)), encoding='utf-8')
        assert command(tmp_path, ['register', str(path)]) == 0
        publish_attempts = []
        real_write = result_store.write
        def fail_publish(table, key, rows, **kwargs):
            if table == 'seed_selected':
                publish_attempts.append(True)
                raise PermissionError('仅最终发布暂时不可写')
            return real_write(table, key, rows, **kwargs)
        with training_round_boundary(tmp_path), patch.object(result_store, 'write', side_effect=fail_publish):
            assert command(tmp_path, args + ['--candidate-id', current_id]) == 2
        records = result_store.read_records('seed_processed', 'deathknight-unholy-1')
        assert next(row for row in records if row['candidate_id'] == current_id)['status'] == 'completed'
        assert publish_attempts == [True], '停用的旧A失败不应阻挡B完整成果发布'
        assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == previous
        capsys.readouterr()
        with training_round_boundary(tmp_path), patch.object(sequence, 'evaluate', side_effect=AssertionError('B完整成果只重试发布')):
            assert command(tmp_path, args + ['--candidate-id', current_id]) == 0
        assert json.loads(capsys.readouterr().out)[0]['status'] == 'restored'
        assert result_store.read_records('seed_selected', 'deathknight-unholy-1')
        records = result_store.read_records('seed_processed', 'deathknight-unholy-1')
        assert next(row for row in records if row['candidate_id'] == failed_id) == failed
        return
    dispatched = set()
    active = 0
    lock = threading.Lock()
    together = threading.Event()
    save_attempted = threading.Event()
    save_attempts = []
    child = None
    real_write = result_store.write
    def failing_save(table, key, rows, **kwargs):
        if interruption == 'store_failure' and table == 'seed_processed' and any(row['status'] == 'completed' for row in rows):
            save_attempts.append([row['candidate_id'] for row in rows if row['status'] == 'completed'])
            save_attempted.set()
            raise PermissionError('父级汇总暂时不可写')
        return real_write(table, key, rows, **kwargs)
    # 这两例只检查任务所有权与故障取消，不需要构造有编辑机会的搜索轮次。
    with training_boundary():
        native = sequence.evaluate
        def observed(*args, **kwargs):
            nonlocal active, child
            path = next(part for part in Path(args[2]).parts if part in ids)
            with lock:
                active += 1
                dispatched.add(path)
                if len(dispatched) == 2:
                    together.set()
            try:
                assert together.wait(5), '必须先有两个实际训练worker'
                if interruption == 'foreground':
                    with lock:
                        if child is None:
                            module_dir = str(Path(seed_activity.__file__).parent)
                            code = '\n'.join(('import sys,time', 'sys.path.insert(0, ' + repr(module_dir) + ')',
                                'import result_store', 'result_store.bind_project(' + repr(str(tmp_path)) + ')',
                                'from seed_activity import foreground_search', 'with foreground_search():',
                                '    time.sleep(0.3)'))
                            child = subprocess.Popen([sys.executable, '-c', code],
                                cwd=str(Path(seed_activity.__file__).parents[2]), env=os.environ.copy(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    assert kwargs['runtime'].cancel_event.wait(5), '普通搜索必须取消全部训练worker'
                    kwargs['runtime'].check()
                elif path == ids[1]:
                    assert save_attempted.wait(10), '目标seed_processed完成结果保存故障尚未注入'
                    assert kwargs['runtime'].cancel_event.wait(10), '保存失败必须停止其他worker及后补派'
                    kwargs['runtime'].check()
                return native(*args, **kwargs)
            finally:
                with lock:
                    active -= 1
        started = time.monotonic()
        with patch.object(sequence, 'evaluate', side_effect=observed), \
                patch.object(result_store, 'write', side_effect=failing_save):
            assert command(tmp_path, args) == 2
        assert active == 0 and len(dispatched) == 2
        if interruption == 'store_failure':
            assert save_attempted.is_set() and save_attempts
        if child is not None:
            _, error = child.communicate(timeout=3)
            assert child.returncode == 0, error.decode(errors='replace')
            assert time.monotonic() - started < 5
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == previous
    records = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    assert all(row['candidate_id'][:12] in dispatched for row in records)


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


@pytest.mark.parametrize('case', ['structured', 'empty'])
def test_training_entry_adapts_burst_sources_and_history_without_rewriting_them(tmp_path, capsys, monkeypatch, case,
                                                                              single_candidate_training_rounds,
                                                                              memory_training_center):
    import burst
    import engine
    import result_store
    import seed_training
    from test_character_export import sample_profile

    entrypoints = (engine.reference, engine.inspect)
    definition = json.loads(Path('projects/sim2gse/burst/unholy.json').read_text(encoding='utf-8'))
    reset = dict(timeout_seconds=3, flags=['target'])
    original = [
        ['army_of_the_dead'], ['dark_transformation', 'use_item,slot=trinket1', 'use_item,slot=trinket2', 'potion'],
        dict(kind='Loop', count=3, blocks=[['army_of_the_dead'], ['dark_transformation']]),
        dict(kind='CastSequence', members=['army_of_the_dead', 'dark_transformation'], reset=reset),
        dict(kind='Loop', count=2, blocks=[['army_of_the_dead'], ['outbreak'], ['outbreak'],
                                         ['dark_transformation'], ['scourge_strike']]),
        dict(kind='WaitClicks', clicks=2),
        dict(kind='CastSequence', members=['death_coil', 'army_of_the_dead', 'scourge_strike',
                                           'dark_transformation', 'death_coil'], reset=reset),
        ['death_coil']]
    expected = [dict(kind='Loop', count=2, blocks=[['outbreak'], ['outbreak'], ['scourge_strike']]),
                dict(kind='WaitClicks', clicks=2),
                dict(kind='CastSequence', members=['death_coil', 'scourge_strike', 'death_coil'], reset=reset),
                ['death_coil']]
    errors = {'empty': '没有可训练的普通循环', 'single-member': '仅剩一个成员', 'unknown': '不支持的动作', 'invalid-block': '1 至 16 个命令', 'invalid-program': '超过 128 个顶层节点'}
    if case == 'changed-definition':
        definition['version'] += '-test-coil'
        definition['blocks'] = [[dict(kind='spell', simc_action='death_coil', name='死亡缠绕', spell_id=1002)]]
        definition['excluded_spell_ids'] = [1002]
        original = [['death_coil'], ['dark_transformation'], ['outbreak']]
        expected = [['dark_transformation'], ['outbreak']]
        from test_search import _minimal_rule_pack
        rules = _minimal_rule_pack()
        # 本构造把death_coil交给独立爆发，普通起手不能再包含它。
        for configuration in rules['configurations']:
            opener = configuration['opener']
            opener['source_steps'] = opener['source_steps'][:2]
            opener['ordinary_steps'] = opener['ordinary_steps'][:2]
        rules_path = tmp_path / 'rules.json'
        rules_path.write_text(json.dumps(rules), encoding='utf-8')
        monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(rules_path))
    elif case == 'empty':
        original = [dict(kind='Loop', count=3, blocks=[['army_of_the_dead'], ['dark_transformation']]),
                    dict(kind='WaitClicks', clicks=2)]
    elif case == 'single-member':
        original = [dict(kind='CastSequence', members=['army_of_the_dead', 'death_coil'], reset=reset)]
    elif case == 'unknown':
        original = [['army_of_the_dead'], ['not_a_real_action']]
    elif case == 'invalid-block':
        original = [['army_of_the_dead'] * 16 + ['death_coil']]
    elif case == 'invalid-program':
        original = [['death_coil']] * 128 + [dict(kind='CastSequence')]
    burst.publish(definition)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    source = tmp_path / 'material.json'
    source.write_text(json.dumps(dict(label=case, class_name='deathknight', spec='unholy', source='constructed-test',
        original='original fixture', instructions='repeat', semantic='preserved', changes=[], family='source-family',
        core=[['army_of_the_dead']] if case == 'structured' else [], program=original)), encoding='utf-8')
    if case != 'history-only':
        assert seed_training.main(['--project', str(tmp_path), 'register', str(source)]) == 0
    source_before = result_store.read_records('seed_candidates', 'registry')
    result_store.write('runs', 'historical-source', [dict(dict.fromkeys(result_store.RUN_SCHEMA),
        run_id='historical-source', status='completed', profile={'identity': {'class': 'deathknight', 'spec': 'unholy'}},
        candidate_data_key='historical-program', search_dps=90.)], schema=result_store.RUN_SCHEMA)
    result_store.write('candidates', 'historical-program', [dict(dict.fromkeys(result_store.CANDIDATE_SCHEMA),
        run_id='historical-source', candidate_key='historical-key', candidate_data_key='historical-program',
        source='search', program=original)], schema=result_store.CANDIDATE_SCHEMA)
    history_before = result_store.read_records('candidates', 'historical-program')
    args = ['--project', str(tmp_path), 'run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work')]
    if case == 'structured':
        args += ['--max-processes', '4']
    with training_boundary(), monkeypatch.context() as guarded:
        inspect = engine.inspect
        def full_catalogue(*args, **kwargs):
            capabilities = inspect(*args, **kwargs)
            capabilities['actions'].append(dict(kind='item', slot=14, item_id=250228,
                simc_action='use_item,slot=trinket2', name='使用trinket2', gcd_ms=0))
            return capabilities
        guarded.setattr(engine, 'inspect', full_catalogue)
        reference = engine.reference
        def burst_reference(*args, **kwargs):
            native = reference(*args, **kwargs)
            native['identity']['data_version'] = definition['data_version']
            return native
        guarded.setattr(engine, 'reference', burst_reference)
        assert seed_training.main(args) == 0
    assert seed_training.main(['--project', str(tmp_path), 'list', '--state', 'processed']) == 0
    records = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len(records) == (1 if case == 'history-only' else 2)
    if case in errors:
        assert all(row['status'] == 'rejected' and errors[case] in row['error'] for row in records)
        if case not in ('invalid-block', 'invalid-program'):
            for row in records:
                adaptation = json.loads(row['comparison'])['adaptation']
                assert adaptation['original_program'] == original and adaptation['removed']
    else:
        assert any(row['status'] == 'completed' for row in records), records
        completed = next(row for row in records if row['status'] == 'completed')
        assert json.loads(completed['initial_program']) == expected
        adaptation = json.loads(completed['comparison'])['adaptation']
        assert adaptation['original_program'] == original and adaptation['removed']
        if case != 'history-only':
            assert any(row['status'] == 'rejected' and '相同行为候选' in row['error'] for row in records)
        if case == 'structured':
            assert adaptation['initial_core_retained'] is False
            assert seed_training.main(['--project', str(tmp_path), 'list', '--state', 'selected']) == 0
            assert all(row['family'] == 'history-search' for row in json.loads(capsys.readouterr().out))
        with training_boundary(), monkeypatch.context() as guarded:
            guarded.setattr(engine, 'reference', burst_reference)
            guarded.setattr(engine, 'inspect', full_catalogue)
            assert seed_training.main(args) == 0
            assert json.loads(capsys.readouterr().out)[0]['processed'] == 0
    registry = result_store.read_records('seed_candidates', 'registry')
    assert all(row in registry for row in source_before)
    assert any(row['source_id'] == 'history:historical-source' for row in registry)
    assert result_store.read_records('candidates', 'historical-program') == history_before
    monkeypatch.undo()
    assert (engine.reference, engine.inspect) == entrypoints


def test_prepare_run_reuses_context_and_only_rebuilds_changed_sources(tmp_path, capsys, memory_training_center):
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
        assert command(tmp_path, ['run', *options]) == 0
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
        assert command(tmp_path, ['run', *options]) == 2
    assert '快照保存故障' in capsys.readouterr().err
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', rebuilt['config_key']]) == 0
    assert json.loads(capsys.readouterr().out) == before_failure


def test_training_freezes_unique_queue_with_all_cores_and_stable_representation(tmp_path, capsys, monkeypatch,
                                                                             memory_training_center,
                                                                             single_candidate_training_rounds):
    import burst
    import sequence
    import engine
    from unittest.mock import patch
    from test_character_export import sample_profile

    definition = json.loads(Path('projects/sim2gse/burst/unholy.json').read_text(encoding='utf-8'))
    burst.publish(definition)
    @contextmanager
    def boundary():
        with training_boundary():
            reference = engine.reference
            def burst_reference(*args, **kwargs):
                native = reference(*args, **kwargs)
                native['identity']['data_version'] = definition['data_version']
                return native
            inspect = engine.inspect
            def full_catalogue(*args, **kwargs):
                capabilities = inspect(*args, **kwargs)
                capabilities['actions'].append(dict(kind='item', slot=14, item_id=250228,
                    simc_action='use_item,slot=trinket2', name='使用trinket2', gcd_ms=0))
                return capabilities
            with patch.object(engine, 'reference', side_effect=burst_reference), \
                 patch.object(engine, 'inspect', side_effect=full_catalogue):
                yield
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    flat = [['death_coil'], ['outbreak'], ['death_coil'], ['outbreak']]
    source = tmp_path / 'material.json'
    rows = [dict(label=name, class_name='deathknight', spec='unholy', source='fixture', source_id=name,
                 original='fixture', instructions='repeat', semantic='preserved', changes=[], family=name,
                 core=core, program=program) for name, program, core in [
        ('a-flat', flat, [['death_coil']]),
        ('b-tree', [dict(kind='Loop', count=2, blocks=[['death_coil'], ['outbreak']])], [['outbreak']]),
        ('c-burst', [['army_of_the_dead'], *flat], [['army_of_the_dead']]),
        ('e-distinct', [['scourge_strike']], [['scourge_strike']])]]
    for row in rows:
        source.write_text(json.dumps(row), encoding='utf-8')
        assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    options = ['--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work'), '--use-burst']
    with boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    prepared = json.loads(capsys.readouterr().out)[0]
    assert prepared['preparation']['registry_sources'] == 4
    assert prepared['preparation']['original_unique'] == 4
    assert prepared['preparation']['unique_inputs'] == 2
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', prepared['config_key']]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    entries = [row for row in snapshot if row['kind'] == 'source']
    flat_id = next(row['candidate_id'] for row in entries if row['source_id'] == 'a-flat')
    assert len(entries) == 4 and len({row['representative_id'] for row in entries}) == 2
    observed = []
    with boundary():
        evaluate = sequence.evaluate
        def inspect_frozen_queue(*args, **kwargs):
            if not observed:
                assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', prepared['config_key']]) == 0
                frozen = json.loads(capsys.readouterr().out)
                assert len([row for row in frozen if row['kind'] == 'source']) == 4
                observed.append(True)
            return evaluate(*args, **kwargs)
        with patch.object(sequence, 'evaluate', side_effect=inspect_frozen_queue):
            assert command(tmp_path, ['run', *options]) == 0
    assert observed
    assert command(tmp_path, ['list', '--state', 'processed', '--use-burst']) == 0
    processed = json.loads(capsys.readouterr().out.splitlines()[-1])
    representative = next(row for row in processed if row['candidate_id'] == flat_id)
    relationships = json.loads(representative['comparison'])['sources']
    assert {row['source_id'] for row in relationships} == {'a-flat', 'b-tree', 'c-burst'}
    assert next(row for row in relationships if row['source_id'] == 'c-burst')['initial_core_retained'] is False
    assert next(row for row in relationships if row['source_id'] == 'b-tree')['initial_core_retained'] is True
    tree_id = next(row['candidate_id'] for row in entries if row['source_id'] == 'b-tree')
    with boundary():
        assert command(tmp_path, ['run', *options, '--candidate-id', tree_id]) == 0
    scoped = json.loads(capsys.readouterr().out)[0]
    assert scoped['processed'] == 1 and scoped['preparation']['completed_paths'] == 1
    assert command(tmp_path, ['list', '--state', 'processed', '--use-burst']) == 0
    scoped_records = json.loads(capsys.readouterr().out)
    tree_path = next(row for row in scoped_records if row['candidate_id'] == tree_id)
    assert tree_path['status'] == 'completed'
    assert json.loads(tree_path['initial_program']) == rows[1]['program']
    assert next(row for row in scoped_records if row['candidate_id'] == flat_id)['status'] == 'completed'
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', prepared['config_key']]) == 0
    frozen = json.loads(capsys.readouterr().out)
    queued = json.loads(next(row['context'] for row in frozen if row['kind'] == 'context'))['frozen_queue']
    assert queued == [dict(candidate_id=tree_id, program=rows[1]['program'], source_ids=['b-tree'])]
    source.write_text(json.dumps(dict(rows[0], active=False)), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    with boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    assert json.loads(capsys.readouterr().out)[0]['preparation']['sources_rebuilt'] == 0
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', prepared['config_key']]) == 0
    after = [row for row in json.loads(capsys.readouterr().out) if row['kind'] == 'source' and row['status'] == 'ready']
    assert {row['representative_id'] for row in after if row['source_id'] != 'e-distinct'} == {flat_id}
    assert all(json.loads(row['representative_program']) == flat for row in after if row['source_id'] != 'e-distinct')
    source.write_text(json.dumps(rows[0]), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    with boundary():
        assert command(tmp_path, ['prepare', *options]) == 0
    assert json.loads(capsys.readouterr().out)[0]['preparation']['sources_rebuilt'] == 0
    assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', prepared['config_key']]) == 0
    reactivated = next(row for row in json.loads(capsys.readouterr().out) if row['source_id'] == 'a-flat')
    assert reactivated['status'] == 'ready' and reactivated['reason'] == ''

    updated = dict(rows[1], family='changed-core-family', core=[])
    source.write_text(json.dumps(updated), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    with boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('来源核心变化不得误废可靠成绩')):
        assert command(tmp_path, ['run', *options]) == 0
    remapped = json.loads(capsys.readouterr().out)[0]
    assert remapped['processed'] == 0 and remapped['preparation']['sources_rebuilt'] == 0
    assert command(tmp_path, ['list', '--state', 'processed', '--use-burst']) == 0
    completed = next(row for row in json.loads(capsys.readouterr().out) if row['candidate_id'] == flat_id)
    mapping = next(row for row in json.loads(completed['comparison'])['sources'] if row['source_id'] == 'b-tree')
    assert mapping['family'] == 'changed-core-family' and mapping['initial_core_retained'] is False
    assert command(tmp_path, ['list', '--state', 'selected', '--use-burst']) == 0
    selected = json.loads(capsys.readouterr().out)
    for row in [*rows[:1], updated, *rows[2:]]:
        source.write_text(json.dumps(dict(row, active=False)), encoding='utf-8')
        assert command(tmp_path, ['register', str(source)]) == 0
    capsys.readouterr()
    with boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('无活动输入不得派发训练')):
        assert command(tmp_path, ['run', *options]) == 0
    assert json.loads(capsys.readouterr().out)[0]['preparation']['unique_inputs'] == 0
    assert command(tmp_path, ['list', '--state', 'selected', '--use-burst']) == 0
    assert json.loads(capsys.readouterr().out) == selected


def test_training_runs_bounded_paths_and_persists_before_refilling(tmp_path, capsys,
                                                                  memory_training_center,
                                                                  single_candidate_training_rounds):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import result_store
    import sequence
    import threading
    import time

    outer, inner = 2, 1
    programs = [[['outbreak'], ['death_coil'], ['scourge_strike']],
                [['death_coil'], ['scourge_strike'], ['outbreak']],
                [['scourge_strike'], ['outbreak'], ['death_coil']]]
    for index, program in enumerate(programs):
        path = tmp_path / f'source-{index}.json'
        path.write_text(json.dumps(dict(label=str(index), source_id=f'parallel-{index}',
            class_name='deathknight', spec='unholy', source='fixture', original='fixture',
            instructions='repeat', semantic='preserved', changes=[], family=str(index),
            core=program[:1], program=program)), encoding='utf-8')
        assert command(tmp_path, ['register', str(path)]) == 0
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work'),
            '--max-trainings', str(outer), '--max-processes', str(inner), '--diagnostic-logging']
    active = peak = 0
    active_paths = set()
    overlap = 0
    dispatched = []
    lock = threading.Lock()
    gate = threading.Barrier(outer * inner)
    gated = {}
    ids = {row['candidate_id'][:12] for row in result_store.read_records('seed_candidates', 'registry')}
    with training_round_boundary(tmp_path):
        native = sequence.evaluate
        def observed(profile, candidate, folder, **kwargs):
            nonlocal active, peak, overlap
            path = next(part for part in Path(folder).parts if part in ids)
            synchronize = False
            with lock:
                if path not in dispatched:
                    if len(dispatched) >= outer:
                        assert any(row['status'] == 'completed' for row in
                                   result_store.read_records('seed_processed', 'deathknight-unholy-1'))
                    dispatched.append(path)
                active += 1
                active_paths.add(path)
                peak = max(peak, active)
                overlap = max(overlap, len(active_paths))
                if (path in dispatched[:outer] and kwargs.get('iterations') == 32 and
                        kwargs.get('trace') is False and gated.get(path, 0) < inner):
                    gated[path] = gated.get(path, 0) + 1
                    synchronize = True
            try:
                if synchronize:
                    gate.wait(15)
                time.sleep(.03 if path == dispatched[0] else .01)
                return native(profile, candidate, folder, **kwargs)
            finally:
                with lock:
                    active -= 1
                    # One candidate can have several native batches in flight.
                    running[path] = running.get(path, 0) - 1
                    if running[path] == 0:
                        active_paths.discard(path)
        running = {}
        def counted(*args, **kwargs):
            path = next(part for part in Path(args[2]).parts if part in ids)
            with lock:
                running[path] = running.get(path, 0) + 1
            return observed(*args, **kwargs)
        # The two-path gate excludes each path's initial traced batch, so request traces explicitly.
        with patch.object(sequence, 'evaluate', side_effect=counted):
            assert command(tmp_path, args) == 0
    output = json.loads(capsys.readouterr().out.splitlines()[-1])[0]
    assert output['preparation']['completed_paths'] == len(programs) and output['preparation']['dynamic_skips'] == 0
    assert sum(gated.values()) == outer * inner
    assert overlap == outer and peak == outer * inner
    assert len(dispatched) == len(programs)
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    records = json.loads(capsys.readouterr().out)
    assert len(records) == len(programs) and all(row['status'] == 'completed' and row['rounds'] == 2 for row in records)
    assert all(len(row['initial_scores']) == len(row['scores']) == 3 for row in records)
    prepared = result_store.read_records('seed_prepared', output['config_key'])
    frozen = json.loads(next(row['context'] for row in prepared if row['kind'] == 'context'))['frozen_queue']
    assert [row['candidate_id'] for row in records] == [row['candidate_id'] for row in frozen]


def test_training_shares_real_store_transactions_and_keeps_each_request_trace(tmp_path, capsys):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import result_store
    import search
    import sequence
    import threading
    target = [['death_coil'], ['outbreak'], ['scourge_strike'], ['outbreak']]
    starts = ([['outbreak'], ['death_coil'], ['scourge_strike'], ['outbreak']],
              [['outbreak'], ['scourge_strike'], ['death_coil'], ['outbreak']])
    for index, program in enumerate(starts):
        path = tmp_path / f'source-{index}.json'
        path.write_text(json.dumps(dict(label=str(index), source_id=str(index), class_name='deathknight',
            spec='unholy', source='fixture', original='fixture', instructions='repeat', semantic='preserved',
            changes=[], family=str(index), core=program[:1], program=program)), encoding='utf-8')
        assert command(tmp_path, ['register', str(path)]) == 0
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    def plateau(candidate):
        return 120. if [[action['simc_action'] for action in block] for block in candidate['blocks']] == target else 100.
    gate = threading.Barrier(2)
    gated = set()
    calls = []
    lock = threading.Lock()
    # 配置仅允许把消费动作移至首位：两材料各有一个真实合法操作到同一程序。
    # 使用正常首批实际trace，不恢复已移除的index99额外诊断批次。
    with guided_training_boundary(tmp_path, plateau, move_to_front=True):
        native = sequence.evaluate
        def observed(*args, **kwargs):
            candidate, folder = args[1], Path(args[2])
            iterations = kwargs.get('iterations', 100)
            wait = False
            with lock:
                calls.append(str(folder))
                token = folder.parents[1]
                if ('batches' in folder.parts and iterations == 32 and kwargs.get('trace') and
                        token not in gated):
                    gated.add(token)
                    wait = True
            if wait:
                gate.wait(15)
            return native(*args, **kwargs)
        with patch.object(sequence, 'evaluate', side_effect=observed):
            assert command(tmp_path, ['run', '--template', str(template), '--targets', '1',
                                      '--workspace', str(tmp_path / 'work'), '--diagnostic-logging']) == 0
    assert len(gated) == 2
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    records = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len(records) == 2 and all(row['status'] == 'completed' for row in records)
    local_batches = []
    runs = []
    trace_origins = []
    for row in records:
        folder = Path(row['task_path'])
        assert folder.parent.joinpath('cache.sqlite3').is_file()
        with sqlite3.connect(folder / 'task.sqlite3') as database:
            state = __import__('search').TaskStore.load_state(database)
            runs.append(state['run_id'])
            batches = {key: json.loads(value) for key, value in database.execute('SELECT key,value FROM batches')}
            local_batches.append(batches)
            traced = [(key, row['trace_source']) for key, row in batches.items()
                      if row.get('status') == 'success' and row['request']['trace']]
            assert traced
            for key, origin in traced:
                assert origin['run_id'] == state['run_id'] and origin['batch_key'] == key
                trace_origins.append(origin)
    common = set(local_batches[0]) & set(local_batches[1])
    shared_key = next(key for key in common if local_batches[0][key]['status'] == 'success' and
                      not local_batches[0][key]['request']['trace'] and
                      local_batches[0][key]['request']['purpose'] == 'search' and
                      local_batches[0][key]['dps'] == 120.)
    assert all('trace_source' not in batches[shared_key] for batches in local_batches)
    for origin in trace_origins:
        traces = result_store.read_records('traces', origin['storage_key'])
        assert traces and {row['run_id'] for row in traces} == {origin['run_id']}
        assert {row['batch_key'] for row in traces} == {origin['batch_key']}
    assert all(result_store.one('batches', 'batch_key', key) is not None for key in common
               if local_batches[0][key]['status'] == 'success')
    assert sum(row['native_batch_starts'] for row in records) == len(calls)
    assert all(row['batch_requests'] == row['native_batch_starts'] + row['cache_hits'] for row in records)
    # 第三材料也有一个合法单步到共同目标；首父真实trace不能冒标给目标缓存。
    source = tmp_path / 'cached-trace-source.json'
    third_start = [['outbreak'], ['scourge_strike'], ['outbreak'], ['death_coil']]
    source.write_text(json.dumps(dict(label='cached', source_id='2', class_name='deathknight', spec='unholy',
        source='fixture', original='fixture', instructions='repeat', semantic='preserved', changes=[],
        family='cached', core=[], program=third_start)), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    with guided_training_boundary(tmp_path, plateau, move_to_front=True):
        native = sequence.evaluate
        def reject_repeated_target(*args, **kwargs):
            commands = [[action['simc_action'] for action in block] for block in args[1]['blocks']]
            if commands == target and kwargs.get('iterations') == 32 and not kwargs.get('trace'):
                raise AssertionError('共同目标的已验证成功缓存不得重新评分')
            return native(*args, **kwargs)
        with patch.object(sequence, 'evaluate', side_effect=reject_repeated_target):
            assert command(tmp_path, ['run', '--template', str(template), '--targets', '1',
                                      '--workspace', str(tmp_path / 'work'), '--diagnostic-logging']) == 0
    records = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    recovered = next(row for row in records if json.loads(row['initial_program']) == third_start)
    with sqlite3.connect(Path(recovered['task_path']) / 'task.sqlite3') as database:
        state = __import__('search').TaskStore.load_state(database)
        cached = json.loads(database.execute('SELECT value FROM batches WHERE key=?', (shared_key,)).fetchone()[0])
    assert cached['status'] == 'success' and not cached['request']['trace'] and 'trace_source' not in cached
    assert recovered['cache_hits'] > 0
    for origin in trace_origins:
        original = result_store.read_records('traces', origin['storage_key'])
        assert original and {row['run_id'] for row in original} == {origin['run_id']}


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
    published = burst.publish(definition)
    from test_search import _minimal_rule_pack
    rules = _minimal_rule_pack()
    # 本定义特意包含death_coil，局部普通起手须与独立爆发动作隔离。
    for configuration in rules['configurations']:
        opener = configuration['opener']
        opener['source_steps'] = opener['source_steps'][:2]
        opener['ordinary_steps'] = opener['ordinary_steps'][:2]
    rules_path = tmp_path / 'rules.json'
    rules_path.write_text(json.dumps(rules), encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG', str(rules_path))
    material = tmp_path / 'material.json'
    material.write_text(json.dumps(dict(label='ordinary-loop', class_name='deathknight', spec='unholy',
        source='fixture', original='fixture', instructions='repeat', semantic='preserved', changes=[],
        family='plain', core=[], program=[['outbreak']])), encoding='utf-8')
    assert command(tmp_path, ['register', str(material)]) == 0
    capsys.readouterr()
    api = result_store._api()
    query, read_key = api['query'], api['read_key']
    discovery_queries = current_reads = references = 0

    def one_discovery(root, sql, parameters=None, **options):
        nonlocal discovery_queries
        if options.get('tables') == ['burst_definitions']:
            discovery_queries += 1
            if discovery_queries > 2:
                raise PermissionError('同次准备已知爆发身份不得再次通用发现')
        return query(root, sql, parameters, **options)

    def current_definition(root, table, key, **options):
        nonlocal current_reads
        if table == 'burst_definitions' and key == 'current_252':
            current_reads += 1
        return read_key(root, table, key, **options)

    monkeypatch.setattr(result_store, '_api', lambda: api)
    monkeypatch.setitem(api, 'query', one_discovery)
    monkeypatch.setitem(api, 'read_key', current_definition)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    with training_boundary(), monkeypatch.context() as scoped:
        reference = engine.reference

        def fixed_native(*args, **options):
            nonlocal references
            references += 1
            native = reference(*args, **options)
            native['identity']['data_version'] = definition['data_version']
            if changed and references == 1:
                replacement = dict(definition, version=definition['version'] + '-changed', instructions='changed')
                burst.publish(replacement)
            return native

        scoped.setattr(engine, 'reference', fixed_native)
        status = command(tmp_path, ['prepare', '--template', str(template), '--targets', '1', '5',
            '--use-burst', '--workspace', str(tmp_path / 'work')])
    if changed:
        assert status == 2
        assert '爆发定义已变化' in capsys.readouterr().err
        assert references == 1
        assert not (tmp_path / 'work/5').exists()
    else:
        assert status == 0
        scenes = json.loads(capsys.readouterr().out)
        assert [scene['targets'] for scene in scenes] == [1, 5]
        for scene in scenes:
            assert command(tmp_path, ['list', '--state', 'prepared', '--config-key', scene['config_key']]) == 0
            snapshot = json.loads(capsys.readouterr().out)
            context = json.loads(next(row['context'] for row in snapshot if row['kind'] == 'context'))
            assert context['burst']['definition_id'] == published['definition_id']
        assert references == 2 and current_reads == 3
    assert discovery_queries == 2


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
        if run_id == 'affected' and failure == 'foreign-reference':
            row['run_id'] = 'foreign'
        records = [row]
        if run_id == 'affected' and failure == 'duplicate':
            records.append(row)
        elif run_id == 'affected' and failure in ('mixed-duplicate', 'fallback-corrupt', 'fallback-unreadable'):
            records.append(dict(row, candidate_data_key='other_candidate'))
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
            if key == 'affected_candidate' and failure == 'fallback-unreadable':
                raise PermissionError('临时历史读取失败')
            if key == 'affected_candidate' and failure == 'fallback-corrupt':
                (Path(root) / 'candidates/affected_candidate.parquet').write_bytes(b'broken during group check')
        return read_key(root, table, key, **options)

    monkeypatch.setattr(result_store, '_api', lambda: api)
    monkeypatch.setitem(api, 'read_keys', candidate_groups)
    monkeypatch.setitem(api, 'read_key', known_single)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    with training_boundary():
        status = command(tmp_path, ['prepare', '--template', str(template), '--targets', '1',
                                  '--workspace', str(tmp_path / 'work')])
    if failure in ('corrupt', 'unreadable', 'fallback-corrupt', 'fallback-unreadable'):
        assert status == 2
        assert ('损坏' if failure in ('corrupt', 'fallback-corrupt') else '临时历史读取失败') in capsys.readouterr().err
        assert not (tmp_path / 'work').exists()
        assert command(tmp_path, ['list']) == 0
        assert json.loads(capsys.readouterr().out) == registry_before
        if failure.startswith('fallback-'):
            assert 'affected_candidate' in fallback_keys
            assert set(fallback_keys) <= {'valid_candidate', 'affected_candidate'}
        else:
            assert fallback_keys == []
    else:
        assert status == 0
        capsys.readouterr()
        assert command(tmp_path, ['list', '--state', 'unsupported']) == 0
        inactive = json.loads(capsys.readouterr().out)
        assert len(inactive) == 1 and inactive[0]['source_id'] == 'history:affected'
        assert ('引用不一致' if failure == 'foreign-reference' else '候选记录缺失') in inactive[0]['unavailable_reason']
        assert command(tmp_path, ['list']) == 0
        active = json.loads(capsys.readouterr().out)
        assert {row['source_id'] for row in active} == {before['candidate_id'], 'history:valid'}
        assert set(fallback_keys) == ({'valid_candidate', 'affected_candidate'}
                                      if failure in ('missing', 'duplicate', 'mixed-duplicate') else set())


def test_training_prepare_freezes_opener_aligned_burst_through_public_cli(tmp_path, monkeypatch, capsys):
    import burst
    from test_burst import reviewed_fixture,character_seed_boundary
    definition,raw=reviewed_fixture()
    published=burst.publish(definition)
    pack = dict(schema_version=2, general=dict(templates={}),
        identity_mappings=dict(hero_talents={'sample_hero': 17}),
        object_sets={'sample': {
            'tap': dict(kind='action', native_action='scourge_strike', base_button='scourge_strike',
                        native_forms=['scourge_strike']),
            'big': dict(kind='action', native_action='army_of_the_dead', base_button='army_of_the_dead',
                        native_forms=['army_of_the_dead'])}},
        configurations=[dict(key=dict(specialization_id=252, hero_talent='sample_hero',
            target_type='single_target'), objects_ref='sample', execution_ref='fixture_macro',
            states={'only': dict(effect=None, expected=True, priority=[])},
            opener=dict(source_basis='fixture: shared ordered initialization',
                source_steps=['tap', 'tap', 'big', 'tap'], precombat=[],
                burst_anchor=dict(source_step=3, estimation='preceding_steps_effective_gcd_and_input_interval',
                                  freeze_per_task=True),
                independent_burst_source_steps=[dict(action='big', source_step=3, mapping='burst')],
                ordinary_steps=[dict(action='tap', source_step=index, source_form='scourge_strike',
                    attribute_query=dict(native_form='scourge_strike', base_button='scourge_strike',
                                         missing='unknown_no_base_cost_fallback')) for index in (1, 2, 4)]))],
        execution_evidence={'fixture_macro': dict(
            blocks=[[command['simc_action'] for command in block] for block in definition['blocks']],
            repeat_ms=45000, input_window_ms=1000, pause_ordinary=True,
            resume_same_position=True, preserve_burst_position_across_windows=True,
            protected_actions_from='actual_configured_execution_blocks')})
    path=tmp_path/'rules.json';path.write_text(json.dumps(pack),encoding='utf-8')
    monkeypatch.setenv('SIM2GSE_RULE_CONFIG',str(path))
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
    assert context['burst']['plan']==dict(published['plan'],start_ms=2000)
    assert context['rule_initialization']['first_burst_ms']==2000
    assert context['preparation_input']['simulation']['scene']=='single_target'
    assert context['rule_snapshot']['pack']==pack
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
            burst_identity=dict(spec_id=252,definition_id=published['definition_id']),rule_snapshot=context['rule_snapshot'])
    assert champion['status']=='selected',champion
    assert champion['candidate_id']==completed[0]['candidate_id']
    assert champion['condition_input']['burst']['plan']['start_ms']==2000
