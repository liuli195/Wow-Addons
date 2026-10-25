import json
import pytest
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.append(str(ROOT/"scripts/dev/sim2gse"))
from benchmark import SEEDS,materialize
class BenchmarkTests(TestCase):
 def test_product_rejects_missing_candidate_identity_and_incomplete_nominal(self):
  import benchmark
  new={'status':'completed','candidate':{'simulation':'passed_native_model','text':'!GSE3!test'},
       'search_result':{'dps':120,'samples':99},'native_reference':{'dps':150}}
  self.assertFalse(benchmark.extract_product(new)['evidence_complete'])
  old=dict(new,selected_candidate_key='winner',locked_candidate_key='winner')
  old.pop('search_result')
  old['final']={'scenarios':{'nominal':{'complete':False,'candidate':[{'samples':99}],
                  'comparison':{'candidate_mean_dps':120}}}}
  self.assertFalse(benchmark.extract_product(old)['evidence_complete'])
 def test_product_command_summarizes_without_requiring_five_final_scenarios(self):
     import benchmark
     with patch.object(Path, 'mkdir'), patch.object(Path, 'is_file', return_value=False), \
             patch.object(Path, 'write_text', autospec=True) as write, \
             patch('sys.argv', ['benchmark.py', '--run-id', 'product-smoke', '--product', '--summarize']):
         self.assertEqual(benchmark.main(), 0)
     report = json.loads(write.call_args.args[1])
     self.assertEqual(write.call_args.args[0].name, 'product-overview.json')
     self.assertEqual(report['status'], 'insufficient_evidence')
     self.assertEqual(len(report['pairs']), 3)
 def test_product_summary_uses_exported_nominal_and_side_budgets(self):
  import benchmark
  old={'status':'completed','selected_candidate_key':'initial','locked_candidate_key':'locked',
       'candidate':{'simulation':'passed_native_model','text':'!GSE3!test'},'native_reference':{'dps':200},
       'final':{'scenarios':{'nominal':{'complete':True,'candidate':[{'samples':99}],
          'seed':[{'samples':99}], 'comparison':{'candidate_mean_dps':180,'control_mean_dps':100}},
          'slow':{'comparison':{'candidate_mean_dps':20,'control_mean_dps':10}}}}}
  baseline=benchmark.extract_product(old)
  self.assertEqual(baseline['final_dps'],100)
  current=dict(baseline,final_dps=120,reference_ratio=.6,measurement='search_score')
  for row,budget in ((baseline,420),(current,600)):
   row.update(search_budget_seconds=budget,engine_identities=['same'],profile_sha256='profile',
              random_seed=1,candidate_timeline=[{'score':80,'lower_seconds':8,'upper_seconds':10}])
  rows = [json.dumps(dict(row, random_seed=seed))
          for row in (baseline, current) for seed in SEEDS[:3]]
  with patch.object(Path, 'mkdir'), patch.object(Path, 'is_file', return_value=True), \
       patch.object(Path, 'read_text', side_effect=rows), patch.object(Path, 'write_text'):
   report = benchmark.summarize_product(Path('unused-product'))
  self.assertEqual(report['status'], 'ready_for_human')
  self.assertEqual(report['pairs'][0]['dps_change'], .2)
  self.assertEqual(report['pairs'][0]['baseline']['threshold_time']['limit_seconds'], 420)
  self.assertEqual(report['pairs'][0]['current']['threshold_time']['limit_seconds'], 600)
  self.assertFalse(report['pairs'][0]['current']['threshold_time']['reached'])
 def test_product_comparison_reads_search_result_without_final_retest(self):
  import benchmark
  result={'status':'completed','candidate':{'simulation':'passed_native_model','text':'!GSE3!test'},
          'selected_candidate_key':'winner','search_result':{'dps':120,'samples':99},
          'native_reference':{'dps':150},'final':{'status':'not_requested','scenarios':{}}}
  row=benchmark.extract_product(result)
  self.assertTrue(row['evidence_complete'])
  self.assertEqual(row['final_dps'],120)
  self.assertEqual(row['reference_ratio'],.8)
  self.assertEqual(row['measurement'],'search_score')
 @pytest.mark.real
 def test_snapshot_publication_recovers_from_brief_directory_occupation(self):
  import os
  import benchmark
  with TemporaryDirectory() as directory:
   root=Path(directory);project=root/"projects/sim2gse";project.mkdir(parents=True)
   for name in ("engine.py","codec.py","macro_interpreter.py","simulation_config.py"):
    (project/name).write_text("ROOT = Path(__file__).resolve().parents[2]\n")
   (project/"search.py").write_text("uncommitted_source\n")
   names="\n".join(p.relative_to(root).as_posix() for p in project.iterdir())
   replace=os.replace;attempts=[]
   occupied=PermissionError("directory temporarily occupied");occupied.winerror=5
   def publish(pending,base):
    attempts.append(pending)
    self.assertFalse(base.exists())
    self.assertEqual((pending/"projects/sim2gse/search.py").read_text(),"uncommitted_source\n")
    self.assertTrue((pending/"source-manifest.json").is_file())
    if len(attempts)<=2:raise occupied
    return replace(pending,base)
   with patch.object(benchmark,"ROOT",root),patch.object(benchmark,"_git",return_value=names),patch("os.replace",side_effect=publish),patch("time.sleep") as sleep:
    source=materialize(root/"evidence","head","current",worktree=True)
   self.assertEqual((source/"search.py").read_text(),"uncommitted_source\n")
   self.assertEqual(len(set(attempts)),1)
   self.assertEqual(len(attempts),3)
   self.assertEqual(sleep.call_count,2)
   self.assertEqual((project/"search.py").read_text(),"uncommitted_source\n")
   self.assertFalse(attempts[0].exists())
   (project/"search.py").write_text("changed_after_snapshot\n")
   with patch.object(benchmark,"ROOT",root),patch.object(benchmark,"_git",return_value=names):
    with self.assertRaisesRegex(RuntimeError,"源码"):
     materialize(root/"evidence","head","current",worktree=True)
 @pytest.mark.real
 def test_snapshot_publication_preserves_persistent_and_unrelated_failures(self):
  import benchmark
  occupied=PermissionError("directory remains occupied");occupied.winerror=5
  for failure,expected_attempts in ((occupied,11),(OSError("unrelated failure"),1)):
   with self.subTest(failure=type(failure).__name__),TemporaryDirectory() as directory:
    root=Path(directory);project=root/"projects/sim2gse";project.mkdir(parents=True)
    for name in ("engine.py","codec.py","macro_interpreter.py","simulation_config.py"):
     (project/name).write_text("ROOT = Path(__file__).resolve().parents[2]\n")
    names="\n".join(p.relative_to(root).as_posix() for p in project.iterdir())
    with patch.object(benchmark,"ROOT",root),patch.object(benchmark,"_git",return_value=names),patch("os.replace",side_effect=failure) as publish,patch("time.sleep") as sleep:
     with self.assertRaises(type(failure)) as raised:
      materialize(root/"evidence","head","current",worktree=True)
    self.assertIs(raised.exception,failure)
    self.assertEqual(publish.call_count,expected_attempts)
    self.assertEqual(sleep.call_args_list,[((0.02,),)]*(expected_attempts-1))
    self.assertFalse((root/"evidence/current-source").exists())
    self.assertEqual(list((root/"evidence").iterdir()),[])
@pytest.mark.real
def test_snapshot_result_reader_binds_the_original_connected_project(tmp_path, installed_data_store, monkeypatch):
 import benchmark, result_store, shutil, subprocess
 run_id = 'snapshot-run'
 row = dict.fromkeys(result_store.RUN_SCHEMA)
 row.update(run_id=run_id, status='completed', phase='done', batch_keys=[])
 result_store.write('runs', run_id, [row], schema=result_store.RUN_SCHEMA)
 connected = subprocess.run([sys.executable, str(installed_data_store / 'scripts/project_binding.py'),
                            'connect', '--project', str(tmp_path)], text=True, capture_output=True)
 assert connected.returncode == 0, connected.stderr
 source = tmp_path / 'snapshot/projects/sim2gse'
 source.mkdir(parents=True)
 for name in ('task.py', 'runtime.py', 'simulation_config.py', 'result_store.py', 'formal_search.py', 'search.py'):
  shutil.copy2(ROOT / 'projects/sim2gse' / name, source / name)
 destination = tmp_path / 'saved-task'
 destination.mkdir()
 (destination / 'result.json').write_text(json.dumps({'run_id': run_id}), encoding='utf-8')
 monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
 result = benchmark.read_task_result(source, destination)
 assert result['run_id'] == run_id and result['status'] == 'completed'
 assert not (tmp_path / 'snapshot/data').exists()
