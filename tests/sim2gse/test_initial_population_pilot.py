"""The pilot is exercised through its actual command, never the production publisher."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'scripts/dev/sim2gse/initial_population_pilot.py'
PILOTS = ROOT / '.local/sim2gse/population-expansion-pilot'


def command(*arguments):
    return subprocess.run([sys.executable, str(CLI), *map(str, arguments)],
                          cwd=ROOT, text=True, capture_output=True, timeout=40)


@pytest.mark.real
def test_command_preflight_freezes_bounded_plan_without_running_native(installed_result_center):
    PILOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PILOTS) as folder:
        output = Path(folder) / 'run'
        result = command('--output', output, '--check-only')
        assert result.returncode == 0, result.stderr
        plan = json.loads(result.stdout)
        assert plan['status'] == 'preflight'
        assert plan['native_starts'] == 0
        assert plan['limits'] == dict(seconds=1800, native_starts=256, requested_iterations=6000)
        assert plan['groups'] == dict(new_starts=32, offspring_slots=32)
        assert plan['confirmation'] == dict(candidates_per_group=4, batches=2, iterations=32)
        assert plan['target_count'] == 1
        assert not any(plan['syntax'].values())
        assert not (output / 'report.json').exists()


@pytest.mark.real
def test_command_completes_isolated_comparison_with_locked_independent_confirmation(installed_result_center):
    PILOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PILOTS) as folder:
        output = Path(folder) / 'run'
        result = command('--output', output, '--native-adapter',
                         ROOT / 'tests/sim2gse/pilot_native_adapter.py')
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(result.stdout)
        assert report['status'] == 'completed'
        assert report['evidence_kind'] == 'constructed_native_boundary'
        assert report['published'] is False
        assert report['counts']['requested_iterations'] <= 6000
        assert report['counts']['native_starts'] <= 256
        assert report['baseline']['count'] == 6
        for name in ('new_starts', 'offspring'):
            group = report['groups'][name]
            assert group['slots'] == 32
            assert len(group['selected']) == 4
            assert group['locked'] == [row['identity'] for row in group['selected']]
            assert all(len(row['confirmation']) == 2 for row in group['selected'])
            assert all(row['samples'] == 62 for row in group['selected'])
        plan = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        search_seed = plan['stage_plan']['search']['seeds'][0]
        confirmations = plan['stage_plan']['nominal']['seeds']
        assert len(set([search_seed, *confirmations])) == 3
        assert not Path(report['data_root']).resolve().is_relative_to(ROOT / 'data')
        assert Path(report['data_root']).resolve() == Path(folder) / 'data'
        assert report['decision'] in ('positive_signal', 'defer', 'inconclusive')
        assert len(report['baseline']['independent']['batch_means']) == 2


@pytest.mark.real
def test_command_reports_incomplete_when_reference_or_scoring_cannot_fit_budget(installed_result_center):
    PILOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PILOTS) as folder:
        result = command('--output', Path(folder) / 'limited', '--max-requested-iterations', 1,
                         '--native-adapter', ROOT / 'tests/sim2gse/pilot_native_adapter.py')
        assert result.returncode == 2, result.stderr
        report = json.loads(result.stdout)
        assert report['status'] == 'incomplete'
        assert report['conclusion'] == '尚不能判断'
        assert report['published'] is False
        assert report['counts']['requested_iterations'] <= 1
        assert report['counts']['native_starts'] == 0
        assert 'BudgetExceeded' in report['error']


@pytest.mark.real
def test_command_deadline_stops_worker_without_publishing_partial_results(installed_result_center):
    PILOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PILOTS) as folder:
        result = command('--output', Path(folder) / 'timeout', '--max-wait-seconds', .05,
                         '--native-adapter', ROOT / 'tests/sim2gse/pilot_native_adapter.py')
        assert result.returncode == 2, result.stderr
        report = json.loads(result.stdout)
        assert report['status'] == 'incomplete'
        assert report['published'] is False


@pytest.mark.real
def test_command_refuses_production_output_or_unapproved_budget(installed_result_center):
    result = command('--output', ROOT / 'data', '--check-only')
    assert result.returncode == 2
    assert '输出必须在隔离探路目录' in result.stderr
    result = command('--output', PILOTS / 'unused', '--max-wait-seconds', 1801, '--check-only')
    assert result.returncode == 2
    assert '预算或种子超出' in result.stderr


def test_shared_variation_keeps_frozen_baseline_random_stream_and_children():
    """Oracle captured from 37a44b53's original gates, not from the new helper."""
    from copy import deepcopy
    import hashlib
    import random
    from deap import base
    from population_training import vary_offspring, _cross
    from program import canonicalize_search_program
    from test_search import _fast_capabilities
    capabilities = _fast_capabilities()
    reference = dict(version=1, samples=31, duration_ms=5580000, successes={'spell:1001': 31},
        pairs={}, outgoing={}, scope=dict(allowed={'spell:1001': True}, excluded={},
                                          windows='', policy='@apl', controlled=False))

    class Fitness(base.Fitness):
        weights = (1.,)

    class Member(list):
        pass

    outputs = []
    for seed in range(30):
        rng = random.Random(seed)
        toolbox = base.Toolbox()
        toolbox.register('clone', deepcopy)
        toolbox.register('mate', lambda a, b: _cross(a, b, rng))
        parents = []
        for program in ([['outbreak'], ['death_coil']], [['scourge_strike'], ['outbreak']]):
            member = Member(deepcopy(program))
            member.fitness = Fitness((100.,))
            member.action_summary = reference
            parents.append(member)
        counts = {route + suffix: 0 for route in ('target', 'random', 'crossover')
                  for suffix in ('_triggered', '_changed')}
        children = vary_offspring(parents, toolbox, rng=rng,
            config=dict(target_mutation_probability=.8, random_mutation_probability=.3, crossover_probability=.3),
            capabilities=capabilities, reference=reference,
            legal=lambda p: canonicalize_search_program(p, capabilities)['identity'],
            check=lambda: None, observe=lambda *a, **k: None, counts=counts)
        outputs.append(dict(children=[list(child) for child in children], rng=rng.getstate(), counts=counts))
    assert hashlib.sha256(json.dumps(outputs, sort_keys=True).encode()).hexdigest() == (
        '18c2223cfab8f5e99e77627a365db8c4da7dd3bdf55d3f68e4e110f7a8100750')


@pytest.mark.parametrize('key,value', [('coarse_iterations', 64), ('tournament_size', 2),
    ('target_mutation_probability', .7), ('random_mutation_probability', .2), ('crossover_probability', .4)])
def test_preflight_refuses_changed_experiment_parameters(monkeypatch, capsys, key, value):
    import runpy
    import simulation_config
    configuration = dict(simulation_config.TRAINING_DEFAULTS, **{key: value})
    monkeypatch.setattr(simulation_config, 'load_training_config', lambda: configuration)
    cli = runpy.run_path(str(CLI))
    with pytest.raises(SystemExit) as error:
        cli['main'](['--output', str(PILOTS / 'unused'), '--check-only'])
    assert error.value.code == 2
    assert '本次探路固定32次粗评' in capsys.readouterr().err
