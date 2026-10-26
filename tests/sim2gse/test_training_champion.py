"""训练冠军选择和来源校验直接消费内存证据。"""
from copy import deepcopy
import pytest

from test_burst import reviewed_fixture


@pytest.fixture
def unchanged_offspring(monkeypatch):
    """曲线开关对照固定子代，只比较观测开关而不引入随机差异。"""
    import population_training
    monkeypatch.setattr(population_training, '_cross', lambda *args, **kwargs: False)
    monkeypatch.setattr(population_training, 'mutate', lambda program, *args, **kwargs: deepcopy(list(program)))
    yield


@pytest.mark.parametrize('legacy_search', [False, True])
@pytest.mark.parametrize('wrong_report_engine', [False, True])
def test_dual_rescores_training_champion_from_an_older_engine(monkeypatch, wrong_report_engine, legacy_search):
    from champion_evidence_fixture import training_history, read_training_history
    from task import _seed_programs
    from runtime import TaskRuntime
    history = training_history(monkeypatch, [([['outbreak'], ['death_coil'], ['outbreak']], [99999.] * 3)],
        report_engines=({'baseline': 'current', 'controlled': 'current'} if wrong_report_engine else None),
        legacy_search=legacy_search)
    before = deepcopy(history['rows'])
    champion = read_training_history(history)
    if wrong_report_engine:
        assert champion['status'] == 'absent'
        assert champion['excluded'][0]['status'] == 'invalid'
        assert '复测引擎' in champion['excluded'][0]['reason']
    else:
        assert champion['status'] == 'selected', champion
        assert champion['candidate_id'] == history['rows'][0]['candidate_id']
        assert champion['engines'] == history['inputs']['engines']
        assert champion['scores'] == [99999.] * 3
        starts, decisions = _seed_programs([], [champion], character=history['inputs']['character'],
            targets=1, configuration_key=history['configuration_key'],
            capabilities=next(iter(history['states'].values()))['capabilities'], runtime=TaskRuntime(600))
        assert starts == [history['rows'][0]['program']]
        assert decisions[0]['status'] == 'accepted'
        # 只交付当前角色程序，不带任何历史DPS作当前评分；此处不证明原生重评分。
        assert not any(isinstance(item, dict) and 'score' in item for item in starts)
    assert history['rows'] == before


@pytest.mark.parametrize('fault', ['wrong_program', 'report_missing', 'report_corrupt', 'temporary_error'])
def test_training_champion_rejects_invalid_final_evidence_and_reports_temporary_storage_errors(monkeypatch, fault):
    import result_store
    from champion_evidence_fixture import training_history, read_training_history
    history = training_history(monkeypatch, [([['outbreak']], [100.] * 3),
        ([['death_coil']], [200.] * 3)])
    high = history['rows'][1]
    key = next(iter(history['receipts'][high['candidate_id']]))
    if fault == 'wrong_program':
        history['receipts'][high['candidate_id']][key]['request']['program'] = {}
        history['refresh']()
    else:
        one = result_store.one
        def read_report(table, field, value, **kwargs):
            if value == key:
                if fault == 'report_missing': return None
                if fault == 'report_corrupt': raise result_store.InvalidRecordError('corrupt original report')
                raise OSError('temporary isolated storage failure')
            return one(table, field, value, **kwargs)
        monkeypatch.setattr(result_store, 'one', read_report)
    if fault == 'temporary_error':
        with pytest.raises(result_store.DataReadError, match='暂时不可读'):
            read_training_history(history)
        return
    champion = read_training_history(history)
    assert champion['candidate_id'] == history['rows'][0]['candidate_id']
    excluded = next(row for row in champion['excluded'] if row['candidate_id'] == high['candidate_id'])
    assert excluded['status'] == ('missing' if fault == 'report_missing' else 'invalid')


def test_dual_does_not_replace_an_inapplicable_highest_champion_with_second_place(monkeypatch):
    from champion_evidence_fixture import training_history, read_training_history
    from task import _seed_programs
    from runtime import TaskRuntime
    history = training_history(monkeypatch, [([['death_coil']], [100.] * 3),
        ([['outbreak']], [200.] * 3)])
    champion = read_training_history(history)
    capabilities = deepcopy(next(iter(history['states'].values()))['capabilities'])
    capabilities['actions'] = [action for action in capabilities['actions'] if action['simc_action'] != 'outbreak']
    capabilities['sources'].append(dict(catalogue='apl', status='native_unavailable',
        action_initialized=True, available=False, data_valid=True, data_id=1001,
        signature='outbreak', name='outbreak', gcd_ms=1500))
    starts, decisions = _seed_programs([], [champion], character=history['inputs']['character'], targets=1,
        configuration_key=history['configuration_key'], capabilities=capabilities, runtime=TaskRuntime(600))
    assert champion['candidate_id'] == history['rows'][1]['candidate_id']
    assert starts == []
    assert decisions[0]['status'] == 'rejected' and decisions[0]['reason']


@pytest.mark.parametrize('fault', ['processed_corrupt', 'processed_temporary'])
def test_dual_distinguishes_corrupt_training_records_from_temporary_read_failures(monkeypatch, fault):
    import result_store
    from champion_evidence_fixture import training_history, read_training_history
    history = training_history(monkeypatch, [([['outbreak']], [200.] * 3)])
    error = (result_store.InvalidRecordError('corrupt processed record') if fault == 'processed_corrupt'
             else result_store.DataReadError('temporary isolated processed storage error'))
    def unreadable(*args, **kwargs): raise error
    monkeypatch.setattr(result_store, 'read_records', unreadable)
    if fault == 'processed_temporary':
        with pytest.raises(result_store.DataReadError): read_training_history(history)
    else:
        snapshot = read_training_history(history)
        assert snapshot['status'] == 'absent' and snapshot['excluded'][0]['status'] == 'invalid'


def test_dual_seed_scope_is_exact_and_target_count_is_only_source_evidence():
    from task import _seed_programs
    from runtime import TaskRuntime
    from test_search import _fast_capabilities
    key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')
    rows = [dict(configuration_key=key, candidate_id=f'scope-{index}', condition='source-condition',
        class_name='deathknight', spec='unholy', targets=99,
        program=[['outbreak'], dict(kind='WaitClicks', clicks=index + 2), ['death_coil']],
        score=99999.) for index in range(5)]
    unknown = dict(rows[0], configuration_key=None, candidate_id='unknown')
    foreign = dict(rows[0], configuration_key=dict(key, hero_talent='other_hero'), candidate_id='other')
    original = deepcopy([unknown, foreign, *rows])
    character = __import__('task').parse_character(reviewed_fixture()[1])
    starts, decisions = _seed_programs([], [unknown, foreign, *rows], character=character, targets=1,
        configuration_key=key, capabilities=_fast_capabilities(), runtime=TaskRuntime(600))
    assert len(starts) == len(decisions) == 4
    assert [row['candidate_id'] for row in decisions] == ['scope-0', 'scope-1', 'scope-2', 'scope-3']
    assert all(row['status'] == 'accepted' for row in decisions)
    assert [unknown, foreign, *rows] == original
    aoe, _ = _seed_programs([], rows, character=character, targets=5,
        configuration_key=dict(key, target_type='aoe'), capabilities=_fast_capabilities(), runtime=TaskRuntime(600))
    assert aoe == []


@pytest.mark.parametrize('fault', ['source_rules', 'report_hero'])
def test_dual_rejects_unproved_training_hero_identity(monkeypatch, fault):
    from champion_evidence_fixture import training_history, read_training_history
    history = training_history(monkeypatch, [([['death_coil']], [200.] * 3)])
    if fault == 'source_rules':
        history['manifest']['rule_snapshot']['pack']['identity_mappings']['hero_talents']['rider_of_the_apocalypse'] = 999
        history['refresh']()
    else:
        for report in history['reports'].values():
            report['report']['sim']['players'][0]['sim2gse_static_snapshot']['hero_subtree_ids'] = [999]
    champion = read_training_history(history)
    assert champion['status'] == 'absent'
    assert champion['excluded'][0]['status'] == 'invalid'


@pytest.mark.parametrize('versions, expected', [([None], 1), ([1], 1), ([2] * 4, 2)])
def test_training_selected_snapshot_uses_explicit_contract_not_source_labels(versions, expected):
    import seed_training
    rows = [dict(contract_version=version, source_kind='ga') if version is not None else dict(source_kind='ga')
            for version in versions]
    assert seed_training.selected_contract_version(rows) == expected


@pytest.mark.parametrize('versions', [[2], [1, 2], [True], ['2'], [3]])
def test_training_selected_snapshot_rejects_mixed_unknown_or_incomplete_contracts(versions):
    import seed_training
    with pytest.raises(ValueError, match='契约版本|完整四条'):
        seed_training.selected_contract_version([dict(contract_version=version) for version in versions])
