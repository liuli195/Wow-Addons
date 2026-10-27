"""正式实际人数、独立配置与限制锦标赛替换；复用公开优化器内存夹具。"""
from copy import deepcopy
import pytest
from test_population_training import memory_ga


@pytest.mark.parametrize('count,window', [(9, 6), (10, 7), (13, 9), (15, 10)])
def test_formal_freezes_actual_population_and_rtr_window(memory_ga, count, window):
    programs = [[['outbreak'], dict(kind='WaitClicks', clicks=i + 2), ['death_coil']]
                for i in range(count)]
    case = memory_ga(formal=True, programs=programs + [programs[0]], search_settings=dict(
        crossover_probability=0., mutation_probability=0., stagnation_generations=1))
    result = case.run()
    assert result['search']['effective_population_size'] == count
    assert result['search']['rtr_window_size'] == window
    assert result['search']['formal_search']['version'] == 3
    assert len(result['final']['scenarios']['nominal']['finalists']) == 8
    assert case.store.state['ga']['rtr_window_size'] == window
    from interface import _public_state
    public = _public_state(result, case.store.destination)
    assert public['search_metrics']['effective_population_size'] == count
    assert public['search_metrics']['rtr_window_size'] == window
    previous = deepcopy(case.store.state['ga'])
    calls = len(case.calls)
    assert case.run()['selected_candidate_key'] == result['selected_candidate_key']
    assert len(case.calls) == calls
    for key in ('population', 'generation', 'rng', 'finalists', 'rtr_window_size'):
        assert case.store.state['ga'][key] == previous[key]


def test_formal_weights_and_window_are_independent_and_validated():
    from io import StringIO
    from simulation_config import load_training_config, load_search_config
    training = load_training_config(StringIO('[training]\ntop_k=10\nbehavior_alpha=0.2'))
    formal = load_search_config(StringIO('[training]\ntop_k=10\nbehavior_alpha=0.2'))
    assert training['top_k'] == 10 and training['behavior_alpha'] == .2
    assert formal['top_k'] == 8 and formal['behavior_alpha'] == .5
    assert formal['rtr_window_ratio'] == .66 and formal['tournament_size'] == 3
    from search import config_for
    for key, values in [('rtr_window_ratio', [0, -1, 1.1, True, float('nan')]),
                        ('behavior_alpha', [-1, 1.1, True, float('inf')])]:
        for value in values:
            with pytest.raises(ValueError, match=key):
                config_for({key: value})


@pytest.mark.parametrize('count', [4, 6, 10])
def test_v3_snapshot_reads_actual_complete_publication(count):
    from seed_training import selected_contract_version
    rows = [dict(contract_version=3, candidate_id=str(i), evaluation=dict(
        publication=dict(count=count, top_k=10, min_publish=4))) for i in range(count)]
    assert selected_contract_version(rows) == 3
    with pytest.raises(ValueError, match='完整|人数|发布'):
        selected_contract_version(rows[:-1])


@pytest.mark.parametrize('count', [6, 10])
def test_current_character_assembly_consumes_every_published_program(memory_ga, count):
    from task import _assemble_formal_starts
    from runtime import TaskRuntime
    case = memory_ga(formal=True, search_settings=dict(crossover_probability=0., mutation_probability=0.,
                                                      stagnation_generations=1))
    configuration = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')
    rows = [dict(contract_version=3, configuration_key=configuration, candidate_id=str(i),
        class_name=case.character.class_name, spec=case.character.spec,
        program=[['outbreak'], dict(kind='WaitClicks', clicks=i + 2), ['death_coil']],
        evaluation=dict(publication=dict(count=count, top_k=10, min_publish=4))) for i in range(count)]
    case.store.state.update(simulation_config=case.ready['simulation_config'], seed_selected_snapshot=rows,
                            formal_champion_snapshot=dict(status='absent'))
    _assemble_formal_starts(case.store.state, [rows[0]['program'], [['scourge_strike']]],
        character=case.character, configuration_key=configuration, capabilities=case.capabilities,
        runtime=TaskRuntime(float('inf')), use_burst=False)
    assert len(case.store.state['seed_adaptations']) == count
    assert len(case.store.state['starts']) == count + 1
    result = case.run()
    assert result['search']['effective_population_size'] == count + 1


@pytest.mark.parametrize('version', [2, 3])
def test_public_result_reads_frozen_formal_versions(monkeypatch, version):
    from pathlib import Path
    import json
    import result_store
    from formal_search import contract_for
    from search import config_for, DEFAULT_CONFIG
    from task import read_task
    config = config_for()
    if version == 2:
        config.pop('behavior_alpha')
        config.pop('rtr_window_ratio')
    frozen = contract_for(config, version=version)
    saved = dict.fromkeys(result_store.RUN_SCHEMA)
    saved.update(status='completed', phase='done', config=config, batch_keys=[], search_rounds=8,
        search_metrics=dict(formal_search=frozen, effective_population_size=15, rtr_window_size=10))
    monkeypatch.setattr(Path, 'is_file', lambda p: p.name == 'result.json')
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: json.dumps(dict(run_id='saved-run')))
    monkeypatch.setattr(result_store, 'one', lambda *a, **kw: deepcopy(saved))
    monkeypatch.setitem(DEFAULT_CONFIG, 'behavior_alpha', .1)
    monkeypatch.setitem(DEFAULT_CONFIG, 'top_k', 20)
    result = read_task('/memory/saved-run')
    assert result['search']['formal_search'] == frozen
    assert result['search']['effective_population_size'] == 15
    assert result['search']['rtr_window_size'] == 10


@pytest.mark.parametrize('child_quality', [160., 150.])
def test_rtr_children_compete_in_frozen_order_against_updated_survivors(memory_ga, child_quality):
    import engine
    from test_search import _fast_report
    from runtime import TaskCancelled
    names = ['outbreak', 'death_coil', 'scourge_strike', 'dark_transformation']
    frequencies = [0., 100., 20., 55.]
    qualities = [100., 200., 150., child_quality]
    def native(profile, candidate, folder, **options):
        index = names.index(candidate['blocks'][0][0]['simc_action'])
        report = _fast_report(options['character'], qualities[index], options['iterations'] - 1)
        for row in report['sim']['players'][0]['stats']:
            row['num_executes']['mean'] = 0.
        report['sim']['players'][0]['stats'][0]['num_executes']['mean'] = frequencies[index]
        return dict(report=report, trace=[], summary=engine.check_report(report, options['character'],
            options['iterations'], simulation_config=options['simulation_config']))
    case = memory_ga(formal=True, programs=[[[name]] for name in names[:2]], native=native,
        search_settings=dict(crossover_probability=0., mutation_probability=0., stagnation_generations=1))
    case.run()
    ga = case.store.state['ga']
    ga.update(phase='breed', generation=0, stagnant=0, finals={},
        pending=dict(programs=[[[name]] for name in names[2:]], parent_slots=[0, 1],
                     regenerations=[0, 0], rng=deepcopy(ga['rng']), windows=[[0, 1], [0, 1]]))
    original = deepcopy(ga['population'])
    checkpoint = case.store.checkpoint
    def stop_after_commit():
        checkpoint()
        if ga['generation'] == 1:
            raise TaskCancelled('complete generation committed')
    case.store.checkpoint = stop_after_commit
    with pytest.raises(TaskCancelled, match='complete generation'):
        case.run()
    # Second child sees child one's new frequency; equal quality keeps child one.
    assert ga['population'][0]['program'] == [[names[3 if child_quality > 150 else 2]]]
    assert ga['population'][1] == original[1]
    assert ga['pending'] is None


def test_formal_progress_and_saved_result_keep_frozen_population(memory_ga, monkeypatch):
    import json
    from pathlib import Path
    import search
    import result_store
    import task
    from interface import _public_state
    case = memory_ga(formal=True, search_settings=dict(crossover_probability=0., mutation_probability=0.,
                                                      stagnation_generations=1))
    result = case.run()
    progress = []
    case.store.state.update(elapsed_seconds=0., status='running')
    monkeypatch.setattr(Path, 'write_text', lambda self, value, **kw: progress.append(json.loads(value)))
    monkeypatch.setattr(search, 'replace_file', lambda *a: None)
    case.store.publish()
    public = _public_state(progress[-1], case.store.destination)
    assert public['search_metrics']['effective_population_size'] == 6
    assert public['search_metrics']['rtr_window_size'] == 4
    stored = {}
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: json.dumps(dict(run_id='memory')))
    monkeypatch.setattr(Path, 'read_bytes', lambda *a: b'fixed-input')
    monkeypatch.setattr(result_store, 'write', lambda table, key, rows, **kw: stored.update({table: deepcopy(rows)}))
    task._store_run(case.store.destination, result, state=case.store.state)
    assert stored['runs'][0]['search_metrics']['rtr_window_size'] == 4
