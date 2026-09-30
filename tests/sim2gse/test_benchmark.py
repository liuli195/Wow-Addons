import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"scripts/dev/sim2gse"))
from benchmark import PROFILES,SEEDS,PHASE2_BASELINE,behavior_id,extract,summarize,materialize
class BenchmarkTests(TestCase):
 def test_phase2_reports_locked_candidate_even_when_export_falls_back(self):
  result={"status":"completed","locked_candidate_key":"locked","selected_candidate_key":"initial",
          "final":{"scenarios":{name:{"comparison":{"candidate_mean_dps":90,"control_mean_dps":100}} for name in ("nominal","jitter","slow","pause","phase")}}}
  historical=extract(result,Path("missing"),600)
  phase2=extract(result,Path("missing"),600,phase2=True)
  self.assertEqual(historical["final_dps"],100)
  self.assertEqual(phase2["final_dps"],90)
  self.assertEqual(phase2["reported_candidate_key"],"locked")
  self.assertEqual(result["selected_candidate_key"],"initial")
 def test_worktree_snapshot_contains_uncommitted_source_and_rejects_later_changes(self):
  import benchmark
  with TemporaryDirectory() as directory:
   root=Path(directory);project=root/"projects/sim2gse";project.mkdir(parents=True)
   for name in ("engine.py","codec.py","macro_interpreter.py","simulation_config.py"):
    (project/name).write_text("ROOT = Path(__file__).resolve().parents[2]\n")
   (project/"search.py").write_text("current_uncommitted_source\n")
   with patch.object(benchmark,"ROOT",root),patch.object(benchmark,"_git",return_value="\n".join(p.relative_to(root).as_posix() for p in project.iterdir())):
    source=materialize(root/"evidence","head","current",worktree=True)
    self.assertEqual((source/"search.py").read_text(),"current_uncommitted_source\n")
    (project/"search.py").write_text("changed_after_snapshot\n")
    with self.assertRaisesRegex(RuntimeError,"源码"):
     materialize(root/"evidence","head","current",worktree=True)
 def test_phase2_uses_first_stage_baseline_and_only_three_pairs(self):
  self.assertEqual(PHASE2_BASELINE,"cc94eb7253004ba1bff74e029fd6f3a8f23681d2")
  with TemporaryDirectory() as directory:
   root=Path(directory)
   for side in ("baseline","current"):
    for seed in SEEDS[:3]:
     path=root/side/"current"/str(seed)/"summary.json";path.parent.mkdir(parents=True);path.write_text(json.dumps(self.row(100,100)))
   result=summarize(root,3,profiles=("current",))
   self.assertEqual(result["seeds"],list(SEEDS[:3]))
   self.assertEqual(list(result["profiles"]),["current"])
   self.assertEqual(result["status"],"ready_for_human")
   self.assertEqual(result["decision"],"human_required")
   pairs=result["profiles"]["current"]["pairs"]
   self.assertEqual(len(pairs),3)
   self.assertEqual([row["final_dps_change"] for row in pairs],[0,0,0])
 def row(self,dps,starts,unique=10,scores=(80,100),complete=True,times=(10,20)):
  return {"final_dps":dps,"native_batch_starts":starts,"common_unique_candidates":unique,"wall_seconds":60,"search_wall_seconds":420,"candidate_scores":list(scores),"candidate_timeline":[{"score":score,"wall_seconds":wall} for score,wall in zip(scores,times)],"evidence_complete":complete,"simc_total_iterations":1000,"engine_identities":["engine"]}
 def test_behavior_identity_includes_castsequence_timeout_seconds(self):
  def candidate(timeout):
   return {"compiled_program":{"clicks":[],"castsequences":[{"step":1,"members":["a","b"],"reset":{"timeout_seconds":timeout,"flags":[]}}]}}
  self.assertNotEqual(behavior_id(candidate(2)),behavior_id(candidate(3)))
 def test_incomplete_result_is_evidence_instead_of_an_exception(self):
  row=extract({"status":"validation_incomplete"},Path("missing"),12);self.assertFalse(row["evidence_complete"]);self.assertIsNone(row["final_dps"])
 def test_incomplete_final_dps_does_not_freeze_threshold(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);baseline=[self.row(100,100) for _ in range(2)]+[self.row(10000,100,complete=False) for _ in range(3)];current=[self.row(100,75,12,(96,)) for _ in range(2)]+[self.row(1,75,12,(96,),complete=False) for _ in range(3)]
   self.write_rows(root,baseline,current);result=summarize(root)["profiles"]["current"]
   self.assertIsNone(result["threshold"])
   self.assertEqual(result["baseline"]["final_dps_median"],100)
   self.assertEqual(result["current"]["final_dps_median"],100)
   self.assertEqual(result["status"],"insufficient_evidence")
 def write_rows(self,root,baseline,current,seeds=SEEDS[:5]):
  for profile in PROFILES:
   for side,rows in (("baseline",baseline),("current",current)):
    for seed,row in zip(seeds,rows):
     path=root/side/profile/str(seed)/"summary.json";path.parent.mkdir(parents=True);path.write_text(json.dumps(row))
 def test_incomplete_first_five_are_reported_as_insufficient(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);rows=[self.row(100,100) for _ in range(4)]+[self.row(100,100,complete=False)]
   self.write_rows(root,rows,rows);self.assertEqual(summarize(root)["status"],"insufficient_evidence")
 def test_report_keeps_primary_dps_and_efficiency_time_separate(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);baseline=[self.row(100,100,10,(80,100),times=(10,20)) for _ in range(5)];current=[self.row(100,75,12,(80,100),times=(8,16)) for _ in range(5)]
   self.write_rows(root,baseline,current);result=summarize(root)
   self.assertEqual(result["profiles"]["current"]["primary_result"]["final_dps_change"],0)
   self.assertEqual(result["profiles"]["current"]["efficiency_result"]["threshold_wall_time_gain"],.2)
   self.assertEqual(result["decision"],"human_required")
   self.assertEqual(result["status"],"ready_for_human")
 def test_evaluation_improvement_does_not_replace_wall_time_result(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);baseline=[self.row(100,100,10,(80,90,100),times=(5,10,20)) for _ in range(5)];current=[self.row(100,100,10,(96,),times=(20,)) for _ in range(5)]
   self.write_rows(root,baseline,current);result=summarize(root)
   self.assertEqual(result["profiles"]["current"]["metrics"]["threshold_evaluation_gain"],2/3)
   self.assertEqual(result["profiles"]["current"]["efficiency_result"]["threshold_wall_time_gain"],0)
   self.assertEqual(result["status"],"ready_for_human")
 def test_only_complete_missing_threshold_runs_are_charged_full_budget(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);baseline=[self.row(100,100) for _ in range(5)];current=[self.row(100,100,scores=(100,),times=(20,)),self.row(100,100,scores=(80,),times=(10,))]+[self.row(None,100,complete=False) for _ in range(3)]
   self.write_rows(root,baseline,current);result=summarize(root)
   self.assertEqual(result["profiles"]["current"]["current"]["threshold_wall_seconds_median"],220)
   self.assertEqual(result["profiles"]["current"]["current"]["threshold_success_rate"],.5)
   self.assertEqual(result["status"],"insufficient_evidence")
 def test_report_does_not_apply_business_thresholds(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);baseline=[self.row(100,100) for _ in range(5)];current=[self.row(99.4,75,12,(96,)) for _ in range(5)]
   self.write_rows(root,baseline,current);result=summarize(root)
   self.assertAlmostEqual(result["profiles"]["current"]["primary_result"]["final_dps_change"],-.006)
   self.assertEqual(result["decision"],"human_required")
   self.assertEqual(result["status"],"ready_for_human")
 def test_user_selects_five_or_ten_search_seeds(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);baseline=[self.row(100,100) for _ in SEEDS[:5]]+[self.row(200,100) for _ in SEEDS[5:]];current=[self.row(200,100) for _ in SEEDS]
   self.write_rows(root,baseline,current,SEEDS)
   first=summarize(root);expanded=summarize(root,10)
   self.assertEqual(len(first["seeds"]),5)
   self.assertEqual(len(expanded["seeds"]),10)
   self.assertEqual(first["profiles"]["current"]["threshold"],95)
   self.assertEqual(expanded["profiles"]["current"]["threshold"],142.5)
 def test_incomplete_selected_baseline_does_not_freeze_threshold(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);baseline=[self.row(100,100) for _ in SEEDS];baseline[-1]=self.row(100,100,complete=False);current=[self.row(100,100) for _ in SEEDS]
   self.write_rows(root,baseline,current,SEEDS);result=summarize(root,10)["profiles"]["current"]
   self.assertIsNone(result["threshold"])
   self.assertIsNone(result["efficiency_result"]["threshold_wall_time_gain"])
   self.assertEqual(result["status"],"insufficient_evidence")
