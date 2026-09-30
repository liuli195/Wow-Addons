"""完整验收入口接受未独立复测的搜索结果。"""
import tempfile
from pathlib import Path
from unittest.mock import patch

import manual_search_task


def test_manual_acceptance_accepts_search_result_without_final_retest():
    result = dict(status="completed", candidate=dict(text="!GSE3!test",
                  game_validation="not_run", simulation="passed_native_model"),
                  search=dict(candidate_count=5, starts=[1, 2]),
                  final=dict(status="not_requested", scenarios={}),
                  independent_validation_complete=False, improvement="search_result",
                  search_result=dict(dps=100, reference_dps=120, reference_ratio=100/120),
                  elapsed_seconds=600, completed_batches=5)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / '.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc'
        source.parent.mkdir(parents=True)
        source.write_bytes(b"character")
        destination = root / "output"
        def run_task(profile, output):
            output.mkdir()
            (output / 'input.original.simc').write_bytes(profile.read_bytes())
            return result
        with patch.object(manual_search_task, 'ROOT', root), \
             patch.object(manual_search_task, 'run_task', run_task), \
             patch('sys.argv', ['manual_search_task.py', '--output', str(destination)]):
            manual_search_task.main()
        assert (destination / 'acceptance.json').exists()
