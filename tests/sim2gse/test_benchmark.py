from pathlib import Path
import sys
from unittest import TestCase
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"scripts/dev/sim2gse"))
from benchmark import extract,summarize_profile
class BenchmarkTests(TestCase):
 def row(self,dps,starts,unique=10,scores=(80,100),complete=True):return {"final_dps":dps,"native_batch_starts":starts,"common_unique_candidates":unique,"wall_seconds":60,"candidate_scores":list(scores),"evidence_complete":complete}
 def test_profile_summary_applies_frozen_gates(self):
  result=summarize_profile([self.row(100,100) for _ in range(5)],[self.row(100,75,12,(96,)) for _ in range(5)]);self.assertEqual(result["threshold"],95);self.assertEqual(result["status"],"passed")
 def test_incomplete_result_is_evidence_instead_of_an_exception(self):
  row=extract({"status":"validation_incomplete"},Path("missing"),12);self.assertFalse(row["evidence_complete"]);self.assertIsNone(row["final_dps"]);self.assertEqual(summarize_profile([self.row(100,100) for _ in range(5)],[self.row(None,80,complete=False) for _ in range(5)])["status"],"insufficient_evidence")
