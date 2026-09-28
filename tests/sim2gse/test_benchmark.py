from pathlib import Path
import sys
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/dev/sim2gse"))
from benchmark import summarize


class BenchmarkTests(TestCase):
    def test_summary_reports_median_iqr_worst_cost_and_throughput(self):
        rows = [
            dict(final_dps=dps, native_batch_starts=starts, unique_candidates=unique,
                 wall_seconds=60, status=status)
            for dps, starts, unique, status in (
                (100, 20, 10, "completed"), (110, 18, 12, "completed"),
                (120, 16, 14, "validation_incomplete"), (130, 14, 16, "completed"),
                (140, 12, 18, "completed"),
            )
        ]

        result = summarize(rows)

        self.assertEqual(result["final_dps_median"], 120)
        self.assertEqual(result["final_dps_worst"], 100)
        self.assertEqual(result["native_batch_starts_median"], 16)
        self.assertEqual(result["new_candidates_per_minute_median"], 14)
        self.assertEqual(result["success_rate"], 0.8)
