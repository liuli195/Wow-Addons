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
