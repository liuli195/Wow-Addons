"""Manual training command uses the existing installed data center."""
import json
from pathlib import Path
import subprocess
import sys

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
    return main(['--project', str(tmp_path), *args])


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


def test_training_command_publishes_five_rounds_and_reuses_completed_work(tmp_path, capsys):
    from seed_training import main
    from test_character_export import sample_profile
    from test_search import _fast_search_boundary
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
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    real_write = result_store.write
    def failing_publish(table, key, rows, **kwargs):
        if table == 'seed_selected':
            raise PermissionError('发布目标暂时不可写')
        return real_write(table, key, rows, **kwargs)
    with _fast_search_boundary(), patch.object(result_store, 'write', side_effect=failing_publish):
        assert command(tmp_path, args) == 2
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1')
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    assert len(processed) == 1
    assert processed[0]['rounds'] == 5
    assert processed[0]['stop_reason'] == 'training_round_limit'
    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'selected', '--targets', '1']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])
    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert command(tmp_path, args) == 0


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
    from test_search import _fast_search_boundary
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
    with _fast_search_boundary():
        assert command(tmp_path, args) == 0
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])[0]
    assert json.loads(first['initial_program']) == [['outbreak'], ['death_coil'], ['scourge_strike']]
    template.write_text(sample_profile() + '\n# new template revision\n', encoding='utf-8')
    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=ValueError('新条件重新计算')):
        assert command(tmp_path, args) == 2
    assert command(tmp_path, ['list', '--state', 'processed']) == 0
    rows = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert len({row['condition'] for row in rows}) == 2
    assert any(row['status'] == 'failed' for row in rows)


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
