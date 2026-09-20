"""死亡骑士三专精 × 三组件的真实生产代码对照。

只断言外部可观察结果：工具跑完，出的报告里三专精 × 生命/主资源/职业资源都有实质断言。
不触碰适配器与投影的内部实现。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SKILL = ROOT / ".agents" / "skills" / "wow-addon-test"
ENTRY = SKILL / "scripts" / "wowtest.py"
CONFIG = HERE / ".wow-test" / "wowtest.json"
OUTPUT_DIR = ROOT / ".local" / "tests" / "wow-addon-test"
DK_SPECS = ("250", "251", "252")
# 固定用仓库自带的 Lua 5.1，结果不随机器上装了什么而变
REPO_LUA = ROOT / ".tools" / "lua-5.1.5" / "src" / "lua.exe"
SKILL_ENV = {**os.environ, "WOWTEST_LUA": str(REPO_LUA)}
# 导入路径只在此处加一次；仓库侧投影与技能库都从这里解析
for extra in (str(HERE), str(SKILL / "scripts")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from wowtestlib import core  # noqa: E402  只借它的锁定数据与完整性校验


ACTUAL = OUTPUT_DIR / "dk-actual.json"


def run_tool(output_name):
    """跑一次对照。退出码 0=范围内通过、1=发现差异，两者都属"正常完成"；
    真正的判定由仓库侧比较层做，所以这里只要求工具**没有执行错误**。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUTPUT_DIR / output_name
    result = subprocess.run(
        [sys.executable, str(ENTRY), "run", "--config", str(CONFIG),
         "--output", str(report), "--save-actual", str(ACTUAL), "--json"],
        capture_output=True, text=True, encoding="utf-8", timeout=600, env=SKILL_ENV,
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
        import wowtest_projection as projection
        dk_cases, dk_ref = locked_data()
        judged = projection.judge(dk_cases, dk_ref, json.loads(ACTUAL.read_text(encoding="utf-8")))
        totals = judged["totals"]
        self.assertEqual(totals["errors"], 0, "存在执行错误")
        self.assertEqual(totals.get("difference", 0), 0, "存在未登记的差异")
        self.assertGreater(totals.get("pass", 0), 0, "没有任何用例通过")
        self.assertGreater(totals.get("known_difference", 0), 0, "已批准的差异未被登记")
        self.assertEqual(totals["cases"], len(dk_cases), "用例数与会话锁定数据不一致")

    def test_tool_public_entry_reports_the_formal_verdict(self):
        """正式判定必须由**工具自己**给出来。

        以前工具报的是"78 个差异、0 通过"——因为插件实际输出与工具标准输出不同形，
        工具认不了，真正的判定落在仓库侧辅助程序里。那等于工具根本没在用：
        任何人直接跑工具，得到的结论都是"全错"。
        """
        _, report, _ = run_tool("dk-run.json")
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["execution"]["verdict"], "project-projection",
                         "工具没有走项目投影，仍在用通用比较")
        self.assertEqual(data["status"], "pass", f"工具给出的判定不是通过：{data['summary']}")
        self.assertEqual(data["summary"]["differences"], 0, "工具报出了未登记的差异")
        self.assertGreater(data["summary"]["known_differences"], 0, "工具没有登记已知差异")
        self.assertTrue(data["execution"].get("projection_sha256"),
                        "报告没有记录所用投影的身份")

    def test_tool_fails_loudly_when_the_projection_is_broken(self):
        """投影声明了却坏掉时必须显式失败，不得静默退回通用比较。

        配置必须放在**项目根正确**的位置，否则会先因为找不到生产文件失败——
        那样测到的是另一件事，等于这条回归没测到它名字宣称的行为。
        """
        project = OUTPUT_DIR / "broken-projection"
        if project.exists():
            shutil.rmtree(project)
        project.mkdir(parents=True)
        config = dict(json.loads(CONFIG.read_text(encoding="utf-8")),
                      project_root=str(ROOT), projection="no-such-projection.py")
        (project / "wowtest.json").write_text(json.dumps(config, ensure_ascii=False),
                                              encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ENTRY), "run", "--config", str(project / "wowtest.json"),
             "--output", str(project / "out.json"), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=600, env=SKILL_ENV,
        )
        self.assertNotEqual(result.returncode, 0, "投影缺失却仍然成功了")
        message = json.loads(result.stderr.strip().splitlines()[-1])["message"]
        self.assertIn("投影", message, f"失败原因不是投影加载：{message[:200]}")

    def test_death_knight_run_has_no_execution_errors(self):
        _, report, _ = run_tool("dk-run.json")
        data = json.loads(report.read_text(encoding="utf-8"))
        errors = [e for case in data["cases"] for e in case.get("errors", [])]
        self.assertEqual(errors, [], f"存在执行错误：{errors[:3]}")


class LockedDataCheckTest(unittest.TestCase):
    """逐条核对与失败路径：不只看总数，也不允许"缺读数"被当成通过。"""

    def test_every_locked_case_and_checkpoint_is_accounted_for(self):
        _, report, _ = run_tool("dk-run.json")
        dk_cases, _ = locked_data()
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
            capture_output=True, text=True, encoding="utf-8", timeout=600, env=SKILL_ENV,
        )
        self.assertNotEqual(result.returncode, 0, "空选择不得返回成功")
        self.assertIn("tool_error", result.stderr, "空选择应显式报错（工具把错误写 stderr）")

    def test_unreadable_reading_is_not_a_silent_pass(self):
        """缺读数必须被显式判为无效，不得补默认值后通过。"""
        _, report, _ = run_tool("dk-run.json")
        dk_cases, dk_ref = locked_data()
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


def locked_data():
    """会话锁定数据里属于死亡骑士三专精的用例与基线。"""
    _, cases, baseline, _ = core.data()
    return ([c for c in cases if c["spec_id"] in (250, 251, 252)],
            [b for b in baseline if b["id"].split(".")[0][5:] in DK_SPECS])


class KnownDifferenceScopeTest(unittest.TestCase):
    """已登记差异的**作用范围**。

    规矩是「逐字段登记 + 观测值必须符合事先批准的产品口径」，不是「整块组件放行」。
    规矩要立得住，就必须有反面证据：登记用例里没登记的字段、以及偏离批准口径的观测值，
    都得照样判失败。这里只改数据、不改生产代码，所以能精确地把规矩本身逼出来。
    """

    @classmethod
    def setUpClass(cls):
        run_tool("dk-run.json")
        cls.observations = json.loads(ACTUAL.read_text(encoding="utf-8"))
        cls.cases, cls.baseline = locked_data()

    def _judge(self, observations=None, cases=None):
        import wowtest_projection as projection
        return projection.judge(cases if cases is not None else self.cases,
                                self.baseline,
                                observations if observations is not None
                                else self.observations)

    def _copy(self):
        return json.loads(json.dumps(self.observations))

    def test_every_known_difference_names_its_field_and_approved_value(self):
        """通过了的登记差异，必须能说出「哪个字段」和「批准它是什么值」。"""
        known = [d for row in self._judge()["cases"] for d in row["differences"] if d.get("known")]
        self.assertGreater(len(known), 0, "没有任何已知差异——登记形同虚设")
        for difference in known:
            self.assertIn("approved_expected", difference, "已知差异缺少批准口径")
            self.assertTrue(difference.get("approved_by"), "已知差异缺少批准说明")

    def test_registered_field_off_the_approved_value_still_fails(self):
        """登记不等于免责：观测值偏离批准口径时仍须判失败。

        做法是把该步**输入**改掉——批准口径是「等于该步输入」，输入一变，
        观测值就不再符合批准口径，必须由「通过」翻成「失败」。
        """
        cases = json.loads(json.dumps(self.cases))
        touched = 0
        for case in cases:
            if case["id"].endswith(".disconnect-reconnect"):
                health = case["steps"][1]["state"]["health"]
                health["current"] = health["maximum"] * 0.9
                touched += 1
        self.assertGreater(touched, 0, "未找到断线用例")
        judged = self._judge(cases=cases)
        self.assertGreater(judged["totals"]["difference"], 0,
                           "观测值已偏离批准口径，却仍被当成已知差异放行")

    def test_unregistered_field_in_a_registered_case_still_fails(self):
        """登记用例里没登记过的字段照常判失败——不许顺手放行整块组件。"""
        observations = self._copy()
        target = next(r for r in observations if r["id"].endswith(".primary-type-roundtrip"))
        for snapshot in target["snapshots"]:
            snapshot["observed"]["health_angle"] += 0.2  # 约 11.5 度，足以改变比例
        judged = self._judge(observations=observations)
        self.assertGreater(judged["totals"]["difference"], 0,
                           "登记用例的未登记字段（生命）未被拦下")
        offending = [d for row in judged["cases"] for d in row["differences"]
                     if d["component"] == "health"]
        self.assertTrue(offending, "生命组件的偏差没有出现在差异清单里")

    # 满格时插件**实际输出过**的两个角度（取自正常观测，不是按公式反推的）。
    # 用来模拟"插件退回原生表现"：读数回到满格，而产品期望并不是满格。
    FULL_BAR_ANGLES = {"health_angle": -5.078908123303499,
                       "power_angle": -10.629055144645466}

    def _first_case(self, observations, suffix):
        return next(r for r in observations if r["id"].endswith(suffix))

    def _blocked_at(self, judged, case_id, step, kinds):
        """该用例该检查点上，这些字段有没有被判为**未登记差异**。

        断言必须落到具体的字段与检查点上：笼统地看"这条用例没通过"会被这条用例
        里其它检查点的偏差满足，等于没测到要测的那条规矩。
        """
        row = next(r for r in judged["cases"] if r["id"] == case_id)
        return [d for d in row["differences"]
                if d.get("step") == step and d["kind"] in kinds and not d.get("known")]

    def test_regressing_to_native_on_disconnect_fails(self):
        """断线时退回原生表现（填满）必须判失败。

        这是"已知差异"最容易被滥用的地方：只在**偏离原生**时才核对产品期望，
        那么插件一退回原生（与原生一致→无差异）就悄悄通过了，而它恰恰违反了
        已批准的产品行为。先核对期望，再谈是否偏离原生。
        """
        observations = self._copy()
        target = self._first_case(observations, ".disconnect-reconnect")
        target["snapshots"][1]["observed"].update(self.FULL_BAR_ANGLES)  # 只改断线那一步
        judged = self._judge(observations=observations)
        blocked = self._blocked_at(judged, target["id"], 2, ("ratio",))
        self.assertTrue(blocked, "断线那一步退回原生满格，产品期望未被核对")

    def test_regressing_to_native_power_type_fails(self):
        """固定符能策略下，跟随被报告的类型必须判失败。"""
        observations = self._copy()
        target = self._first_case(observations, ".primary-type-roundtrip")
        target["snapshots"][1]["observed"]["power_type"] = 3  # 被报告的类型，即原生跟随的那个
        judged = self._judge(observations=observations)
        blocked = self._blocked_at(judged, target["id"], 2, ("type",))
        self.assertTrue(blocked, "主资源类型跟随了被报告的值，产品期望未被核对")

    def test_ready_rune_filled_with_zero_fails(self):
        """就绪的符文必须是满的：填 0 要判失败。"""
        observations = self._copy()
        target = self._first_case(observations, ".runes-depleted-1")
        touched = 0
        for snapshot in target["snapshots"]:
            for node in snapshot["observed"].get("runes") or []:
                if node.get("state") == "ready" and touched == 0:
                    node["frac"] = 0.0
                    touched += 1
        self.assertGreater(touched, 0, "没有找到就绪的符文可改")
        judged = self._judge(observations=observations)
        offenders = [row for row in judged["cases"] if row["id"] == target["id"]]
        self.assertTrue(offenders and offenders[0]["status"] != "pass",
                        "就绪的符文被填了 0，却被放行")

    def test_gapped_rune_indices_fail(self):
        """六个格子的索引必须正好是 1..N：缺号或重复都说明没对上号。"""
        observations = self._copy()
        target = self._first_case(observations, ".runes-depleted-1")
        nodes = target["snapshots"][0]["observed"]["runes"]
        nodes[1]["index"] = nodes[0]["index"]  # 制造重复，必然缺号
        judged = self._judge(observations=observations)
        offenders = [row for row in judged["cases"] if row["id"] == target["id"]]
        self.assertTrue(offenders and offenders[0]["status"] != "pass",
                        "符文索引重复/缺号，却被放行")

    def test_missing_power_type_is_not_silently_skipped(self):
        """观测不到主资源类型时必须显式失败，不能当作"没这回事"。"""
        observations = self._copy()
        target = self._first_case(observations, ".primary-full")
        for snapshot in target["snapshots"]:
            snapshot["observed"]["power_type"] = None
        judged = self._judge(observations=observations)
        offenders = [row for row in judged["cases"] if row["id"] == target["id"]]
        self.assertTrue(offenders and offenders[0]["status"] != "pass",
                        "主资源类型缺失被静默跳过")

    def test_error_count_reflects_unreadable_snapshots(self):
        """读不到快照时必须计入错误数，且用例总数不能因此少算。"""
        observations = self._copy()
        for record in observations:
            record["snapshots"] = [dict(s, observed=None) for s in record["snapshots"]]
        judged = self._judge(observations=observations)
        totals = judged["totals"]
        self.assertEqual(totals["pass"], 0, "读不到读数却仍有用例通过")
        self.assertEqual(totals["errors"], totals["cases"], "错误数与出错用例数对不上")
        self.assertEqual(totals["cases"], len(observations), "出错用例被漏计")

    def test_projection_tolerance_matches_the_tool(self):
        """投影的比例容差必须与工具的正式比较口径同值，不许各写各的。

        两边不一致会出现"数据规则判定可区分、正式比较却认为相同"的自相矛盾，
        而规格明确要求数据规则的"可区分"一律经正式比较口径判定。
        """
        import inspect
        import wowtest_projection as projection
        tool_atol = inspect.signature(core.diff).parameters["atol"].default
        self.assertEqual(projection.RATIO_TOLERANCE, tool_atol,
                         "投影的容差与工具正式比较口径不一致")

    def test_unregistered_case_gets_no_allowance(self):
        """没登记过的用例，出现任何差异都判失败。"""
        observations = self._copy()
        untouched = next(r for r in observations
                         if not r["id"].endswith((".disconnect-reconnect",
                                                  ".primary-type-roundtrip")))
        untouched["snapshots"][0]["observed"]["health_angle"] += 0.2
        judged = self._judge(observations=observations)
        offenders = [row for row in judged["cases"]
                     if row["id"] == untouched["id"] and row["status"] != "pass"]
        self.assertTrue(offenders, f"{untouched['id']} 未登记却被放行")


class DefectDetectionTest(unittest.TestCase):
    """定向缺陷注入：证明这套比较真的能抓到错误，而不是橡皮图章。

    **注入在临时项目副本里做**：真实受跟踪的生产文件一个字节都不改。
    改真实文件会带来并行跑测试时互相看到"注入到一半"的代码的风险，
    也会在受跟踪文件上留下会被别的运行误当正常结果的产物。

    注入点选生产的曲线端点、符文充能、以及轮询周期——仓库侧的逆映射与容差
    都按设计常量独立写，不复用生产常量，所以生产一改就得被抓到。
    """

    PRODUCTION = ("Logic.lua", "Elements.lua", "Config.lua", "Core.lua")

    def _temp_project(self, name):
        """生产代码 + 适配器 + 投影 + 配置复制成一个独立的临时项目。"""
        target = OUTPUT_DIR / "injection" / name
        if target.exists():
            shutil.rmtree(target)
        (target / "addons" / "MYUI_CrosshairHUD").mkdir(parents=True)
        for filename in self.PRODUCTION:
            shutil.copy2(ROOT / "addons" / "MYUI_CrosshairHUD" / filename,
                         target / "addons" / "MYUI_CrosshairHUD" / filename)
        shutil.copy2(HERE / "wowtest_projection.py", target / "projection.py")
        shutil.copy2(CONFIG.parent / "adapter.lua", target / "adapter.lua")
        config = dict(json.loads(CONFIG.read_text(encoding="utf-8")), project_root=".",
                      adapter="adapter.lua", projection="projection.py",
                      files=[f"addons/MYUI_CrosshairHUD/{n}" for n in self.PRODUCTION])
        (target / "wowtest.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _run_project(self, project, output_name):
        output = OUTPUT_DIR / output_name
        actual = OUTPUT_DIR / (Path(output_name).stem + "-actual.json")
        result = subprocess.run(
            [sys.executable, str(ENTRY), "run", "--config", str(project / "wowtest.json"),
             "--output", str(output), "--save-actual", str(actual), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=600, env=SKILL_ENV,
        )
        self.assertIn(result.returncode, (0, 1), f"工具未正常完成：{result.stdout[-400:]}")
        return json.loads(output.read_text(encoding="utf-8")), json.loads(
            actual.read_text(encoding="utf-8"))

    def _component_defect_is_detected(self, name, filename, marker, replacement, component):
        """该组件必须有一条**真的会响**的断言链：改坏生产代码就得产生未登记差异。"""
        project = self._temp_project(name)
        source = project / "addons" / "MYUI_CrosshairHUD" / filename
        original = source.read_bytes()
        self.assertIn(marker.encode("utf-8"), original, f"{filename} 里未找到注入点")
        source.write_bytes(original.replace(marker.encode("utf-8"),
                                            replacement.encode("utf-8"), 1))
        data, actual = self._run_project(project, f"{name}.json")
        import wowtest_projection as projection
        dk_cases, dk_ref = locked_data()
        judged = projection.judge(dk_cases, dk_ref, actual)
        hit = [row["id"] for row in judged["cases"]
               for d in row["differences"]
               if d["component"] == component and not d.get("known")]
        self.assertGreater(judged["totals"].get("difference", 0), 0,
                           f"{component} 组件被改坏，却没有产生未登记的差异")
        self.assertTrue(hit, f"{component} 组件未出现预期差异")
        self.assertEqual(data["execution"]["adapter_sha256"],
                         json.loads((OUTPUT_DIR / "dk-run.json").read_text(
                             encoding="utf-8"))["execution"]["adapter_sha256"],
                         "适配器不应随注入变化——差异必须来自生产代码")

    def test_injected_health_curve_defect_is_detected(self):
        self._component_defect_is_detected("health-arc", "Logic.lua",
                                           "start = 99", "start = 111", "health")

    def test_injected_power_curve_defect_is_detected(self):
        self._component_defect_is_detected("power-arc", "Logic.lua",
                                           "start = 339", "start = 349", "primary")

    def test_injected_rune_charge_defect_is_detected(self):
        self._component_defect_is_detected("rune-charge", "Logic.lua",
                                           "(now - start) / duration",
                                           "(now - start) / (duration * 2)", "resource")

    def test_injected_event_update_defect_is_detected(self):
        """事件更新路径：让生命事件分支不再更新读数，必须被抓到。

        做法是让**两个生命事件都不再进入更新分支**。注意不能只摘掉其中一个：
        `UNIT_HEALTH` 与 `UNIT_MAXHEALTH` 走的是同一个分支，只摘一个另一个照样触发，
        看起来"没有差异"，实则是自己的注入没生效——不是"事件不可观测"。
        """
        self._component_defect_is_detected(
            "event-branch", "Core.lua",
            'if event == "UNIT_HEALTH" or event == "UNIT_MAXHEALTH" then',
            'if event == "UNIT_HEALTH_OFF" or event == "UNIT_MAXHEALTH_OFF" then',
            "health")

    def test_normal_run_fails_after_injection_then_passes_after_restore(self):
        """完整闭环：正常通过 → 注入后失败 → 换一份干净副本重新通过。

        只证明"注入能被抓到"还不够——还得证明**干净的那份确实是通的**，
        否则"抓到"可能只是这套比较对什么都报错。
        """
        clean = self._temp_project("cycle-clean")
        report, _ = self._run_project(clean, "dk-cycle-clean.json")
        self.assertEqual(report["status"], "pass", f"干净副本本应通过：{report['summary']}")

        mutated = self._temp_project("cycle-mutated")
        source = mutated / "addons" / "MYUI_CrosshairHUD" / "Logic.lua"
        source.write_bytes(source.read_bytes().replace(b"start = 99", b"start = 111", 1))
        report, _ = self._run_project(mutated, "dk-cycle-mutated.json")
        self.assertIn(report["status"], ("difference", "error"),
                      f"改坏生产代码后工具未报失败：{report['summary']}")

        restored = self._temp_project("cycle-restored")
        report, _ = self._run_project(restored, "dk-cycle-restored.json")
        self.assertEqual(report["status"], "pass", "换回干净副本后没有重新通过")

    def test_injection_leaves_tracked_production_files_untouched(self):
        """注入全程不得改动受版本控制的生产文件。"""
        before = subprocess.run(["git", "status", "--porcelain", "addons/MYUI_CrosshairHUD"],
                                cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8").stdout
        project = self._temp_project("untouched-check")
        source = project / "addons" / "MYUI_CrosshairHUD" / "Logic.lua"
        source.write_bytes(source.read_bytes().replace(b"start = 99", b"start = 111", 1))
        self._run_project(project, "dk-untouched.json")
        after = subprocess.run(["git", "status", "--porcelain", "addons/MYUI_CrosshairHUD"],
                               cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8").stdout
        self.assertEqual(before, after, "注入改动了受版本控制的生产文件")


if __name__ == "__main__":
    unittest.main()
