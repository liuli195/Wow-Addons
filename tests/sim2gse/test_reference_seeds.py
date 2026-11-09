"""Reference refresh is exercised through the material command."""
import json

import pytest
from test_seed_training import prepared_input


def test_refresh_preflight_lists_four_scopes_without_native_or_publication(monkeypatch, capsys):
    import result_store
    import seed_training as seeds
    monkeypatch.setattr(result_store, 'bind_project', lambda path: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(seeds, 'registry_rows', lambda: [])
    monkeypatch.setattr(seeds, 'check_training', lambda **kw: dict(status='ready', groups=[
        dict(configuration_key=dict(specialization_id=252, hero_talent=hero,
                                    target_type='single_target' if targets == 1 else 'aoe'))
        for hero in ('rider_of_the_apocalypse', 'sanlayn') for targets in (1, 5)]))
    monkeypatch.setattr(result_store, 'write', lambda *a, **kw: pytest.fail('preflight must not publish'))
    assert seeds.main(['--project', '/memory', 'refresh-references', '--workspace', '/memory/run',
                       '--simc-only', '--check-only']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'preflight'
    assert result['target'] == 30
    assert len(result['groups']) == 4
    assert result['native_starts'] == 0 and result['published'] is False


def test_preparation_filters_new_sources_by_actual_group_before_dedup(prepared_input):
    import seed_training as seeds
    shared = prepared_input.source('legacy', [['outbreak']])
    other = prepared_input.source('other', [['death_coil']])
    other['allowed_groups'] = [dict(specialization_id=252, hero_talent='sanlayn',
                                    target_type='single_target', target_count=1)]
    ready = seeds.ensure_prepared('/profile', 1, '/memory', sources=[shared, other],
                                  inputs=prepared_input.inputs)
    assert [row['source_id'] for row in ready['entries']] == ['legacy']


def test_weighted_generator_matches_frozen_legacy_output_and_resumes():
    import hashlib
    import random
    from weighted_seeds import generate
    capabilities = dict(actions=[dict(kind='spell', spell_id=i, simc_action=name)
                                for i, name in ((1, 'a'), (2, 'b'))], precombat_actions=[0] * 121)
    reference = dict(successes={'spell:1': 3, 'spell:2': 1})
    rng = random.Random(20261110)
    state = generate(capabilities, reference, rng, count=32, excluded=set(),
                     legal=lambda p: json.dumps(p), check=lambda: None)
    assert len(state['programs']) == 32
    assert state['attempts'] == 41 and state['duplicates'] == 9
    assert hashlib.sha256(json.dumps(state['programs'], sort_keys=True).encode()).hexdigest() == '4c487877f77493565180ec167da80fd8f041756601268c8b329fb807af22fb26'
    assert hashlib.sha256(repr(rng.getstate()).encode()).hexdigest() == '84ffeb133154d382ce0c0a31e4c7c7b367700442f58b412d211e445e56ed801f'
    saved = {}
    def checkpoint(progress):
        saved.update(json.loads(json.dumps(progress)))
        if progress['attempts'] == 9:
            raise InterruptedError('cancel')
    with pytest.raises(InterruptedError):
        generate(capabilities, reference, random.Random(20261110), count=32, excluded=set(),
                 legal=lambda p: json.dumps(p), check=lambda: None, checkpoint=checkpoint)
    resumed = generate(capabilities, reference, random.Random(0), count=32, excluded=set(),
                       legal=lambda p: json.dumps(p), check=lambda: None, progress=saved)
    assert resumed['programs'] == state['programs'] and resumed['attempts'] == 41


def test_explicit_other_group_material_is_rejected(prepared_input):
    import seed_training as seeds
    row = prepared_input.source('other', [['outbreak']])
    row['allowed_groups'] = [dict(specialization_id=252, hero_talent='sanlayn',
                                 target_type='single_target', target_count=1)]
    with pytest.raises(ValueError, match='适用范围'):
        seeds.ensure_prepared('/profile', 1, '/memory', sources=[row], materials=[row],
                              inputs=prepared_input.inputs)


@pytest.mark.real
def test_refresh_command_recovers_storage_failure_and_rejects_drift_corruption_and_exhaustion(
        tmp_path, monkeypatch, capsys, prepared_input):
    """Use the real command/preparer; only filesystem/catalogue/storage boundaries are supplied."""
    import burst
    import engine
    import result_store
    import seed_training as seeds
    import simulation_config
    from search import digest
    from pathlib import Path
    root = tmp_path / 'refresh'
    template = tmp_path / 'role.simc'
    template.write_text(prepared_input.inputs['text'], encoding='utf-8')
    config = tmp_path / 'config.toml'
    original_config = ('[training]\nreference_seed_mode="weighted-v1"\nreference_seed_target=3\n'
        '[syntax]\nmulti_command_blocks=false\nloop=false\nwait_clicks=false\ncastsequence=false\n')
    config.write_text(original_config, encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    monkeypatch.setattr(engine, 'identity', lambda mode: (Path('/fake-engine'), {'mode': mode}))
    monkeypatch.setattr(burst, 'load', lambda spec: dict(spec_id=252))
    monkeypatch.setattr(burst, 'select_definition', lambda character: None)
    inputs = seeds._training_inputs(template, 1, use_burst=True)
    key = digest(dict(version=seeds.PREPARATION_VERSION, template=inputs['template_sha'],
        engines=inputs['engines'], simulation=inputs['simulation_config'], definition=None,
        semantics=seeds.semantic_versions(), config=seeds._identity_config(inputs['config'])))
    header = prepared_input.header
    header['config_key'] = key
    native = header['context']['native']
    native.update(samples=1, action_summary=dict(version=1, samples=1, duration_ms=180000,
        successes={'spell:1001': 1}, pairs={}, outgoing={}, positions={}, witnesses={},
        scope=dict(allowed={'spell:1001': True}, excluded={}, windows='none', policy='fixture', controlled=False)))
    header['checksum'] = digest([{k: v for k, v in header.items() if k != 'checksum'}])
    source = prepared_input.source('old', [['outbreak']])
    source['source_id'] = 'manual:simc-sanlayn-a1-20261012'
    monkeypatch.setattr(seeds, 'registry_rows', lambda: [source])
    monkeypatch.setattr(seeds, 'check_training', lambda **kw: dict(groups=[dict(template=str(template),
        configuration_key=dict(specialization_id=252, hero_talent='rider_of_the_apocalypse',
                               target_type='single_target'))]))
    monkeypatch.setattr(result_store, 'bind_project', lambda path: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    writes = []
    def store_write(table, key, rows, **kw):
        assert table != 'seed_candidates', 'preparation cannot publish the registry'
        writes.append(table)
        if table == 'seed_prepared' and writes.count('seed_prepared') == 2:
            raise OSError('constructed write failure')
    monkeypatch.setattr(result_store, 'write', store_write)
    arguments = ['--project', str(tmp_path), 'refresh-references', '--workspace', str(root), '--simc-only']
    assert seeds.main(arguments) == 2
    assert 'constructed write failure' in capsys.readouterr().err
    plan_path = root / 'plan.json'
    paused = json.loads(plan_path.read_text(encoding='utf-8'))
    assert paused['status'] == 'paused' and len(paused['groups'][0]['generation']['programs']) == 2
    assert seeds.main(arguments) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed['status'] == 'simc_prepared' and completed['groups'][0]['simc_behaviors'] == 3
    assert [r['program'] for r in completed['generated']] == paused['groups'][0]['generation']['programs']
    assert completed['requested_iterations'] == paused['requested_iterations'] == 0
    assert result_store.DATA_ROOT != root / 'data'
    config.write_text(original_config.replace('loop=false', 'loop=true'), encoding='utf-8')
    assert seeds.main(arguments) == 2
    assert '配置' in capsys.readouterr().err
    config.write_text(original_config, encoding='utf-8')
    plan_path.write_text(json.dumps(dict(completed, checksum='broken')), encoding='utf-8')
    assert seeds.main(arguments) == 2
    assert '校验损坏' in capsys.readouterr().err
    completed.update(status='paused', used_seconds=300)
    completed['groups'][0]['status'] = 'preparing'
    completed['checksum'] = digest({k: v for k, v in completed.items() if k != 'checksum'})
    plan_path.write_text(json.dumps(completed), encoding='utf-8')
    assert seeds.main(arguments) == 2
    assert '预算' in capsys.readouterr().err
