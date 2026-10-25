"""既有手工CLI接受自然结束的完整nominal成果，不把半成品记成功。"""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import manual_search_task


def test_manual_acceptance_requires_natural_complete_nominal_retest():
    result = dict(status='completed', candidate=dict(text='!GSE3!test',
                  game_validation='not_run', simulation='passed_native_model'),
                  selected_candidate_key='winner', stop_policy=dict(version=1, kind='natural_stagnation'),
                  search=dict(candidate_count=1001, starts=[[['outbreak']]]),
                  final=dict(status='completed', scenarios=dict(nominal=dict(finalists=[dict(
                      key='winner', score=100., samples=381,
                      batches=[dict(requested_iterations=128, samples=127) for _ in range(3)])]))),
                  independent_validation_complete=True, improvement='search_result',
                  search_result=dict(dps=100., samples=381, reference_dps=120., reference_ratio=100/120),
                  elapsed_seconds=601, completed_batches=5)
    root = Path('unused-project')
    destination = root / 'output'
    with patch.object(manual_search_task, 'ROOT', root), \
            patch.object(manual_search_task, 'run_task', return_value=result) as run, \
            patch.object(Path, 'read_bytes', return_value=b'character'), \
            patch.object(Path, 'write_text', autospec=True) as write, \
            patch('sys.argv', ['manual_search_task.py', '--output', str(destination)]):
        manual_search_task.main()
        evidence = json.loads(write.call_args.args[1])
        assert write.call_args.args[0] == destination / 'acceptance.json'
        assert evidence['search_result'] == result['search_result']
        assert evidence['independently_tested'] is True
        assert evidence['scenarios'] == result['final']['scenarios']
        assert evidence['stop_policy'] == result['stop_policy']
        for fault in ('incomplete', 'missing_finalists'):
            broken = deepcopy(result)
            if fault == 'incomplete':
                broken['independent_validation_complete'] = False
            else:
                broken['final']['scenarios']['nominal']['finalists'] = []
            run.return_value = broken
            write.reset_mock()
            try:
                manual_search_task.main()
            except AssertionError:
                pass
            else:
                raise AssertionError('手工验收不得接受未完成正常复测: ' + fault)
            write.assert_not_called()
