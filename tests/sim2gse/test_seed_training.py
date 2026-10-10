"""Manual training command uses the existing installed data center."""
import json
from pathlib import Path
import subprocess
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
        result = _fast_evaluate(profile, candidate, folder, **kwargs)
        damage = damage_for(candidate)
        result['summary']['dps'] = damage
        result['report']['sim']['statistics']['raid_dps']['mean'] = damage
        result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
        Path(folder, 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result

    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
        yield

import pytest


@pytest.fixture(autouse=True)
def training_center(tmp_path, installed_data_store, monkeypatch):
    import result_store
    (tmp_path / 'data').mkdir(exist_ok=True)
    monkeypatch.setattr(result_store, '_BOUND_PROJECT', None)
    subprocess.run([sys.executable, str(installed_data_store / 'scripts/project_binding.py'),
                    'connect', '--project', str(tmp_path)], check=True, capture_output=True)


def command(tmp_path, args):
    from seed_training import main
    # These existing cases exercise the explicitly retained legacy training mode.
    if args[0] in ('run', 'list') and '--use-burst' not in args:
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


def test_training_unknown_material_is_rejected_before_compute(tmp_path, capsys, monkeypatch):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('错误材料编号不能启动计算')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    assert main(['--project', str(tmp_path), 'run', '--candidate-id', 'missing-material',
                 '--workspace', str(tmp_path / 'work')]) == 2
    assert '训练材料不存在' in capsys.readouterr().err
    assert not (tmp_path / 'work').exists()


@pytest.mark.parametrize('entry', ['check', 'run'])
def test_training_entry_refuses_missing_definition_before_starting_compute(tmp_path, capsys, monkeypatch, entry):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('缺少审核定义时不能启动计算进程')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    assert main(['--project', str(tmp_path), entry,
                 *(['--workspace', str(tmp_path / 'work')] if entry == 'run' else [])]) == 2
    assert '已审核' in capsys.readouterr().err


def test_training_check_uses_fixed_specialization_burst_for_standard_talents(tmp_path, capsys, monkeypatch):
    import burst
    import result_store
    from seed_training import main

    result_store.bind_project(tmp_path)
    definition = json.loads(Path('projects/sim2gse/burst/unholy.json').read_text(encoding='utf-8'))
    published = burst.publish(definition)

    def forbidden_process(*args, **kwargs):
        raise AssertionError('只读检查不能启动计算')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    assert main(['--project', str(tmp_path), 'check']) == 0
    output = json.loads(capsys.readouterr().out)
    assert output['burst_definition_id'] == published['definition_id']
    assert output['talent_sha256'] == '25290264e714733e77e73c453363fa128792bfd219bece3854d5e6193b4e50da'


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


def test_training_command_stops_after_two_unimproved_rounds_and_reuses_completed_work(tmp_path, capsys):
    from seed_training import main
    from test_character_export import sample_profile
    from unittest.mock import patch
    import sequence
    import result_store

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='test', class_name='deathknight', spec='unholy',
        source='constructed-test', original='independent fixture', instructions='repeat',
        semantic='preserved', changes=[], family='plain', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile() + '\nactions=auto_attack\n', encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    selected_id = result_store.read_records('seed_candidates', 'registry')[0]['candidate_id']
    other = json.loads(source.read_text(encoding='utf-8'))
    other['label'] = 'not selected for this run'
    source.write_text(json.dumps(other), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work'),
            '--candidate-id', selected_id]
    real_write = result_store.write
    def failing_publish(table, key, rows, **kwargs):
        if table == 'seed_selected':
            raise PermissionError('发布目标暂时不可写')
        return real_write(table, key, rows, **kwargs)
    with training_boundary(), patch.object(result_store, 'write', side_effect=failing_publish):
        assert command(tmp_path, args) == 2
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1')
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    assert len(processed) == 1
    assert processed[0]['rounds'] == 2
    assert processed[0]['stop_reason'] == 'no_improvement'
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'selected', '--targets', '1']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, args) == 0


def test_training_command_preserves_matched_work_for_two_and_four_processes(tmp_path, capsys):
    from test_character_export import sample_profile
    from test_search import _fast_evaluate
    from unittest.mock import patch
    import sequence
    import threading
    import time

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='parallel', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three actions', instructions='repeat',
        semantic='preserved', changes=[], family='plain', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    observations = []
    for workers in (None, 4):
        active = peak = 0
        requests = []
        lock = threading.Lock()

        def evaluate(profile, candidate, folder, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                requests.append((candidate['blocks'], kwargs['iterations'], kwargs['seed']))
            try:
                time.sleep(.02)  # 外部引擎边界等待，确保同层请求确实重叠。
                result = _fast_evaluate(profile, candidate, folder, **kwargs)
                result['summary']['dps'] = 100.
                result['report']['sim']['statistics']['raid_dps']['mean'] = 100.
                result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = 100.
                Path(folder, 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
                return result
            finally:
                with lock:
                    active -= 1

        workspace = tmp_path / ('work-2' if workers is None else 'work-4')
        run_args = args[:-1] + [str(workspace)]
        with training_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
            assert command(tmp_path, run_args + ([] if workers is None else ['--max-processes', str(workers)])) == 0
        assert peak == (2 if workers is None else 4)
        assert command(tmp_path, ['list', '--state', 'processed']) == 0
        rows = json.loads(capsys.readouterr().out.splitlines()[-1])
        record = rows[-1]
        assert record['status'] == 'completed'
        assert record['rounds'] == 2
        assert record['stop_reason'] == 'no_improvement'
        observations.append((record, sorted(json.dumps(row, sort_keys=True) for row in requests)))
    first, second = observations
    assert first[0]['condition'] == second[0]['condition']
    for field in ('initial_program', 'program', 'scores', 'initial_scores', 'native_batch_starts', 'batch_requests'):
        assert first[0][field] == second[0][field]
    assert first[1] == second[1]
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, run_args + ['--max-processes', '2']) == 0
        assert command(tmp_path, run_args + ['--max-processes', '4']) == 0


def test_training_entry_reads_internal_concurrency_and_reuses_complete_scores(tmp_path, capsys, monkeypatch):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import simulation_config
    import sequence
    import threading
    import time

    settings = tmp_path / 'config.toml'
    settings.write_text('[simulation]\ntarget_count=3\n[training]\nmax_processes=4\n', encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', settings)
    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='internal', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three actions', instructions='repeat', semantic='preserved',
        changes=[], family='plain', core=[], program=[['outbreak'], ['death_coil'], ['scourge_strike']])),
        encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    active = peak = 0
    lock = threading.Lock()
    with training_boundary():
        native = sequence.evaluate
        def observed(*args, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(.02)
                return native(*args, **kwargs)
            finally:
                with lock:
                    active -= 1
        with patch.object(sequence, 'evaluate', side_effect=observed):
            assert command(tmp_path, args) == 0
    assert peak == 4
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    before = json.loads(capsys.readouterr().out.splitlines()[-1])
    settings.write_text('[simulation]\ntarget_count=3\n[training]\nmax_processes=16\n', encoding='utf-8')
    assert simulation_config.load_config()['target_count'] == 3
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复训练或复测')):
        assert command(tmp_path, args) == 0
        assert command(tmp_path, args + ['--max-processes', '2']) == 0
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == before
    import search
    monkeypatch.setattr(search, 'SEARCH_ALGORITHM', 'changed-search-semantics')
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=ValueError('真实语义变化重新评分')):
        assert command(tmp_path, args) == 2
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    changed = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len({row['condition'] for row in changed}) == 2
    assert any(row['status'] == 'failed' for row in changed)


def legacy_batch_fixture(tmp_path, *, mutate_input=lambda payload: None, burst_context=None):
    """构造完整旧条件/检查点/成绩证据；不冒充本机真实成绩。"""
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
    payload['rules'].update({key: values[0] for key, values in LEGACY_EXECUTION_RULES.items()})
    payload = json.loads(json.dumps(payload))
    mutate_input(payload)
    condition = digest(payload)
    batch = tmp_path / 'work' / '1' / condition[:12]
    folder = batch / candidate['candidate_id'][:12]
    folder.mkdir(parents=True)
    (batch / 'standard.simc').write_text(text, encoding='utf-8')
    (batch / 'condition.txt').write_text(condition, encoding='ascii')
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
    evidence = dict(condition_input=payload, source_commit=LEGACY_SOURCE_COMMIT,
                    semantic_versions=LEGACY_SEMANTIC_VERSIONS)
    return template, batch, evidence


@pytest.fixture
def legacy_engine_boundary():
    with training_boundary():
        yield


def test_training_entry_reuses_verified_legacy_namespace_without_retraining(tmp_path, monkeypatch, capsys,
                                                                          legacy_engine_boundary):
    import result_store
    import sequence
    from seed_training import adopt_legacy_condition, validate_training_identity
    template, batch, evidence = legacy_batch_fixture(tmp_path)
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work'),
            '--max-processes', '4']
    monkeypatch.setattr(sequence, 'evaluate', lambda *a, **kw: pytest.fail('完整旧成绩不能重算'))
    assert command(tmp_path, args) == 2
    assert '缺少完整身份凭据' in capsys.readouterr().err
    before = (Path(processed[0]['task_path']) / 'task.sqlite3').read_bytes()
    # 原Python输入可能是tuple，检查点/JSON凭据是list，规范摘要仍相同。
    evidence['condition_input']['config']['batch_targets'] = tuple(evidence['condition_input']['config']['batch_targets'])
    manifest = adopt_legacy_condition(batch, evidence, processed=processed, selected=[])
    assert command(tmp_path, args) == 0
    assert result_store.read_records('seed_processed', 'deathknight-unholy-1') == processed
    assert (Path(processed[0]['task_path']) / 'task.sqlite3').read_bytes() == before
    assert manifest['condition'] == processed[0]['condition'] != manifest['semantic_condition']
    assert manifest['executions'][0]['config']['max_processes'] == 2
    payload = evidence['condition_input']
    validated = validate_training_identity(batch, payload['template'], payload['engines'],
        dict(payload['config'], max_processes=4), payload['simulation'])
    assert validated['condition'] == processed[0]['condition']
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1')[0]['condition'] == processed[0]['condition']


@pytest.mark.parametrize('fault', ['none', 'missing_source', 'changed_source', 'changed_legacy_content', 'changed_current'])
def test_training_entry_reuses_legacy_only_with_checked_original_line_endings(tmp_path, fault,
                                                                            legacy_engine_boundary,
                                                                            monkeypatch):
    import hashlib
    import result_store
    import sequence
    from engine import ROOT
    from seed_training import adopt_legacy_condition, LEGACY_SOURCE_COMMIT
    keys = ['projects/sim2gse/' + name for name in
            ('gse_import.py', 'macro_interpreter.py', 'runtime.py')]
    source_root = tmp_path / 'legacy-source'
    original_rules = {}
    normalized_hashes = {}
    for key in keys:
        blob = subprocess.check_output(['git', 'show', LEGACY_SOURCE_COMMIT + ':' + key], cwd=ROOT)
        normalized = blob.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        original = normalized.replace(b'\n', b'\r\n', 1)
        if fault == 'changed_legacy_content' and key == keys[0]:
            original = original.replace(b'import hashlib', b'import random as hashlib', 1)
        source = source_root / key
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(original)
        original_rules[key] = hashlib.sha256(original).hexdigest()
        normalized_hashes[key] = hashlib.sha256(normalized).hexdigest()
    template, batch, evidence = legacy_batch_fixture(tmp_path,
        mutate_input=lambda payload: payload['rules'].update(original_rules))
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    original_payload = json.loads(json.dumps(evidence['condition_input']))
    checkpoint = Path(processed[0]['task_path']) / 'task.sqlite3'
    before = checkpoint.read_bytes()
    if fault == 'missing_source':
        (source_root / keys[0]).unlink()
    elif fault == 'changed_source':
        with (source_root / keys[0]).open('ab') as handle:
            handle.write(b'# not the recorded original\n')
    if fault in ('missing_source', 'changed_source', 'changed_legacy_content'):
        with pytest.raises(ValueError):
            adopt_legacy_condition(batch, evidence, processed=processed, selected=[], source_root=source_root)
        assert not (batch / 'identity.json').exists()
        assert checkpoint.read_bytes() == before
        return
    manifest = adopt_legacy_condition(batch, evidence, processed=processed, selected=[], source_root=source_root)
    assert evidence['condition_input'] == original_payload == manifest['condition_input']
    assert manifest['condition'] == processed[0]['condition']
    assert manifest['legacy_line_endings'] == {key: dict(raw_sha256=original_rules[key],
        normalized_sha256=normalized_hashes[key]) for key in keys}
    monkeypatch.setattr(sequence, 'evaluate', lambda *args, **kwargs: pytest.fail('可靠完整旧成绩不能重算'))
    if fault == 'changed_current':
        original_read = Path.read_bytes
        changed_path = (ROOT / keys[0]).resolve()
        monkeypatch.setattr(Path, 'read_bytes', lambda path: original_read(path).replace(
            b'import hashlib', b'import random as hashlib', 1)
            if path.resolve() == changed_path else original_read(path))
    assert command(tmp_path, ['run', '--template', str(template), '--targets', '1',
        '--workspace', str(tmp_path / 'work'), '--max-processes', '4']) == (2 if fault == 'changed_current' else 0)
    assert checkpoint.read_bytes() == before
    assert result_store.read_records('seed_processed', 'deathknight-unholy-1') == processed


def test_training_entry_can_start_changed_template_without_borrowing_unproven_legacy(tmp_path,
                                                                                  legacy_engine_boundary):
    import result_store
    import sequence
    from unittest.mock import patch
    template, _, _ = legacy_batch_fixture(tmp_path)
    original = result_store.read_records('seed_processed', 'deathknight-unholy-1')[0]
    template.write_text(template.read_text(encoding='utf-8') + '\n# new role revision\n', encoding='utf-8')
    with patch.object(sequence, 'evaluate', side_effect=ValueError('新模板重新评分')):
        assert command(tmp_path, ['run', '--template', str(template), '--targets', '1',
            '--workspace', str(tmp_path / 'work'), '--max-processes', '4']) == 2
    rows = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    assert any(row == original for row in rows)
    assert len({row['condition'] for row in rows}) == 2


@pytest.mark.parametrize('fault', ['source', 'missing_rule', 'changed_rule', 'versions', 'checkpoint', 'record',
                                 'selected_program', 'selected_scores'])
def test_legacy_adoption_refuses_incomplete_or_unknown_proof(tmp_path, fault, legacy_engine_boundary):
    import result_store
    from seed_training import adopt_legacy_condition
    def mutate(payload):
        if fault == 'missing_rule':
            payload['rules'].pop('projects/sim2gse/engine.py')
        elif fault == 'changed_rule':
            payload['rules']['projects/sim2gse/engine.py'] = 'unreviewed'
    template, batch, evidence = legacy_batch_fixture(tmp_path, mutate_input=mutate)
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    if fault == 'source':
        evidence['source_commit'] = 'unknown'
    elif fault == 'versions':
        evidence['semantic_versions'] = dict(evidence['semantic_versions'], behavior='unknown')
    elif fault == 'checkpoint':
        with sqlite3.connect(Path(processed[0]['task_path']) / 'task.sqlite3') as database:
            database.execute("UPDATE state_fields SET value=? WHERE key='training_condition'", ('"other"',))
    elif fault == 'record':
        processed[0]['condition'] = 'other'
    selected = []
    if fault.startswith('selected_'):
        payload = evidence['condition_input']
        selected = [dict(candidate_id=processed[0]['candidate_id'], condition=processed[0]['condition'],
            template_sha256=payload['template'], engines=payload['engines'],
            program=json.loads(processed[0]['program']), scores=processed[0]['scores'])]
        if fault == 'selected_program':
            selected[0]['program'] = [['death_coil']]
        else:
            selected[0]['scores'] = [200.] * 3
    with pytest.raises(ValueError):
        adopt_legacy_condition(batch, evidence, processed=processed, selected=selected)
    assert not (batch / 'identity.json').exists()


def test_training_condition_excludes_only_execution_and_keeps_real_inputs(tmp_path, legacy_engine_boundary):
    from copy import deepcopy
    from seed_training import semantic_condition, semantic_versions
    _, _, evidence = legacy_batch_fixture(tmp_path)
    payload, versions = evidence['condition_input'], semantic_versions()
    expected = semantic_condition(payload, versions)
    execution = deepcopy(payload)
    execution['config']['max_processes'] = 16
    execution['rules']['projects/sim2gse/seed_training.py'] = 'logging-only-source-change'
    assert semantic_condition(execution, versions) == expected
    for field, value in [('template', 'new-role'), ('engines', {'baseline': 'new-engine'}),
                         ('retest', [20261011]), ('effective_options', ['threads=2'])]:
        assert semantic_condition(dict(payload, **{field: value}), versions) != expected
    for key in ('random_seed', 'iterations', 'no_improvement_rounds', 'input_interval_ms'):
        changed = deepcopy(payload)
        changed['config'][key] += 1
        assert semantic_condition(changed, versions) != expected
    assert semantic_condition(payload, dict(versions, search='new-search')) != expected


def test_upgrade_postcheck_accepts_legacy_identity_and_keeps_retest_key_checks(tmp_path, legacy_engine_boundary,
                                                                            monkeypatch):
    import result_store
    import runpy
    from search import digest
    from program import canonicalize_search_program
    from seed_training import adopt_legacy_condition, RETEST_SEEDS, PROCESSED_SCHEMA
    from test_search import _fast_capabilities
    _, batch, evidence = legacy_batch_fixture(tmp_path, burst_context={'definition_id': 'test-definition'})
    scope = 'deathknight-unholy-1-burst'
    rows = result_store.read_records('seed_processed', scope)
    row = rows[0]
    adopt_legacy_condition(batch, evidence, processed=rows, selected=[])
    for candidate_id in ('rejected-a', 'rejected-b'):
        rows.append(dict(row, candidate_id=candidate_id, status='rejected', error='explicit rejection'))
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
                 processed=[row['candidate_id'], 'rejected-a', 'rejected-b'])
    batches = {}
    for name in ('retest-initial', 'retest-final'):
        for seed in RETEST_SEEDS:
            key = digest(dict(folder=str(Path(row['task_path']) / name), seed=seed))
            batches[key] = dict(purpose='seed_retest', seed=seed, samples=127, dps=100.,
                engines=payload['engines'], condition_key=row['condition'], requested_iterations=128,
                program_identity=canonicalize_search_program(row['program'], _fast_capabilities())['form'])
    real_read, checked = result_store.read_records, []
    def read(table, key, **kwargs):
        if table == 'runs':
            return [dict(engines=payload['engines'])]
        if table == 'batches':
            checked.append(key)
            return [batches[key]]
        return real_read(table, key, **kwargs)
    monkeypatch.setattr(result_store, 'read_records', read)
    # 已经穿过旧身份及六个复测核验；此构造场景故意仅有一份成功材料。
    with pytest.raises(ValueError, match='缺少两类成功材料'):
        postcheck['check_scene'](scene, ready)
    assert len(checked) == 6
    batches[checked[0]]['condition_key'] = 'foreign-condition'
    with pytest.raises(ValueError, match='独立复测引擎、条件或程序身份不一致'):
        postcheck['check_scene'](scene, ready)


def test_training_entry_resumes_two_to_four_preserving_successful_batches(tmp_path, capsys, monkeypatch):
    import hashlib
    import result_store
    import sequence
    import seed_activity
    import threading
    import types
    import task
    import engine
    from engine import ROOT
    from seed_training import (_checkpoint_states, adopt_legacy_condition, training_condition_input,
        LEGACY_SOURCE_COMMIT, LEGACY_EXECUTION_RULES, LEGACY_SEMANTIC_VERSIONS)
    from test_character_export import sample_profile
    from unittest.mock import patch
    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='resume', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three actions', instructions='repeat', semantic='preserved',
        changes=[], family='plain', core=[], program=[['outbreak'], ['death_coil'], ['scourge_strike']])),
        encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    cancelled = threading.Event()
    @contextmanager
    def activity():
        yield cancelled
    monkeypatch.setattr(seed_activity, 'training_activity', activity)
    requests = []
    # 原固定提交的公开命令生成真实旧请求键；只替换文件来源和外部引擎边界。
    baseline = types.ModuleType('seed_training_baseline')
    baseline.__file__ = str(ROOT / 'projects/sim2gse/seed_training.py')
    old_source = subprocess.check_output(['git', 'show', LEGACY_SOURCE_COMMIT + ':projects/sim2gse/seed_training.py'],
                                         cwd=ROOT).decode('utf-8')
    exec(compile(old_source, baseline.__file__, 'exec'), baseline.__dict__)
    old_rules = task._rule_hashes(relative_to=ROOT)
    old_rules.update({key: values[0] for key, values in LEGACY_EXECUTION_RULES.items()})
    with training_boundary(), patch.object(task, '_rule_hashes', return_value=old_rules):
        evaluate = sequence.evaluate
        def interrupt(profile, candidate, folder, **kwargs):
            requests.append(Path(folder).name)
            result = evaluate(profile, candidate, folder, **kwargs)
            if len(requests) >= 12:
                cancelled.set()
            return result
        with patch.object(sequence, 'evaluate', side_effect=interrupt):
            assert baseline.main(['--project', str(tmp_path), *args, '--legacy']) == 2
    failed = result_store.read_records('seed_processed', 'deathknight-unholy-1')[0]
    batch = Path(failed['task_path']).parent
    before = next(iter(_checkpoint_states(batch).values()))
    assert before['phase'] == 'search' and before['pending'] and before['rng']
    with sqlite3.connect(Path(failed['task_path']) / 'task.sqlite3') as database:
        saved = {key: value for key, value in database.execute('SELECT key,value FROM batches')
                 if json.loads(value).get('status') == 'success'}
    assert saved
    with training_boundary():
        engines = {mode: engine.identity(mode)[1] for mode in ('baseline', 'controlled')}
        payload = training_condition_input(hashlib.sha256(template.read_text(encoding='utf-8').encode()).hexdigest(),
            engines, before['config'], {'target_count': 1, 'enable_omnium_talents': True})
        payload['rules'] = old_rules
        evidence = dict(condition_input=payload, source_commit=LEGACY_SOURCE_COMMIT,
                        semantic_versions=LEGACY_SEMANTIC_VERSIONS)
        adopt_legacy_condition(batch, evidence,
            processed=result_store.read_records('seed_processed', 'deathknight-unholy-1'), selected=[])
    cancelled.clear()
    resumed = []
    with training_boundary():
        evaluate = sequence.evaluate
        def observe(profile, candidate, folder, **kwargs):
            resumed.append(Path(folder).name)
            return evaluate(profile, candidate, folder, **kwargs)
        with patch.object(sequence, 'evaluate', side_effect=observe):
            assert command(tmp_path, args + ['--max-processes', '4']) == 0
    complete = result_store.read_records('seed_processed', 'deathknight-unholy-1')[0]
    assert complete['condition'] == failed['condition'] and complete['task_path'] == failed['task_path']
    assert complete['status'] == 'completed' and complete['cache_hits'] > 0
    assert not set(saved) & set(resumed)
    with sqlite3.connect(Path(complete['task_path']) / 'task.sqlite3') as database:
        after = dict(database.execute('SELECT key,value FROM batches'))
    assert all(after[key] == value for key, value in saved.items())
    manifest = json.loads((batch / 'identity.json').read_text(encoding='utf-8'))
    assert [segment['config']['max_processes'] for segment in manifest['executions']] == [2, 4]
    segment = manifest['executions'][-1]
    assert segment['before']['elapsed_seconds'] == before['elapsed_seconds']
    assert segment['before']['native_batch_starts'] == before['native_batch_starts']
    assert segment['after']['elapsed_seconds'] >= before['elapsed_seconds']


@pytest.mark.parametrize('value', ['0', '17', '1.5', 'four'])
def test_training_command_rejects_invalid_parallelism_before_compute(tmp_path, monkeypatch, value):
    from seed_training import main

    def forbidden_process(*args, **kwargs):
        raise AssertionError('非法并发参数不能启动计算进程')

    monkeypatch.setattr(subprocess, 'Popen', forbidden_process)
    with pytest.raises(SystemExit) as stopped:
        main(['--project', str(tmp_path), 'run', '--max-processes', value])
    assert stopped.value.code == 2


@pytest.mark.parametrize('partial_improvement', [False, True])
def test_training_improvements_reset_stagnation_and_can_exceed_five_rounds(tmp_path, partial_improvement):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import random
    import result_store
    import search

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='improving', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three actions', instructions='repeat',
        semantic='preserved', changes=[], family='plain', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    proposals = {}
    scores = {}

    class NoFallbackShuffle(random.Random):
        def randrange(self, *args, **kwargs):
            return 1 if args == (16,) else super().randrange(*args, **kwargs)

    def growing_program(parent, *args, **kwargs):
        size = len(parent) + 4
        positions = [(a, b) for a in range(size) for b in range(size) if a != b]
        key = json.dumps(parent, sort_keys=True)
        index = proposals.get(key, 0)
        round_index = sum(proposals.values()) // 16
        proposals[key] = index + 1
        if partial_improvement and len(parent) == 3 and index >= 24:
            return None
        a, b = positions[index % len(positions)]
        program = [['outbreak'] for _ in range(size)]
        program[a], program[b] = ['death_coil'], ['scourge_strike']
        if partial_improvement:
            score = 103. if len(parent) == 3 and index < 16 else 107.
        else:
            score = (103., 107., 107., 111., 113., 113., 113.)[round_index]
        scores[json.dumps(program)] = score
        return program

    def damage_for(candidate):
        program = [[action['simc_action'] for action in block] for block in candidate['blocks']]
        return scores.get(json.dumps(program), 103.)

    with training_boundary(damage_for), \
            patch.object(search, 'mutate', side_effect=growing_program), \
            patch.object(search.random, 'Random', NoFallbackShuffle):
        assert command(tmp_path, ['run', '--template', str(template), '--targets', '1',
                                  '--workspace', str(tmp_path / 'work')]) == 0
    completed = result_store.read_records('seed_processed', 'deathknight-unholy-1')[0]
    assert completed['status'] == 'completed'
    assert completed['rounds'] == (4 if partial_improvement else 7)
    assert completed['stop_reason'] == 'no_improvement'
    assert completed['scores'] == [107. if partial_improvement else 113.] * 3
    with sqlite3.connect('file:' + Path(completed['task_path'], 'task.sqlite3').as_posix() + '?mode=ro',
                         uri=True) as database:
        state = search.TaskStore.load_state(database)
    assert state['no_improvement'] == 2
    assert len(state['chains']) == 1


@pytest.mark.parametrize('max_processes', [2, 4])
def test_training_budget_stop_keeps_progress_and_previous_selected_snapshot(tmp_path, max_processes):
    from test_character_export import sample_profile
    from unittest.mock import patch
    from runtime import BudgetExceeded
    import result_store
    import sequence
    from test_search import _fast_evaluate

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
    with training_boundary():
        assert command(tmp_path, args) == 0
    previous = result_store.read_records('seed_selected', 'deathknight-unholy-1')
    assert previous
    template.write_text(sample_profile() + '\n# changed template\n', encoding='utf-8')
    def budget_on_first_round(*args, **kwargs):
        if kwargs.get('trace') and kwargs.get('iterations') == 2:
            raise BudgetExceeded('训练预算耗尽')
        return _fast_evaluate(*args, **kwargs)

    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=budget_on_first_round):
        assert command(tmp_path, args) == 2
    assert result_store.read_records('seed_selected', 'deathknight-unholy-1') == previous
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    failed = next(row for row in processed if row['status'] == 'failed')
    assert failed['stop_reason'] == 'search_deadline'
    assert '未收敛' in failed['error']
    assert Path(failed['task_path'], 'task.sqlite3').exists()


def test_unexpressible_material_is_retained_but_not_trained(tmp_path, capsys):
    source = tmp_path / 'unsupported.json'
    source.write_text(json.dumps(dict(label='two state machines', class_name='deathknight', spec='unholy',
        source='community original', original='/castsequence A,null\n/castsequence B,C',
        instructions='author instructions retained', semantic='unsupported', changes=['multiple stateful commands'],
        family='unexpressible', core=[], program=[])), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    assert command(tmp_path, ['list', '--state', 'unsupported']) == 0
    rows = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert rows[0]['original'] == '/castsequence A,null\n/castsequence B,C'
    assert command(tmp_path, ['list', '--state', 'pending']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == []


def test_history_candidate_is_retested_and_changed_template_is_not_reused(tmp_path, capsys):
    from test_character_export import sample_profile
    from unittest.mock import patch
    import sequence
    import result_store

    # Existing public center schemas, not a substitute history reader.
    result_store.write('runs', 'historic-1', [dict(dict.fromkeys(result_store.RUN_SCHEMA),
        run_id='historic-1', status='completed',
        profile={'identity': {'class': 'deathknight', 'spec': 'unholy'}},
        candidate_data_key='historic-candidate', search_dps=90.)], schema=result_store.RUN_SCHEMA)
    shared = {'adapter': 'search', 'metadata': {}, 'nodes': [
        {'kind': 'Action', 'commands': [{'kind': 'spell', 'simc_action': name}]}
        for name in ('outbreak', 'death_coil', 'scourge_strike')]}
    result_store.write('candidates', 'historic-candidate', [dict(dict.fromkeys(result_store.CANDIDATE_SCHEMA),
        run_id='historic-1',
        candidate_key='historic-key', candidate_data_key='historic-candidate', source='search',
        program=shared)], schema=result_store.CANDIDATE_SCHEMA)
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    with training_boundary():
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])[0]
    assert json.loads(first['initial_program']) == [['outbreak'], ['death_coil'], ['scourge_strike']]
    template.write_text(sample_profile() + '\n# new template revision\n', encoding='utf-8')
    with training_boundary(), patch.object(sequence, 'evaluate', side_effect=ValueError('新条件重新计算')):
        assert command(tmp_path, args) == 2
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    rows = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len({row['condition'] for row in rows}) == 2
    assert any(row['status'] == 'failed' for row in rows)


def test_training_skips_history_matching_completed_final_and_keeps_new_history(tmp_path, capsys):
    from test_character_export import sample_profile
    import result_store

    source = tmp_path / 'candidate.json'
    source.write_text(json.dumps(dict(label='training seed', class_name='deathknight', spec='unholy',
        source='constructed-test', original='three ordered actions', instructions='repeat',
        semantic='rewritten', changes=['use a short test program'], family='test-seed', core=[['outbreak']],
        program=[['outbreak'], ['death_coil'], ['scourge_strike']])), encoding='utf-8')
    template = tmp_path / 'standard.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    assert command(tmp_path, ['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    with training_boundary():
        assert command(tmp_path, args) == 0

    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    existing = json.loads(capsys.readouterr().out.splitlines()[-1])
    completed = next(row for row in existing if row['status'] == 'completed')
    initial = json.loads(completed['initial_program'])
    final = json.loads(completed['program'])
    assert completed['rounds'] == 2

    alternatives = [
        [['scourge_strike'], ['outbreak'], ['death_coil']],
        [['death_coil'], ['scourge_strike'], ['outbreak']],
        [['outbreak', 'death_coil'], ['scourge_strike']],
    ]
    distinct = next(program for program in alternatives if program not in (initial, final))

    def shared_program(program):
        nodes = []
        for segment in program:
            if isinstance(segment, list):
                nodes.append(dict(kind='Action', commands=[
                    dict(kind='spell', simc_action=action) for action in segment]))
            elif isinstance(segment, dict) and segment.get('kind') == 'CastSequence':
                nodes.append(dict(kind='Action', commands=[dict(
                    kind='castsequence', members=segment['members'], reset=segment.get('reset'))]))
            elif isinstance(segment, dict) and segment.get('kind') == 'Loop':
                nodes.append(dict(kind='Loop', step_function='Sequential', count=segment['count'],
                    body=[dict(kind='Action', commands=[dict(kind='spell', simc_action=action)
                           for action in block]) for block in segment['blocks']]))
            elif isinstance(segment, dict) and segment.get('kind') == 'WaitClicks':
                nodes.append(dict(kind='Pause', duration_ms=None, clicks=segment['clicks']))
            else:
                raise AssertionError(f'训练产物有未覆盖的搜索结构: {segment!r}')
        return dict(adapter='search', metadata={}, nodes=nodes)

    history = [
        ('history-final', final),
        ('history-new', distinct),
    ]
    for run_id, program in history:
        data_key = run_id + '-candidate'
        result_store.write('runs', run_id, [dict(dict.fromkeys(result_store.RUN_SCHEMA),
            run_id=run_id, status='completed',
            profile={'identity': {'class': 'deathknight', 'spec': 'unholy'}},
            candidate_data_key=data_key, search_dps=90.)], schema=result_store.RUN_SCHEMA)
        result_store.write('candidates', data_key, [dict(dict.fromkeys(result_store.CANDIDATE_SCHEMA),
            run_id=run_id, candidate_key=run_id, candidate_data_key=data_key, source='search',
            program=shared_program(program))], schema=result_store.CANDIDATE_SCHEMA)

    with training_boundary():
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    processed = json.loads(capsys.readouterr().out.splitlines()[-1])
    history_rows = [row for row in processed if row['family'] == 'history-search']
    duplicate = next(row for row in history_rows if json.loads(row['initial_program']) == final)
    new_candidate = next(row for row in history_rows if json.loads(row['initial_program']) == distinct)
    assert duplicate['status'] == 'rejected'
    assert '相同行为候选:' in duplicate['error']
    assert new_candidate['status'] == 'completed'
    assert result_store.read_records('runs', 'history-final')
    assert result_store.read_records('candidates', 'history-final-candidate')


def test_normal_search_keeps_four_original_starts_and_reads_one_legal_snapshot(tmp_path, monkeypatch):
    from test_character_export import sample_profile
    from test_search import _fast_search_boundary
    from task import run_task
    from unittest.mock import patch
    import result_store

    template = tmp_path / 'role.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    engines = {mode: dict(mode=mode, upstream_commit='test', build_options=[])
               for mode in ('baseline', 'controlled')}
    accepted = [
        ['outbreak'], ['death_coil'], ['scourge_strike'], ['dark_transformation'], ['outbreak']]
    additional = [accepted,
                  [['scourge_strike'], ['dark_transformation'], ['outbreak'], ['death_coil'], ['scourge_strike']],
                  [['death_coil'], ['dark_transformation'], ['scourge_strike'], ['outbreak'], ['death_coil']],
                  [['dark_transformation'], ['scourge_strike'], ['death_coil'], ['outbreak'], ['dark_transformation']],
                  [['outbreak'], ['scourge_strike'], ['dark_transformation'], ['death_coil'], ['outbreak']]]
    changed_after_start = [['death_coil'], ['outbreak'], ['death_coil'], ['outbreak'], ['death_coil']]
    rows = [
        *[dict(candidate_id=f'valid-{index}', condition='condition', class_name='deathknight', spec='unholy',
               targets=1, program=program, family='community', score=100. - index,
               scores=[100. - index] * 3, template_sha256='template', engines=engines)
          for index, program in enumerate(additional)],
        dict(candidate_id='illegal', condition='condition', class_name='deathknight', spec='unholy',
             targets=1, program=[['not_a_character_action']], family='community', score=99.,
             scores=[99., 99., 99.], template_sha256='template', engines=engines),
        dict(candidate_id='oversized', condition='condition', class_name='deathknight', spec='unholy',
             targets=1, program=[['outbreak'] * 40], family='community', score=98.5,
             scores=[98.5, 98.5, 98.5], template_sha256='template', engines=engines),
        dict(candidate_id='wrong-targets', condition='condition', class_name='deathknight', spec='unholy',
             targets=5, program=changed_after_start, family='community', score=98.,
             scores=[98., 98., 98.], template_sha256='template', engines=engines),
    ]
    result_store.write('seed_selected', 'deathknight-unholy-1', rows,
                       schema=__import__('seed_training').SELECTED_SCHEMA)
    real_read = result_store.read_records
    selected_reads = []

    def changing_snapshot(table, key):
        if table == 'seed_selected':
            selected_reads.append((table, key))
            return rows if len(selected_reads) == 1 else [dict(rows[0], program=changed_after_start)]
        return real_read(table, key)

    config = dict(total_budget_seconds=60, search_budget_seconds=10, candidate_limit=8,
                  round_candidate_limit=1, batch_targets=(2,), validation_batches=2,
                  final_batches=1, iterations=2, final_iterations=2,
                  scenarios=('nominal',), max_processes=1)
    with _fast_search_boundary(), patch.object(result_store, 'read_records', side_effect=changing_snapshot):
        result = run_task(template, tmp_path / 'normal-search', search_config=config)

    assert result['status'] == 'completed'
    starts = result['search']['starts']
    assert len(starts) == 8
    assert starts[-4:] == additional[:4]
    assert additional[4] not in starts
    assert changed_after_start not in starts
    assert [['outbreak'] * 40] not in starts
    assert len(selected_reads) == 1


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


def test_foreground_search_does_not_wait_for_training_and_stops_it(tmp_path):
    import os
    import subprocess
    import sys
    import time
    from seed_activity import training_activity
    import seed_activity

    root = str(tmp_path)
    module_dir = str(Path(seed_activity.__file__).parent)
    code = '\n'.join((
        'import sys,time',
        'sys.path.insert(0, ' + repr(module_dir) + ')',
        'import result_store',
        'result_store.bind_project(' + repr(root) + ')',
        'from seed_activity import foreground_search',
        'with foreground_search():',
        '    time.sleep(0.3)',
    ))
    environment = os.environ.copy()
    started = time.monotonic()
    with training_activity(poll_seconds=0.01) as cancel_event:
        child = subprocess.Popen([sys.executable, '-c', code], cwd=str(Path(seed_activity.__file__).parents[2]),
                                 env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            _, error = child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            raise AssertionError('普通搜索被训练等待')
        assert child.returncode == 0, error.decode(errors='replace')
        assert time.monotonic() - started < 2
        assert cancel_event.wait(0.3)


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


def test_connected_public_search_creates_data_root_on_first_run(tmp_path, monkeypatch):
    from test_character_export import sample_profile
    from test_search import _fast_search_boundary
    from task import run_task
    import result_store

    data_root = tmp_path / 'first-run-center' / 'data'
    monkeypatch.setattr(result_store, 'DATA_ROOT', data_root)
    template = tmp_path / 'role.simc'
    template.write_text(sample_profile(), encoding='utf-8')
    config = dict(total_budget_seconds=60, search_budget_seconds=10, candidate_limit=2,
                  round_candidate_limit=1, batch_targets=(2,), validation_batches=2,
                  final_batches=1, iterations=2, final_iterations=2,
                  scenarios=('nominal',), max_processes=1)

    assert not data_root.exists()
    with _fast_search_boundary():
        result = run_task(template, tmp_path / 'first-run-task', search_config=config)

    assert result['status'] == 'completed'
    assert data_root.is_dir()
    assert (data_root / '.seed-activity').is_dir()


@pytest.mark.parametrize('case', ['structured', 'history-only', 'changed-definition', 'empty', 'single-member', 'unknown', 'invalid-block', 'invalid-program'])
def test_training_entry_adapts_burst_sources_and_history_without_rewriting_them(tmp_path, capsys, monkeypatch, case):
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
    assert result_store.read_records('seed_candidates', 'registry') == source_before
    assert result_store.read_records('candidates', 'historical-program') == history_before
    monkeypatch.undo()
    assert (engine.reference, engine.inspect) == entrypoints
