import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"scripts/dev/sim2gse"))
from benchmark import PROFILES,SEEDS,behavior_id,extract,summarize,summarize_profile
class BenchmarkTests(TestCase):
 def row(self,dps,starts,unique=10,scores=(80,100),complete=True,times=(10,20)):
  return {"final_dps":dps,"native_batch_starts":starts,"common_unique_candidates":unique,"wall_seconds":60,"search_wall_seconds":420,"candidate_scores":list(scores),"candidate_timeline":[{"score":score,"wall_seconds":wall} for score,wall in zip(scores,times)],"evidence_complete":complete,"simc_total_iterations":1000,"engine_identities":["engine"]}
 def test_profile_summary_applies_frozen_gates(self):
  result=summarize_profile([self.row(100,100) for _ in range(5)],[self.row(105,75,12,(96,)) for _ in range(5)]);self.assertEqual(result["threshold"],95);self.assertEqual(result["metrics"]["dps_change"],.05);self.assertEqual(result["status"],"ready_for_human")
 def test_behavior_identity_includes_castsequence_timeout_seconds(self):
  def candidate(timeout):
   return {"compiled_program":{"clicks":[],"castsequences":[{"step":1,"members":["a","b"],"reset":{"timeout_seconds":timeout,"flags":[]}}]}}
  self.assertNotEqual(behavior_id(candidate(2)),behavior_id(candidate(3)))
 def test_incomplete_result_is_evidence_instead_of_an_exception(self):
  row=extract({"status":"validation_incomplete"},Path("missing"),12);self.assertFalse(row["evidence_complete"]);self.assertIsNone(row["final_dps"]);self.assertEqual(summarize_profile([self.row(100,100) for _ in range(5)],[self.row(None,80,complete=False) for _ in range(5)])["status"],"insufficient_evidence")
 def test_incomplete_final_dps_is_excluded_from_formal_statistics(self):
  baseline=[self.row(100,100) for _ in range(2)]+[self.row(10000,100,complete=False) for _ in range(3)]
  current=[self.row(100,75,12,(96,)) for _ in range(2)]+[self.row(1,75,12,(96,),complete=False) for _ in range(3)]
  result=summarize_profile(baseline,current)
  self.assertEqual(result["threshold"],95)
  self.assertEqual(result["baseline"]["final_dps_median"],100)
  self.assertEqual(result["current"]["final_dps_median"],100)
  self.assertEqual(result["status"],"insufficient_evidence")
 def write_first_five(self,root,baseline,current):
  for profile in PROFILES:
   for side,rows in (("baseline",baseline),("current",current)):
    for seed,row in zip(SEEDS[:5],rows):
     path=root/side/profile/str(seed)/"summary.json";path.parent.mkdir(parents=True);path.write_text(json.dumps(row))
 def test_incomplete_first_five_are_reported_as_insufficient(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);rows=[self.row(100,100) for _ in range(4)]+[self.row(100,100,complete=False)]
   self.write_first_five(root,rows,rows)
   result=summarize(root)
   self.assertEqual(result["status"],"insufficient_evidence")
 def test_report_keeps_primary_dps_and_efficiency_time_separate(self):
  with TemporaryDirectory() as directory:
   root=Path(directory)
   baseline=[self.row(100,100,10,(80,100),times=(10,20)) for _ in range(5)]
   current=[self.row(100,75,12,(80,100),times=(8,16)) for _ in range(5)]
   self.write_first_five(root,baseline,current)
   result=summarize(root)
   self.assertEqual(result["profiles"]["current"]["primary_result"]["final_dps_change"],0)
   self.assertEqual(result["profiles"]["current"]["efficiency_result"]["threshold_wall_time_gain"],.2)
   self.assertEqual(result["decision"],"human_required")
   self.assertEqual(result["status"],"ready_for_human")
 def test_evaluation_improvement_does_not_replace_wall_time_result(self):
  with TemporaryDirectory() as directory:
   root=Path(directory)
   baseline=[self.row(100,100,10,(80,90,100),times=(5,10,20)) for _ in range(5)]
   current=[self.row(100,100,10,(96,),times=(20,)) for _ in range(5)]
   self.write_first_five(root,baseline,current)
   result=summarize(root)
   self.assertEqual(result["profiles"]["current"]["metrics"]["threshold_evaluation_gain"],2/3)
   self.assertEqual(result["profiles"]["current"]["metrics"]["threshold_wall_time_gain"],0)
   self.assertEqual(result["profiles"]["current"]["efficiency_result"]["threshold_wall_time_gain"],0)
   self.assertEqual(result["status"],"ready_for_human")
 def test_missing_threshold_is_charged_full_search_budget_and_reported(self):
  baseline=[self.row(100,100) for _ in range(5)]
  current=[self.row(100,100,scores=(80,),times=(10,)) for _ in range(5)]
  result=summarize_profile(baseline,current)
  self.assertEqual(result["current"]["threshold_wall_seconds_median"],420)
  self.assertEqual(result["current"]["threshold_success_rate"],0)
  self.assertEqual(result["status"],"ready_for_human")
 def test_report_does_not_apply_business_thresholds(self):
  with TemporaryDirectory() as directory:
   root=Path(directory)
   baseline=[self.row(100,100) for _ in range(5)]
   current=[self.row(99.4,75,12,(96,)) for _ in range(5)]
   self.write_first_five(root,baseline,current)
   result=summarize(root)
   self.assertAlmostEqual(result["profiles"]["current"]["primary_result"]["final_dps_change"],-.006)
   self.assertEqual(result["decision"],"human_required")
   self.assertEqual(result["status"],"ready_for_human")
