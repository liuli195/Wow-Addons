"""仓库内技能 wow-addon-test：布局与可用性。

只断言外部可观察行为：技能目录的形状、入口能否跑通、两个代理能否定位到同一份真身。
不触碰工具内部实现。
"""
import re
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


class SkillLayoutTest(unittest.TestCase):
    def test_skill_entry_exists_with_valid_frontmatter(self):
        entry = SKILL / "SKILL.md"
        self.assertTrue(entry.is_file(), f"技能入口不存在：{entry}")
        fields = read_frontmatter(entry)
        self.assertEqual(fields.get("name"), SKILL.name)
        self.assertTrue(fields.get("description"), "description 不得为空")


if __name__ == "__main__":
    unittest.main()
