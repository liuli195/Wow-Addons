"""死亡骑士三专精 × 三组件的真实生产代码对照。

只断言外部可观察结果：工具跑完，出的报告里三专精 × 生命/主资源/职业资源都有实质断言。
不触碰适配器与投影的内部实现。
"""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / ".agents" / "skills" / "wow-addon-test"
ENTRY = SKILL / "scripts" / "wowtest.py"
CONFIG = ROOT / "tests" / "addons" / "MYUI_CrosshairHUD" / ".wow-test" / "wowtest.json"
OUTPUT_DIR = ROOT / ".local" / "tests" / "wow-addon-test"
DK_SPECS = ("250", "251", "252")


ACTUAL = OUTPUT_DIR / "dk-actual.json"


def run_tool(output_name):
    """跑一次对照。退出码 0=范围内通过、1=发现差异，两者都属"正常完成"；
    真正的判定由仓库侧比较层做，所以这里只要求工具**没有执行错误**。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUTPUT_DIR / output_name
    result = subprocess.run(
        [sys.executable, str(ENTRY), "run", "--config", str(CONFIG),
         "--output", str(report), "--save-actual", str(ACTUAL), "--json"],
        capture_output=True, text=True, encoding="utf-8", timeout=600,
    )
    self_check = result.returncode in (0, 1)
    payload = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
    return result, report, payload if self_check else {}


class DeathKnightComparisonTest(unittest.TestCase):
    def test_report_loaded_real_production_files(self):
        result, report, _ = run_tool("dk-run.json")
        self.assertIn(result.returncode, (0, 1), f"工具未正常完成：{result.stdout[-500:]}{result.stderr[-500:]}")
        self.assertNotIn("tool_error", result.stdout, f"工具报错：{result.stdout[:300]}")
        data = json.loads(report.read_text(encoding="utf-8"))
        loaded = set(data["execution"]["source_sha256"])
        self.assertEqual(
            loaded,
            {"addons/MYUI_CrosshairHUD/Logic.lua", "addons/MYUI_CrosshairHUD/Elements.lua",
             "addons/MYUI_CrosshairHUD/Config.lua", "addons/MYUI_CrosshairHUD/Core.lua"},
            "报告未记录预期的四个生产文件",
        )

    def test_all_three_components_have_substantive_assertions(self):
        _, report, _ = run_tool("dk-run.json")
        data = json.loads(report.read_text(encoding="utf-8"))
        covered = [row for row in data["coverage"] if str(row["spec_id"]) in DK_SPECS]
        self.assertEqual(len(covered), len(DK_SPECS), "并非三专精都被覆盖")
        for row in covered:
            self.assertEqual(sorted(row["components"]), ["health", "primary", "resource"],
                             f"专精 {row['spec_id']} 未覆盖三个组件")
            self.assertGreater(row["cases"], 0, f"专精 {row['spec_id']} 没有用例")

    def test_repo_judgement_has_no_unregistered_differences(self):
        """仓库侧双边投影的判定：通过 + 已知差异，未登记差异必须为零。"""
        _, report, _ = run_tool("dk-run.json")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import wowtest_projection as projection
        from wowtestlib import core
        _, cases, baseline, _ = core.data()
        dk_cases = [c for c in cases if c["spec_id"] in (250, 251, 252)]
        dk_ref = [b for b in baseline if b["id"].split(".")[0][5:] in DK_SPECS]
        judged = projection.judge(dk_cases, dk_ref, json.loads(ACTUAL.read_text(encoding="utf-8")))
        totals = judged["totals"]
        self.assertEqual(totals["errors"], 0, "存在执行错误")
        self.assertEqual(totals.get("difference", 0), 0, "存在未登记的差异")
        self.assertGreater(totals.get("pass", 0), 0, "没有任何用例通过")
        self.assertGreater(totals.get("known_difference", 0), 0, "已批准的差异未被登记")
        self.assertEqual(totals["cases"], len(dk_cases), "用例数与会话锁定数据不一致")

    def test_death_knight_run_has_no_execution_errors(self):
        _, report, _ = run_tool("dk-run.json")
        data = json.loads(report.read_text(encoding="utf-8"))
        errors = [e for case in data["cases"] for e in case.get("errors", [])]
        self.assertEqual(errors, [], f"存在执行错误：{errors[:3]}")


class LockedDataCheckTest(unittest.TestCase):
    """逐条核对与失败路径：不只看总数，也不允许"缺读数"被当成通过。"""

    def _locked(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from wowtestlib import core
        _, cases, baseline, _ = core.data()
        dk_cases = [c for c in cases if c["spec_id"] in (250, 251, 252)]
        dk_ref = [b for b in baseline if b["id"].split(".")[0][5:] in DK_SPECS]
        return dk_cases, dk_ref

    def test_every_locked_case_and_checkpoint_is_accounted_for(self):
        _, report, _ = run_tool("dk-run.json")
        dk_cases, _ = self._locked()
        expected = {c["id"]: len(c["steps"]) for c in dk_cases}
        actual = {r["id"]: len(r.get("snapshots") or [])
                  for r in json.loads(ACTUAL.read_text(encoding="utf-8"))}
        self.assertEqual(set(expected), set(actual), "用例清单与锁定数据不一致")
        mismatched = {cid: (steps, actual[cid]) for cid, steps in expected.items()
                      if actual[cid] != steps}
        self.assertEqual(mismatched, {}, f"检查点数与锁定数据不一致：{list(mismatched)[:3]}")

    def test_empty_selection_is_not_a_pass(self):
        result = subprocess.run(
            [sys.executable, str(ENTRY), "run", "--config", str(CONFIG),
             "--case", "no-such-case", "--output", str(OUTPUT_DIR / "dk-empty.json"), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
        )
        self.assertNotEqual(result.returncode, 0, "空选择不得返回成功")
        self.assertIn("tool_error", result.stderr, "空选择应显式报错（工具把错误写 stderr）")

    def test_unreadable_reading_is_not_a_silent_pass(self):
        """缺读数必须被显式判为无效，不得补默认值后通过。"""
        _, report, _ = run_tool("dk-run.json")
        dk_cases, dk_ref = self._locked()
        observed = json.loads(ACTUAL.read_text(encoding="utf-8"))
        for record in observed:
            record["snapshots"] = [dict(s, observed=dict(s["observed"], has_health=False))
                                   for s in record["snapshots"]]
        import wowtest_projection as projection
        judged = projection.judge(dk_cases, dk_ref, observed)
        self.assertEqual(judged["totals"].get("pass", 0), 0, "缺读数却仍有用例被判通过")
        self.assertGreater(judged["totals"].get("difference", 0), 0, "缺读数未被判为差异")

    def test_repeat_run_leaves_tracked_files_unchanged(self):
        def tracked_state():
            return subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                  capture_output=True, text=True, encoding="utf-8").stdout
        before = tracked_state()
        run_tool("dk-run.json")
        run_tool("dk-run.json")
        self.assertEqual(before, tracked_state(), "重复运行改动了受版本控制的文件")


class DefectDetectionTest(unittest.TestCase):
    """定向缺陷注入：证明这套比较真的能抓到错误，而不是橡皮图章。

    注入点选**生产代码的曲线端点**：仓库侧的逆映射按设计常量独立写死，
    不复用被测曲线——所以生产曲线一改，观测比例就会偏，必须被抓到。
    """

    def _inject_and_judge(self, marker, replacement, expected_component):
        source = ROOT / "addons" / "MYUI_CrosshairHUD" / "Logic.lua"
        original = source.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        self.assertIn(marker.encode("utf-8"), original, "注入点未找到")
        try:
            source.write_bytes(original.replace(marker.encode("utf-8"),
                                                replacement.encode("utf-8"), 1))
            result, report, _ = run_tool("dk-injected.json")
            self.assertIn(result.returncode, (0, 1), f"注入后工具未正常完成：{result.stdout[-400:]}")
            data = json.loads(report.read_text(encoding="utf-8"))
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import wowtest_projection as projection
            from wowtestlib import core
            profiles, cases, baseline, _ = core.data()
            dk_cases = [c for c in cases if c["spec_id"] in (250, 251, 252)]
            dk_ref = [b for b in baseline if b["id"].split(".")[0][5:] in DK_SPECS]
            actual = json.loads(ACTUAL.read_text(encoding="utf-8"))
            judged = projection.judge(dk_cases, dk_ref, actual)
            hit = [row["id"] for row in judged["cases"]
                   for d in row["differences"]
                   if d["component"] == expected_component and not d.get("known")]
            return data, judged, hit
        finally:
            source.write_bytes(original)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest,
                             "注入后未能恢复生产代码")

    def test_injected_health_curve_defect_is_detected(self):
        data, judged, hit = self._inject_and_judge("start = 99", "start = 111", "health")
        self.assertGreater(judged["totals"].get("difference", 0), 0,
                           "曲线端点被改动，却没有产生未登记的差异")
        self.assertTrue(hit, "生命组件未出现预期差异")
        self.assertEqual(data["execution"]["adapter_sha256"],
                         json.loads((OUTPUT_DIR / "dk-run.json").read_text(encoding="utf-8")
                                    )["execution"]["adapter_sha256"],
                         "适配器不应随注入变化——差异必须来自生产代码")


if __name__ == "__main__":
    unittest.main()
