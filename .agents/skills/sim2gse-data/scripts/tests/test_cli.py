"""从真实命令行入口验证数据管理；测试根全部为临时合成目录。"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "simdata.py"


class SharedEntryTests(unittest.TestCase):
    def call(self, *arguments, cwd=None):
        return subprocess.run([sys.executable, "-B", str(CLI), *arguments],
                              cwd=cwd, capture_output=True, text=True, encoding="utf-8")

    @unittest.skipUnless(sys.platform == "win32", "Windows目录联接行为")
    def test_parent_components_cannot_hide_a_junction(self):
        with tempfile.TemporaryDirectory(prefix="simdata parent ") as directory:
            repository = Path(directory) / "repo"
            skill = repository / ".agents" / "skills" / "sim2gse-data"
            shutil.copytree(CLI.parent.parent, skill)
            entry = skill / "scripts" / "simdata.py"
            installed = subprocess.run([sys.executable, "-B", str(entry), "install-junction",
                                        "--repository", str(repository), "--apply"],
                                       capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(installed.returncode, 0, installed.stderr)
            link = repository / ".claude" / "skills" / "sim2gse-data"
            for path in (str(link) + "\\..", str(link) + "/../"):
                result = self.call("status", "--root", path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("上级路径", json.loads(result.stderr)["error"])

    @unittest.skipUnless(sys.platform == "win32", "Windows目录联接行为")
    def test_status_rejects_a_link_at_the_known_index_endpoint(self):
        with tempfile.TemporaryDirectory(prefix="simdata index link ") as directory:
            repository = Path(directory) / "repo"
            skill = repository / ".agents" / "skills" / "sim2gse-data"
            shutil.copytree(CLI.parent.parent, skill)
            installed = subprocess.run([sys.executable, "-B", str(skill / "scripts" / "simdata.py"),
                                        "install-junction", "--repository", str(repository), "--apply"],
                                       capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(installed.returncode, 0, installed.stderr)
            data = Path(directory) / "data"
            data.mkdir()
            (repository / ".claude" / "skills" / "sim2gse-data").rename(data / "index.sqlite3")
            result = self.call("status", "--root", str(data))
            self.assertEqual(result.returncode, 2)
            self.assertIn("重解析点", json.loads(result.stderr)["error"])

    def test_status_reports_disabled_unset_policy_without_creating_an_index(self):
        with tempfile.TemporaryDirectory(prefix="simdata status ") as directory:
            root = Path(directory)
            result = self.call("status", "--root", str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["production_enabled"])
            self.assertIsNone(report["capacity_bytes"])
            self.assertIsNone(report["retention_days"])
            self.assertIsNone(report["maintenance_interval_hours"])
            self.assertFalse(report["index_present"])
            self.assertEqual(list(root.iterdir()), [])

    def test_write_preflight_explains_disabled_and_incomplete_policy(self):
        with tempfile.TemporaryDirectory(prefix="simdata policy ") as directory:
            root = Path(directory)
            disabled = self.call("check-config", "--root", str(root), "--for-write")
            self.assertEqual(disabled.returncode, 2)
            self.assertIn("生产管理未启用", json.loads(disabled.stderr)["error"])
            config = root / "machine.json"
            config.write_text(json.dumps({"schema_version": 1, "production_enabled": True}), encoding="utf-8")
            incomplete = self.call("check-config", "--root", str(root), "--config", str(config), "--for-write")
            self.assertEqual(incomplete.returncode, 2)
            self.assertIn("生产策略未完整配置", json.loads(incomplete.stderr)["error"])
            self.assertEqual(list(root.iterdir()), [config])

    def test_invalid_config_root_is_rejected_without_a_traceback(self):
        with tempfile.TemporaryDirectory(prefix="simdata invalid ") as directory:
            config = Path(directory) / "machine.json"
            config.write_text('{"data_root": true}', encoding="utf-8")
            result = self.call("status", "--root", directory, "--config", str(config))
            self.assertEqual(result.returncode, 2)
            self.assertIn("data_root", json.loads(result.stderr)["error"])

    def test_relative_config_is_rejected_from_each_working_directory(self):
        with tempfile.TemporaryDirectory(prefix="simdata config cwd ") as directory:
            for name in ("first", "second"):
                working = Path(directory) / name
                working.mkdir()
                data = working / "data"
                data.mkdir()
                (working / "machine.json").write_text(json.dumps({"data_root": str(data)}), encoding="utf-8")
                result = self.call("status", "--config", "machine.json", cwd=working)
                self.assertEqual(result.returncode, 2)
                self.assertIn("配置须使用绝对路径", json.loads(result.stderr)["error"])

    def test_nul_in_configured_root_returns_a_structured_path_error(self):
        with tempfile.TemporaryDirectory(prefix="simdata nul ") as directory:
            config = Path(directory) / "machine.json"
            config.write_text(json.dumps({"data_root": str(Path(directory) / "bad\x00name")}), encoding="utf-8")
            result = self.call("status", "--config", str(config))
            self.assertEqual(result.returncode, 2)
            self.assertIn("NUL", json.loads(result.stderr)["error"])
            self.assertEqual(list(Path(directory).iterdir()), [config])

    def test_inventory_limit_relative_root_and_root_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="simdata bounded ") as directory:
            root = Path(directory) / "data"
            root.mkdir()
            for name in ("a", "b", "c"):
                (root / name).write_bytes(b"synthetic")
            report = json.loads(self.call("inventory", "--root", str(root), "--limit", "1").stdout)
            self.assertTrue(report["truncated"])
            self.assertEqual(report["files"], 1)
            self.assertEqual(report["logical_bytes"], 9)
            relative = self.call("inventory", "--root", "data", cwd=directory)
            self.assertEqual(relative.returncode, 2)
            self.assertIn("绝对", json.loads(relative.stderr)["error"])
            config = Path(directory) / "machine.json"
            config.write_text(json.dumps({"data_root": directory}), encoding="utf-8")
            mismatch = self.call("status", "--root", str(root), "--config", str(config))
            self.assertEqual(mismatch.returncode, 2)
            self.assertIn("不一致", json.loads(mismatch.stderr)["error"])


    @unittest.skipUnless(sys.platform == "win32", "Windows目录联接行为")
    def test_install_preview_apply_and_both_agent_entries_share_one_skill(self):
        with tempfile.TemporaryDirectory(prefix="simdata 双宿主 ") as directory:
            repository = Path(directory) / "合成 repo"
            skill = repository / ".agents" / "skills" / "sim2gse-data"
            shutil.copytree(CLI.parent.parent, skill)
            direct = skill / "scripts" / "simdata.py"
            link = repository / ".claude" / "skills" / "sim2gse-data"
            def invoke(entry, *arguments):
                return subprocess.run([sys.executable, "-B", str(entry), *arguments],
                                      cwd=directory, capture_output=True, text=True, encoding="utf-8")
            preview = invoke(direct, "install-junction", "--repository", str(repository))
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertFalse(link.exists())
            for _ in range(2):
                installed = invoke(direct, "install-junction", "--repository", str(repository), "--apply")
                self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertTrue(link.is_junction())
            data = Path(directory) / "合成 data"
            data.mkdir()
            (data / "native.json").write_bytes(b"synthetic")
            reports = [json.loads(invoke(entry, "inventory", "--root", str(data)).stdout)
                       for entry in (direct, link / "scripts" / "simdata.py")]
            self.assertEqual(reports[0], reports[1])
            config = Path(directory) / "machine with spaces.json"
            config.write_text(json.dumps(dict(data_root=str(data))), encoding="utf-8")
            for entry in (direct, link / "scripts" / "simdata.py"):
                disabled = invoke(entry, "schedule-preview", "--config", str(config), "--python", sys.executable)
                self.assertEqual(disabled.returncode, 0, disabled.stderr)
                self.assertIsNone(json.loads(disabled.stdout)["xml"])
                self.assertFalse(json.loads(disabled.stdout)["installed"])
            refused = invoke(direct, "inventory", "--root", str(link))
            self.assertEqual(refused.returncode, 2)
            self.assertIn("重解析点", json.loads(refused.stderr)["error"])
            inner = invoke(direct, "inventory", "--root", str(repository))
            self.assertEqual(inner.returncode, 2)
            self.assertIn("重解析点", json.loads(inner.stderr)["error"])

    @unittest.skipUnless(sys.platform == "win32", "Windows目录联接行为")
    def test_install_never_overwrites_an_existing_unrelated_directory(self):
        with tempfile.TemporaryDirectory(prefix="simdata no overwrite ") as directory:
            repository = Path(directory) / "repo"
            skill = repository / ".agents" / "skills" / "sim2gse-data"
            shutil.copytree(CLI.parent.parent, skill)
            unrelated = repository / ".claude" / "skills" / "sim2gse-data"
            unrelated.mkdir(parents=True)
            kept = unrelated / "keep.txt"
            kept.write_text("synthetic user file", encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(skill / "scripts" / "simdata.py"),
                                     "install-junction", "--repository", str(repository), "--apply"],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 2)
            self.assertIn("不覆盖", json.loads(result.stderr)["error"])
            self.assertEqual(kept.read_text(encoding="utf-8"), "synthetic user file")

    def test_inventory_from_another_working_directory_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="simdata 合成 data ") as directory:
            root = Path(directory) / "受管 root"
            root.mkdir()
            (root / "native.json").write_bytes(b'{"synthetic": true}')
            (root / "nested").mkdir()
            (root / "nested" / "input.simc").write_bytes(b"synthetic")
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            result = subprocess.run(
                [sys.executable, "-B", str(CLI), "inventory", "--root", str(root)],
                cwd=Path(directory), capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["files"], 2)
            self.assertEqual(report["logical_bytes"], 28)
            self.assertFalse(report["production_enabled"])
            self.assertTrue(report["unknown_data_protected"])
            self.assertEqual(before, sorted(str(path.relative_to(root)) for path in root.rglob("*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
