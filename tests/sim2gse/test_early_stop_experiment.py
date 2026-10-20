"""隔离MVP运行器通过真实任务入口比较早停，不改变产品默认。"""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from test_search import REPOSITORY, _guided_search_boundary, sample_profile
from test_rule_diagnostics import _observed_evaluate


def _runner():
    path = REPOSITORY / 'scripts/dev/sim2gse/sanlayn_four_case.py'
    spec = importlib.util.spec_from_file_location('sanlayn_experiment', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_progress_experiment_keeps_global_winner_and_stops_after_new_stagnation(tmp_path):
    import result_store
    import search
    from task import run_task

    starts = [
        [['outbreak'], ['scourge_strike'], ['epidemic'], ['death_coil']],
        [['outbreak'], ['scourge_strike'], ['death_coil']],
    ]

    def scored(profile, candidate, folder, **kwargs):
        result = _observed_evaluate(profile, candidate, folder, **kwargs)
        blocks = result['blocks']
        damage = (1000.0 if ['epidemic'] in blocks else
                  100.0 if blocks == starts[1] else 200.0)
        result['summary']['dps'] = damage
        result['report']['sim']['statistics']['raid_dps']['mean'] = damage
        result['report']['sim']['players'][0]['collected_data']['dps']['mean'] = damage
        (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result

    original = Path(search.__file__).read_text(encoding='utf-8')
    outcomes = {}
    for policy in ('on', 'route-progress'):
        directory = tmp_path / policy
        directory.mkdir()
        source = directory / 'role.simc'
        source.write_text(sample_profile(), encoding='utf-8')
        namespace = dict(search.__dict__)
        effective = _runner().experiment_source(original, policy)
        exec(compile(effective, search.__file__, 'exec'), namespace)
        with _guided_search_boundary(directory, starts, evaluate=scored), \
                patch.object(search, 'optimize', namespace['optimize']), \
                patch.object(result_store, 'DATA_ROOT', directory / 'center'):
            outcomes[policy] = run_task(source, directory / 'task', search_config=dict(
                input_interval_ms=200, candidate_limit=16, round_candidate_limit=1,
                batch_targets=(2,), iterations=2, validation_batches=2, max_processes=1))

    control, experiment = outcomes['on'], outcomes['route-progress']
    for result in (control, experiment):
        assert result['status'] == 'completed'
        assert result['search']['stop_reason'] == 'no_improvement'
        assert result['search']['no_improvement_round_limit'] == 2
        assert result['search_result']['dps'] == 1000.0
        assert result['search']['records'][0]['key'] == result['locked_candidate_key']
        records = {row['key']: row for row in result['search']['records']}
        assert records[result['search']['chains'][1]['best']]['score'] == 200.0
    assert control['search']['rounds'] == 2
    assert experiment['search']['rounds'] == 4
    assert Path(search.__file__).read_text(encoding='utf-8') == original
