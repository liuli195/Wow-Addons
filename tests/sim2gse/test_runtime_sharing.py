"""从训练和正式任务入口观察评分资料的复用及隔离。"""
import pytest

from test_population_training import memory_ga
from test_seed_training import training_cli, prepared_input, public_training_memory
from test_search import public_formal_memory


@pytest.mark.parametrize(('entry', 'targets'), [('training', 1), ('formal', 1), ('formal', 5)])
def test_public_runs_reuse_frozen_click_values_but_keep_request_lists_independent(
        request, monkeypatch, entry, targets):
    import sequence
    case = request.getfixturevalue('public_training_memory' if entry == 'training' else 'public_formal_memory')
    evaluate = sequence.evaluate
    observed = []
    def capture(*args, **kwargs):
        observed.append((kwargs['seed'], kwargs['input_times']))
        return evaluate(*args, **kwargs)
    monkeypatch.setattr(sequence, 'evaluate', capture)
    if entry == 'training':
        from seed_training import run_training
        result = run_training(case.template, targets, '/memory/work')
    else:
        from task import run_task
        result = run_task('/memory/role.simc', '/memory/formal',
            simulation_config=dict(target_count=targets, scene='single_target' if targets == 1 else 'aoe'))
    assert result['status'] == 'completed'
    previous = {}
    reused = 0
    for seed, times in observed:
        assert type(times) is list
        key = (seed, tuple(times))
        if key in previous:
            assert times is not previous[key]
            assert times[10] is previous[key][10]
            reused += 1
        previous[key] = times
    assert reused > 0
