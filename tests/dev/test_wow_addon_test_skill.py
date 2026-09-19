"""仓库内技能 wow-addon-test：布局与可用性。

只断言外部可观察行为：技能目录的形状、入口能否跑通、两个代理能否定位到同一份真身。
不触碰工具内部实现。
"""
import json
import re
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
        self.assertTrue(CLAUDE_LINK.exists(), f"Claude 侧连接不存在：{CLAUDE_LINK}")
        self.assertEqual(CLAUDE_LINK.resolve(), SKILL.resolve(), "连接未指向技能真身")
        self.assertTrue((CLAUDE_LINK / "SKILL.md").is_file(), "连接下入口不可达")

    def test_no_pointer_or_installer_residue(self):
        residue = sorted(
            p.relative_to(SKILL).as_posix()
            for p in SKILL.rglob("tool-location.json")
        )
        self.assertEqual(residue, [], "技能自包含后不应再有定位指针")

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
        )
        self.assertEqual(result.returncode, 0, f"入口执行失败：{result.stderr[-400:]}")
        report = json.loads(result.stdout)
        self.assertEqual(report.get("data_integrity"), "pass")


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
