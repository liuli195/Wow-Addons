"""Manual training command uses the existing installed data center."""
import json
from pathlib import Path


def test_cleaned_candidate_registration_is_reusable_and_rejects_missing_provenance(tmp_path, capsys):
    from seed_training import main
    import result_store

    source = tmp_path / 'cleaned.json'
    source.write_text(json.dumps(dict(label='ABC-C', spec='unholy', class_name='deathknight',
        source='plugin:Smolbreather', original='15 ordered spell ids',
        instructions='continuous unmodified key', semantic='rewritten',
        changes=['remove movement'], family='plugin-opener', core=[['putrefy'], ['death_coil']],
        program=[['outbreak'], ['putrefy'], ['death_coil']])), encoding='utf-8')
    assert main(['register', str(source)]) == 0
    capsys.readouterr()
    assert main(['register', str(source)]) == 0
    assert main(['list', '--state', 'pending']) == 0
    lines = capsys.readouterr().out.splitlines()
    candidates = json.loads(lines[-1])
    assert len(candidates) == 1
    assert candidates[0]['label'] == 'ABC-C'
    assert result_store.DATA_ROOT.joinpath('seed_candidates').is_dir()
    invalid = json.loads(source.read_text())
    invalid.pop('changes')
    source.write_text(json.dumps(invalid), encoding='utf-8')
    assert main(['register', str(source)]) != 0
    assert main(['list', '--state', 'pending']) == 0
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
    assert main(['register', str(source)]) == 0
    args = ['run', '--template', str(template), '--targets', '1', '--workspace', str(tmp_path / 'work')]
    real_write = result_store._api()['write']
    def failing_publish(root, table, key, rows, **kwargs):
        if table == 'seed_selected':
            raise PermissionError('发布目标暂时不可写')
        return real_write(root, table, key, rows, **kwargs)
    with _fast_search_boundary(), patch.dict(result_store._SKILL_API, write=failing_publish):
        assert main(args) == 2
    assert not result_store.read_records('seed_selected', 'deathknight-unholy-1')
    processed = result_store.read_records('seed_processed', 'deathknight-unholy-1')
    assert len(processed) == 1
    assert processed[0]['rounds'] == 5
    assert processed[0]['stop_reason'] == 'training_round_limit'
    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert main(args) == 0
    assert main(['list', '--state', 'selected', '--targets', '1']) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])
    with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=AssertionError('重复模拟')):
        assert main(args) == 0
