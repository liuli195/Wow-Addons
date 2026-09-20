"""仓库内技能 wow-addon-test：布局与可用性。

只断言外部可观察行为：技能目录的形状、入口能否跑通、两个代理能否定位到同一份真身，
以及文档里给出的路径与命令是否真实存在。

唯一的例外是**输出预算的边界用例**：它直接驱动入口的输出出口，因为"字段一多就超预算"
这种形状现有的命令造不出来，只靠跑命令测不到。除此之外不触碰工具内部实现。
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "wow-addon-test"
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


def read_frontmatter(path):
    """返回 SKILL.md 头部字段字典；没有合法头部时抛 AssertionError。"""
    text = path.read_text(encoding="utf-8")
    matched = FRONTMATTER.match(text)
    assert matched, f"{path} 缺少以 --- 起始的头部"
    fields = {}
    for line in matched.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


CLAUDE_LINK = ROOT / ".claude" / "skills" / "wow-addon-test"
ENTRY = SKILL / "scripts" / "wowtest.py"
# 仓库固定用自带的 Lua 5.1 跑本技能，结果不随机器上装了什么而变
REPO_LUA = ROOT / ".tools" / "lua-5.1.5" / "src" / "lua.exe"
# 面向代理的输出预算，与工具内的常量一致
OUTPUT_BUDGET = 16 * 1024


def skill_env():
    """调用技能入口时统一带上固定的 Lua 后端。"""
    return {**os.environ, "WOWTEST_LUA": str(REPO_LUA)}


def load_entry():
    """按路径加载技能入口，供**预算边界**用例直接驱动它的输出出口。"""
    if str(ENTRY.parent) not in sys.path:
        sys.path.insert(0, str(ENTRY.parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("wowtest_entry_under_test", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _JsonArgs:
    json = True
# 打包不变量：载荷里不得出现未被声明的纯文本大文件（应放进压缩容器）
PLAIN_TEXT_CEILING_BYTES = 64 * 1024
PLAIN_TEXT_SUFFIXES = {".json", ".lua", ".md", ".txt", ".csv", ".py"}


class SkillLayoutTest(unittest.TestCase):
    def test_skill_entry_exists_with_valid_frontmatter(self):
        entry = SKILL / "SKILL.md"
        self.assertTrue(entry.is_file(), f"技能入口不存在：{entry}")
        fields = read_frontmatter(entry)
        self.assertEqual(fields.get("name"), SKILL.name)
        self.assertTrue(fields.get("description"), "description 不得为空")

    def test_claude_side_link_resolves_to_truth(self):
        # 连接不入库（真身才是版本化对象），所以干净克隆上没有它。
        # 这里按需把它建出来，使这条检查**在干净仓库里可准备、可重复**。
        if not CLAUDE_LINK.exists():
            CLAUDE_LINK.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["cmd", "/c", "mklink", "/J",
                            str(CLAUDE_LINK), str(SKILL)],
                           check=True, capture_output=True, text=True)
        self.assertEqual(CLAUDE_LINK.resolve(), SKILL.resolve(), "连接未指向技能真身")
        self.assertTrue((CLAUDE_LINK / "SKILL.md").is_file(), "连接下入口不可达")

    def test_skill_needs_no_pointer_file(self):
        """技能自包含：载荷里不得有定位指针，工具位置由自身目录解析。

        这条只管**定位指针**。`install-skill` 是另一个东西——它把整份技能复制到
        某个项目里（供别的插件项目复用），不是让本仓库这份技能能跑起来的前提。
        它的真实性质由下面那条单独验证。
        """
        residue = sorted(
            p.relative_to(SKILL).as_posix()
            for p in SKILL.rglob("tool-location.json")
        )
        self.assertEqual(residue, [], "技能自包含后不应再有定位指针")

    def test_install_skill_only_writes_inside_the_target_project(self):
        """安装命令只往**目标项目**里写，不碰用户级目录；复制出来的副本能独立跑。

        "不装到用户级"是用户定下的约束，所以这里要证明的是**写到哪儿**，
        而不是"没有安装器"——按需复制到另一个项目是它该有的能力。
        """
        project = ROOT / ".local" / "tests" / "wow-addon-test" / "install-target"
        if project.exists():
            shutil.rmtree(project)
        project.mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(ENTRY), "install-skill",
             "--project", str(project), "--agent", "codex", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, env=skill_env(),
        )
        self.assertEqual(result.returncode, 0, f"安装失败：{result.stderr[-400:]}")
        installed = Path(json.loads(result.stdout)["skill_path"]).resolve()
        self.assertTrue(installed.is_relative_to(project.resolve()),
                        f"装到了目标项目之外：{installed}")
        self.assertEqual(installed, (project / ".agents" / "skills" / SKILL.name).resolve(),
                         "Codex 侧应落在项目的 .agents/skills/ 下")
        self.assertTrue((installed / "SKILL.md").is_file(), "复制出来的技能缺少入口")
        # 副本必须能独立跑：这正是"自包含"的含义
        probe = subprocess.run(
            [sys.executable, str(installed / "scripts" / "wowtest.py"), "doctor", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, env=skill_env(),
        )
        self.assertEqual(probe.returncode, 0, f"副本跑不起来：{probe.stderr[-400:]}")
        self.assertEqual(json.loads(probe.stdout)["data_integrity"], "pass")

    def test_payload_has_no_undeclared_large_plain_text(self):
        oversized = []
        for path in SKILL.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in PLAIN_TEXT_SUFFIXES:
                continue
            size = path.stat().st_size
            if size > PLAIN_TEXT_CEILING_BYTES:
                oversized.append(f"{path.relative_to(SKILL).as_posix()} = {size} 字节")
        self.assertEqual(oversized, [], "载荷中存在未压缩的大文本：\n" + "\n".join(oversized))

    def test_entry_runs_and_reports_integrity(self):
        result = subprocess.run(
            [sys.executable, str(ENTRY), "doctor", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
            env=skill_env(),
        )
        self.assertEqual(result.returncode, 0, f"入口执行失败：{result.stderr[-400:]}")
        report = json.loads(result.stdout)
        self.assertEqual(report.get("data_integrity"), "pass")

    def test_repo_pins_the_lua_backend(self):
        """仓库自带的 Lua 必须真的被用上，而不是碰运气用机器上装的那个。"""
        self.assertTrue(REPO_LUA.is_file(), f"仓库自带的 Lua 缺失：{REPO_LUA}")
        result = subprocess.run(
            [sys.executable, str(ENTRY), "doctor", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
            env=skill_env(),
        )
        self.assertEqual(result.returncode, 0, f"入口执行失败：{result.stderr[-400:]}")
        self.assertEqual(Path(json.loads(result.stdout)["lua"]["path"]), REPO_LUA,
                         "实际使用的 Lua 不是仓库固定指定的那个")

    def test_agent_facing_output_stays_within_budget(self):
        """给代理看的输出有大小上限；超限必须**显式标注缩裁**，不能悄悄丢内容。"""
        result = subprocess.run(
            [sys.executable, str(ENTRY), "catalog", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, env=skill_env(),
        )
        self.assertEqual(result.returncode, 0, f"入口执行失败：{result.stderr[-400:]}")
        self.assertLessEqual(len(result.stdout.encode("utf-8")), OUTPUT_BUDGET,
                             "面向代理的输出超出了预算")
        report = json.loads(result.stdout)
        self.assertTrue(report.get("details_truncated"), "缩裁没有被显式标注")
        self.assertEqual(report.get("budget_bytes"), OUTPUT_BUDGET, "未报出预算值")

    def test_truncated_output_says_how_much_was_left_out(self):
        """缩裁必须报出「少了几条」，代理才知道要不要去取完整结果。"""
        result = subprocess.run(
            [sys.executable, str(ENTRY), "catalog", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, env=skill_env(),
        )
        report = json.loads(result.stdout)
        preview = report["profiles"]
        omitted = [item for item in preview if isinstance(item, dict) and "omitted" in item]
        self.assertEqual(len(omitted), 1, f"缩裁未报出省略条数：{preview[-1]!r}")
        self.assertEqual(len(preview) - 1 + omitted[0]["omitted"], 40, "省略条数与专精总数不符")

    def test_full_result_is_reachable_past_the_budget(self):
        """屏幕上被截掉的内容必须另有去处——否则就是静默丢数据。"""
        target = ROOT / ".local" / "tests" / "wow-addon-test" / "catalog-full.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, str(ENTRY), "catalog", "--json", "--output", str(target)],
            capture_output=True, text=True, encoding="utf-8", timeout=300, env=skill_env(),
        )
        self.assertEqual(result.returncode, 0, f"入口执行失败：{result.stderr[-400:]}")
        full = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(len(full["profiles"]), 40, "完整结果里专精数不对")
        self.assertNotIn("details_truncated", full, "落盘的完整结果不应被缩裁")

    def test_budget_holds_when_field_count_is_large(self):
        """**字典的键数不受条数限制约束**：字段一多，裁剪一次照样能超出预算。

        ChatGPT 复审给的反例：100 个字段 × 512 字符 = 约 52 KB，而预算是 16 KB。
        """
        entry = load_entry()

        payload = {"status": "pass", "summary": {"cases": 1, "passed": 1, "differences": 0,
                                                 "errors": 0, "compared_checkpoints": 1,
                                                 "selected_specs": 1},
                   "wide": {f"field-{n:03d}": "x" * 512 for n in range(100)}}
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            entry.emit(payload, _JsonArgs())
        text = buffer.getvalue()
        self.assertLessEqual(len(text.encode("utf-8")), OUTPUT_BUDGET,
                             f"字段数量多时输出超出预算：{len(text.encode('utf-8'))} 字节")
        report = json.loads(text)
        self.assertTrue(report.get("details_truncated"), "超限没有被显式标注")
        self.assertEqual(report.get("summary"), payload["summary"], "总量计数在缩裁中丢失")

    def test_budget_holds_for_wide_nested_structures(self):
        """嵌套列表 + 宽字典同时超限时也必须真的装进预算。"""
        entry = load_entry()

        row = {f"k{n}": "y" * 400 for n in range(60)}
        payload = {"status": "difference", "summary": {"cases": 900, "passed": 0,
                                                       "differences": 900, "errors": 0,
                                                       "compared_checkpoints": 1800,
                                                       "selected_specs": 40},
                   "cases": [dict(row, id=f"case-{i}") for i in range(200)]}
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            entry.emit(payload, _JsonArgs())
        text = buffer.getvalue()
        self.assertLessEqual(len(text.encode("utf-8")), OUTPUT_BUDGET,
                             f"宽嵌套结构下输出超出预算：{len(text.encode('utf-8'))} 字节")
        report = json.loads(text)
        self.assertEqual(report["summary"]["cases"], 900, "总量计数在缩裁中丢失")

    def test_preview_count_is_capped(self):
        """预览条数上限：超出部分要报出省略了多少条，而不是整份倒出来。"""
        entry = load_entry()

        payload = {"status": "difference",
                   "summary": {"cases": 11, "passed": 0, "differences": 11, "errors": 0,
                               "compared_checkpoints": 11, "selected_specs": 1},
                   "rows": [{"step": n, "detail": "d"} for n in range(11)]}
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            entry.emit(payload, _JsonArgs())
        text = buffer.getvalue()
        report = json.loads(text)
        # 全部很短、总量远未超预算——上限**照样**要生效（这正是原先漏掉的情形）
        self.assertLessEqual(len(text.encode("utf-8")), OUTPUT_BUDGET, "输出超预算")
        items = [item for item in report["rows"] if not (isinstance(item, dict) and "omitted" in item)]
        omitted = [item for item in report["rows"] if isinstance(item, dict) and "omitted" in item]
        self.assertLessEqual(len(items), 10, f"预览条数超过 10：{len(items)}")
        self.assertEqual(len(omitted), 1, "没有报出省略条数")
        self.assertEqual(len(items) + omitted[0]["omitted"], 11, "省略条数对不上")
        self.assertTrue(report.get("details_truncated"), "裁剪没有被显式标注")

    def test_tool_error_message_is_bounded(self):
        """失败信息同样要有上限：错误消息可以很长。

        要**真的产生一条长错误**再验截断。用"适配器被列成生产文件"那类错误会先一步
        拦下，根本走不到超长消息，这条回归就变成名不副实。
        """
        broken = ROOT / ".local" / "tests" / "wow-addon-test" / "long-error"
        if broken.exists():
            shutil.rmtree(broken)
        broken.mkdir(parents=True)
        (broken / "adapter.lua").write_text(
            "return function(ctx) return {start=function()end,snapshot=function()end,stop=function()end} end",
            encoding="utf-8")
        long_name = "x" * 4000 + ".lua"       # 消息里会带上这个名字
        (broken / "wowtest.json").write_text(json.dumps({
            "schema_version": 1, "project_root": ".", "addon_name": "long-error",
            "adapter": "adapter.lua", "files": [long_name], "specs": "all",
            "components": ["health"], "require_cleanup": False, "timeout_seconds": 30},
            ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ENTRY), "run", "--config", str(broken / "wowtest.json"),
             "--output", str(broken / "out.json"), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, env=skill_env(),
        )
        self.assertNotEqual(result.returncode, 0, "缺文件竟然成功了")
        report = json.loads(result.stderr.strip().splitlines()[-1])
        self.assertEqual(report["status"], "tool_error")
        self.assertTrue(report.get("details_truncated"), "超长失败信息没有被标注截断")
        self.assertLessEqual(len(report["message"]), 2048 + 16, "失败信息本身没有上限")

    def test_small_outputs_are_never_truncated(self):
        """没超预算的命令不该被缩裁——否则代理会以为结果不完整。"""
        result = subprocess.run(
            [sys.executable, str(ENTRY), "validate", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, env=skill_env(),
        )
        self.assertEqual(result.returncode, 0, f"入口执行失败：{result.stderr[-400:]}")
        report = json.loads(result.stdout)
        self.assertNotIn("details_truncated", report, "小输出被误标为缩裁")
        self.assertEqual(report.get("cases"), 846, "用例总数不对")

    def test_tool_selftest_passes_in_the_repo(self):
        """工具自带的整套自检要在仓库里真跑一遍——否则它退化成一句没人执行的承诺。

        屏幕上的报告有条数上限（38 项会被截到 10 项），逐项明细走 `--output` 取——
        这里正好连"完整结果另有去处"这条路一起验了。
        """
        target = ROOT / ".local" / "tests" / "wow-addon-test" / "selftest-full.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, str(ENTRY), "selftest", "--json", "--output", str(target)],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            env=skill_env(),
        )
        self.assertEqual(result.returncode, 0, f"自检未通过：{result.stdout[-600:]}")
        report = json.loads(target.read_text(encoding="utf-8"))
        failed = [c["name"] for c in report["results"] if c["status"] != "pass"]
        self.assertEqual(failed, [], f"自检项失败：{failed}")
        self.assertEqual(report["passed"], report["checks"], "自检项数与通过数不一致")


# 技能文档不得把代理指向不存在的东西：读完照做就该能跑通。
PAYLOAD_DIRS = ("scripts", "assets", "references")
RETIRED_DIRS = ("data", "examples", "reference", "reports")
EXECUTABLE_SUFFIXES = (".py", ".cmd", ".bat", ".sh", ".exe")
PATH_TOKEN = re.compile(
    r"[A-Za-z0-9_][A-Za-z0-9_./\\<>-]*\.(?:py|cmd|bat|sh|exe|json|lua|md|txt)(?:\.gz)?")
# 占位前缀（如 <技能目录>/）剥掉后再判，否则真正的入口会被整条跳过、检查形同虚设
PLACEHOLDER = re.compile(r"^(?:<[^>]*>[\\/])+")
# 安装目标（往别的项目里放）与宿主环境路径：不属于技能载荷，本检查不裁决
OUTSIDE_PAYLOAD = (".", "wow-addon-test/", "github.com/", "www.")


def document_paths():
    """技能文档里出现的、形似「载荷内路径」的记号，按文档归拢。"""
    found = {}
    for path in sorted(SKILL.glob("references/*.md")) + [SKILL / "SKILL.md"]:
        tokens = set()
        for match in PATH_TOKEN.finditer(path.read_text(encoding="utf-8")):
            token = PLACEHOLDER.sub("", match.group(0).replace("\\", "/"))
            if token and not token.startswith(OUTSIDE_PAYLOAD):
                tokens.add(token)
        found[path.relative_to(SKILL).as_posix()] = sorted(tokens)
    return found


class DocumentedPathsTest(unittest.TestCase):
    """技能文档里承诺的路径必须真实存在，已退役的目录名不许再出现。"""

    def test_documented_payload_paths_exist(self):
        missing = []
        for doc, tokens in document_paths().items():
            for token in tokens:
                head = token.split("/")[0]
                if head in PAYLOAD_DIRS and not (SKILL / token).exists():
                    missing.append(f"{doc} → {token}")
                elif head in RETIRED_DIRS:
                    missing.append(f"{doc} → {token}（{head}/ 已退役）")
        self.assertEqual(missing, [], "技能文档指向了不存在的路径：\n" + "\n".join(missing))

    def test_documented_entry_points_exist(self):
        """文档给出的可执行入口必须真实存在——照抄就能跑，不留死命令。"""
        dead = []
        for doc, tokens in document_paths().items():
            for token in tokens:
                if not token.endswith(EXECUTABLE_SUFFIXES):
                    continue
                if token.split("/")[0] in RETIRED_DIRS:
                    continue  # 已由上面那条报出，不重复计数
                if not (SKILL / token).exists():
                    dead.append(f"{doc} → {token}")
        self.assertEqual(dead, [], "技能文档给出了不存在的命令入口：\n" + "\n".join(dead))


if __name__ == "__main__":
    unittest.main()
