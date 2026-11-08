"""搜索语法配置通过公开任务和编译入口生效。"""
from io import BytesIO
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'projects' / 'sim2gse'))

SIMPLE = dict(multi_command_blocks=False, loop=False, wait_clicks=False, castsequence=False)


def test_search_configuration_overlays_only_explicit_syntax_keys():
    from simulation_config import load_search_config
    document = ('[syntax]\n' + '\n'.join(f'{key}=false' for key in SIMPLE)).encode()
    config = load_search_config(BytesIO(document), syntax_config={'loop': False})
    assert config['syntax'] == SIMPLE
    config = load_search_config(BytesIO(document), syntax_config={'loop': True})
    assert config['syntax'] == dict(SIMPLE, loop=True)
    for invalid in (None, {'loop': None}, {'looop': False}, {'loop': 0}):
        with pytest.raises(ValueError):
            load_search_config(BytesIO(document), syntax_config=invalid)


def test_single_task_preserves_nested_policy_and_rejects_duplicate_authority():
    import task
    with patch('result_store.ensure_available', side_effect=AssertionError('不应访问存储')):
        with pytest.raises(ValueError, match='multi_command_blocks'):
            task.run_task('/memory/profile', '/memory/task', mode='single',
                          program=[['a', 'b']], search_config={'syntax': SIMPLE})
        with pytest.raises(ValueError, match='重复'):
            task.run_task('/memory/profile', '/memory/task', mode='single',
                          program=[['a']], search_config={'syntax': SIMPLE}, syntax_config=SIMPLE)


def test_resume_compares_only_explicit_syntax_keys_and_rejects_missing_policy():
    from search import config_for, resume_config_for
    saved = config_for({'syntax': SIMPLE})
    assert resume_config_for(saved, {'syntax': {'loop': False}})['syntax'] == SIMPLE
    with pytest.raises(ValueError, match='恢复|语法'):
        resume_config_for(saved, {'syntax': {'loop': True}})
    saved.pop('syntax')
    with pytest.raises(ValueError, match='语法|新任务'):
        resume_config_for(saved)


def test_training_rejects_invalid_shared_policy_before_reading_materials():
    import seed_training
    with patch.object(seed_training, 'sync_history', side_effect=AssertionError('不得读取材料')):
        with pytest.raises(ValueError, match='语法|syntax'):
            seed_training.run_training('/memory/template', 1, '/memory/training',
                                       syntax_config={'loop': 1})


def test_simple_mutation_reaches_single_edits_and_targeted_feedback_stays_in_scope():
    from itertools import product
    import random
    from search import mutate
    from program import check_search_syntax
    from test_search import _fast_capabilities
    caps = _fast_capabilities()
    caps['actions'] = caps['actions'][:2]
    caps['search_syntax'] = SIMPLE
    names = ('outbreak', 'death_coil')
    operations = set()
    for size in range(1,5):
        for words in product(names, repeat=size):
            parent = [[name] for name in words]
            reached = set()
            for seed in range(1500):
                detail = {}
                child = mutate(parent,caps,random.Random(seed),observation=detail,
                    feedback=dict(positions=[dict(source_position=dict(segment=0),unresolved_inputs=1)]))
                check_search_syntax(child,SIMPLE)
                operations.add(detail['actual_mutation'])
                reached.add(tuple(block[0] for block in child))
            # 独立列举每个位置的替换、首尾及中间插入、删除目标。
            expected = {words[:i]+(name,)+words[i+1:] for i in range(size) for name in names}
            expected |= {words[:i]+(name,)+words[i:] for i in range(size+1) for name in names}
            if size>1: expected |= {words[:i]+words[i+1:] for i in range(size)}
            assert expected-{words} <= reached
    assert {'replace','insert','delete','move','swap'} <= operations
    assert not operations & {'block','loop','wait_clicks','castsequence'}


@pytest.mark.parametrize('program,key', [
    ([['a', 'b']], 'multi_command_blocks'),
    ([dict(kind='Loop', count=2, blocks=[['a']])], 'loop'),
    ([dict(kind='WaitClicks', clicks=2)], 'wait_clicks'),
    ([dict(kind='CastSequence', members=['a', 'b'], reset=None)], 'castsequence'),
])
def test_single_task_rejects_forbidden_syntax_before_storage_or_native(program, key):
    import task
    with patch('result_store.ensure_available', side_effect=AssertionError('不应访问存储')), \
            pytest.raises(ValueError, match=key):
        task.run_task('/memory/character.simc', '/memory/task', mode='single',
                      program=program, syntax_config=SIMPLE)


def test_search_program_binds_one_base_button_without_expanding_variants():
    from program import from_search_program
    base = dict(kind='spell', spell_id=85948, base_spell_id=85948,
                simc_action='festering_strike', name='Festering Strike', gcd_ms=1500)
    variant = dict(base, spell_id=458128, simc_action='festering_scythe', name='Festering Scythe')
    capabilities = dict(actions=[dict(base, variants=[base, variant])], precombat_actions=[],
                        search_syntax=SIMPLE)
    result = from_search_program([['festering_strike']], capabilities)
    assert len(result['nodes']) == 1
    assert result['nodes'][0]['commands'] == [base]
    # 原全开放路径仍保留原来的形态展开能力。
    capabilities.pop('search_syntax')
    assert len(from_search_program([['festering_strike']], capabilities)['nodes'][0]['commands']) == 2


@pytest.mark.real
def test_single_button_variants_really_export_as_one_gse_step(tmp_path):
    from program import from_search_program, compile_program
    from sequence import compiled_program
    base = dict(kind='spell', spell_id=85948, base_spell_id=85948,
                simc_action='festering_strike', name='Festering Strike', gcd_ms=1500)
    variant = dict(base, spell_id=458128, simc_action='festering_scythe', name='Festering Scythe')
    capabilities = dict(actions=[dict(base, variants=[base, variant])], precombat_actions=[],
                        search_syntax=SIMPLE)
    exported = compile_program(from_search_program([['festering_strike']] * 2, capabilities),
                               tmp_path / 'export', identity=dict(class_id=6, spec_id=252),
                               capabilities=capabilities)
    assert [step['spell'] for step in exported['compiled_steps']] == [85948, 85948]
    assert compiled_program(exported) == [['festering_strike'], ['festering_strike']]
