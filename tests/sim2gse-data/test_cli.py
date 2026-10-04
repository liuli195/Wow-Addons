"""从真实命令行入口验证数据管理；测试根全部为临时合成目录。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid


CLI = Path(__file__).resolve().parents[2] / ".agents/skills/sim2gse-data/scripts/simdata.py"


class SharedEntryTests(unittest.TestCase):
    def test_managed_root_outputs_are_ignored_only_at_repository_root(self):
        repository = CLI.parents[4]
        managed_paths = (".simdata-root.json", ".manager.lock", "index.sqlite3", "index.sqlite3-wal",
                         "index.sqlite3-shm", "index.sqlite3-journal", ".archives/", ".backups/",
                         ".staging/", ".quarantine/", "runs/")
        for relative in managed_paths:
            with self.subTest(path=relative):
                result = subprocess.run(["git", "check-ignore", "-q", "--no-index", relative], cwd=repository)
                self.assertEqual(result.returncode, 0, f"repository-root management path not ignored: {relative}")
        nested = subprocess.run(["git", "check-ignore", "-q", "--no-index", "tests/.simdata-root.json"], cwd=repository)
        self.assertEqual(nested.returncode, 1, "the ignore rules must not become a recursive exclusion framework")

    def test_copied_minimal_runtime_works_without_repository_or_tests(self):
        with tempfile.TemporaryDirectory(prefix="simdata portable runtime ") as directory:
            skill = Path(directory) / "copied skill"
            shutil.copytree(CLI.parent.parent, skill)
            files = {path.relative_to(skill).as_posix() for path in skill.rglob("*") if path.is_file()}
            self.assertEqual(files, {"SKILL.md", "scripts/simdata.py", "assets/config.default.json"})
            entry = skill / "scripts/simdata.py"
            working = Path(directory) / "other working directory"
            working.mkdir()
            config = Path(directory) / "machine.json"
            root = Path(directory) / "data root"
            policy = json.loads((skill / "assets/config.default.json").read_text(encoding="utf-8"))
            policy.update(mode="test", root_id=str(uuid.uuid4()), data_root=str(root),
                          capacity_bytes=4 * 1024 * 1024, retention_days=1, maintenance_interval_hours=1,
                          maintenance_reserve_bytes=65536, archive_part_bytes=65536,
                          metadata_reserve_bytes=131072, lease_seconds=1)
            config.write_text(json.dumps(policy), encoding="utf-8")
            def invoke(*arguments):
                result = subprocess.run([sys.executable, "-B", str(entry), *arguments], cwd=working,
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                return result
            self.assertIn("usage:", invoke("--help").stdout)
            preview = json.loads(invoke("init-root", "--config", str(config)).stdout)
            invoke("init-root", "--config", str(config), "--approve-hash", preview["plan_hash"])
            source = root / "native.json"
            source.write_bytes(b'{"synthetic":true}')
            arguments = ("register", "--config", str(config), "--path", str(source), "--role", "native")
            preview = json.loads(invoke(*arguments).stdout)
            registered = json.loads(invoke(*arguments, "--approve-hash", preview["plan_hash"]).stdout)
            resolved = json.loads(invoke("resolve", "--config", str(config), "--artifact-id",
                                         registered["artifact_id"], "--inspect").stdout)
            self.assertEqual(Path(resolved["path"]).read_bytes(), source.read_bytes())

    def call(self, *arguments, cwd=None):
        return subprocess.run([sys.executable, "-B", str(CLI), *arguments],
                              cwd=cwd, capture_output=True, text=True, encoding="utf-8")



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

    def test_write_preflight_explains_disabled_and_requires_root_identity(self):
        with tempfile.TemporaryDirectory(prefix="simdata policy ") as directory:
            root = Path(directory)
            disabled = self.call("check-config", "--root", str(root), "--for-write")
            self.assertEqual(disabled.returncode, 2)
            self.assertIn("生产管理未启用", json.loads(disabled.stderr)["error"])
            config = root / "machine.json"
            config.write_text(json.dumps({"schema_version": 1, "production_enabled": True}), encoding="utf-8")
            incomplete = self.call("check-config", "--root", str(root), "--config", str(config), "--for-write")
            self.assertEqual(incomplete.returncode, 2)
            self.assertIn("数据根身份", json.loads(incomplete.stderr)["error"])
            self.assertEqual(list(root.iterdir()), [config])

    def test_on_demand_root_metadata_actions_allow_unset_long_term_policy(self):
        with tempfile.TemporaryDirectory(prefix="simdata unset policies ") as directory:
            base = Path(directory)
            root = base / "synthetic managed root"
            root.mkdir()
            config = base / "synthetic config.json"
            policy = json.loads((CLI.parent.parent / "assets" / "config.default.json").read_text(encoding="utf-8"))
            policy.update(mode="production", production_enabled=True, root_id=str(uuid.uuid4()), data_root=str(root))
            config.write_text(json.dumps(policy), encoding="utf-8")

            def invoke(*arguments, expected=0):
                result = subprocess.run([sys.executable, "-B", str(CLI), *arguments, "--config", str(config)],
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, expected, result.stderr)
                return json.loads(result.stdout if expected == 0 else result.stderr)

            checked = invoke("check-config", "--for-write")
            self.assertTrue(checked["production_enabled"])
            plan = invoke("init-root")
            invoke("init-root", "--approve-hash", plan["plan_hash"])
            source = root / "native.json"
            source.write_bytes(b'{"synthetic":true}')
            registration = invoke("register", "--path", str(source), "--role", "native")
            artifact = invoke("register", "--path", str(source), "--role", "native",
                              "--approve-hash", registration["plan_hash"])
            invoke("pin", "--artifact-id", artifact["artifact_id"], "--label", "keep", "--action", "add")
            invoke("reference", "--artifact-id", artifact["artifact_id"], "--owner", "synthetic-reader",
                   "--kind", "durable", "--action", "add")
            resolved = invoke("resolve", "--artifact-id", artifact["artifact_id"])
            self.assertEqual(Path(resolved["path"]).read_bytes(), source.read_bytes())
            status = invoke("status")
            for key in ("capacity_bytes", "retention_days", "maintenance_interval_hours",
                        "maintenance_reserve_bytes", "metadata_reserve_bytes"):
                self.assertIsNone(status[key])
            missing_lease = invoke("begin", "--request-id", "missing-lease", "--owner-pid", str(os.getpid()),
                                   "--reserve-bytes", "1024", expected=2)
            self.assertIn("lease_seconds", missing_lease["error"])
            missing_part = invoke("archive", "--artifact-id", artifact["artifact_id"], expected=2)
            self.assertIn("archive_part_bytes", missing_part["error"])

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

    def test_inventory_reports_directory_symlinks_without_following_them(self):
        with tempfile.TemporaryDirectory(prefix="simdata root links ") as directory:
            base = Path(directory)
            root = base / "data"
            target = base / "outside"
            root.mkdir()
            target.mkdir()
            (root / "inside.json").write_bytes(b"inside")
            (target / "external.json").write_bytes(b"outside")
            link = root / "external skills"
            link.symlink_to(target, target_is_directory=True)

            result = self.call("inventory", "--root", str(root), "--complete")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual((report["files"], report["logical_bytes"]), (1, 6))
            self.assertEqual(report["skipped_directory_links_count"], 1)
            self.assertEqual(report["skipped_directory_links"], ["external skills"])
            self.assertFalse(report["skipped_directory_links_truncated"])

    def test_incremental_inventory_reports_directory_symlinks_without_following_them(self):
        with tempfile.TemporaryDirectory(prefix="simdata incremental links ") as directory:
            base = Path(directory)
            root = base / "data"
            target = base / "outside"
            root.mkdir()
            target.mkdir()
            (target / "external.json").write_bytes(b"outside")
            (root / "z-inside.json").write_bytes(b"inside")
            (root / "a-external").symlink_to(target, target_is_directory=True)

            first = self.call("inventory", "--root", str(root), "--incremental", "--limit", "1")

            self.assertEqual(first.returncode, 0, first.stderr)
            first_report = json.loads(first.stdout)
            self.assertEqual(first_report["skipped_directory_links_count"], 1)
            self.assertEqual(first_report["skipped_directory_links"], ["a-external"])
            second = self.call("inventory", "--root", str(root), "--incremental", "--limit", "1",
                               "--cursor", first_report["next_cursor"])
            self.assertEqual(second.returncode, 0, second.stderr)
            second_report = json.loads(second.stdout)
            self.assertEqual((second_report["files"], second_report["logical_bytes"]), (1, 6))
            self.assertEqual(second_report["skipped_directory_links_count"], 0)

    def test_metadata_write_peak_is_checked_in_addition_to_configured_reserve(self):
        with tempfile.TemporaryDirectory(prefix="simdata metadata peak ") as directory:
            base = Path(directory)
            root = base / "data"
            config = base / "machine.json"
            policy = json.loads((CLI.parent.parent / "assets" / "config.default.json").read_text(encoding="utf-8"))
            policy.update(mode="test", root_id=str(uuid.uuid4()), data_root=str(root), capacity_bytes=4 * 1024 * 1024,
                          metadata_reserve_bytes=1)
            config.write_text(json.dumps(policy), encoding="utf-8")

            def invoke(*arguments):
                result = subprocess.run([sys.executable, "-B", str(CLI), *arguments, "--config", str(config)],
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            plan = invoke("init-root")
            invoke("init-root", "--approve-hash", plan["plan_hash"])
            source = root / "native.json"
            source.write_bytes(b"synthetic")
            registration = invoke("register", "--path", str(source), "--role", "native")
            artifact = invoke("register", "--path", str(source), "--role", "native",
                              "--approve-hash", registration["plan_hash"])
            code = ("import shutil,sys,runpy\nfrom types import SimpleNamespace\n"
                    "shutil.disk_usage=lambda _: SimpleNamespace(total=1,used=0,free=1)\n"
                    "path=sys.argv[1]; sys.argv=[path,*sys.argv[2:]]; runpy.run_path(path,run_name='__main__')")
            result = subprocess.run([sys.executable, "-B", "-c", code, str(CLI), "pin", "--config", str(config),
                                     "--artifact-id", artifact["artifact_id"], "--label", "keep", "--action", "add"],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("所在卷可用空间不足", json.loads(result.stderr)["error"])


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
                disabled = invoke(entry, "schedule-preview", "--config", str(config), "--python", str(Path(sys.executable).resolve()))
                self.assertEqual(disabled.returncode, 0, disabled.stderr)
                self.assertIsNone(json.loads(disabled.stdout)["xml"])
                self.assertFalse(json.loads(disabled.stdout)["installed"])
            refused = invoke(direct, "inventory", "--root", str(link))
            self.assertEqual(refused.returncode, 2)
            self.assertIn("重解析点", json.loads(refused.stderr)["error"])
            inner = invoke(direct, "inventory", "--root", str(repository))
            self.assertEqual(inner.returncode, 0, inner.stderr)
            inner_report = json.loads(inner.stdout)
            self.assertEqual(inner_report["skipped_directory_links_count"], 1)
            self.assertEqual(inner_report["skipped_directory_links"], [".claude/skills/sim2gse-data"])
            for path in (str(link) + "\\..", str(link) + "/../"):
                result = self.call("status", "--root", path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("上级路径", json.loads(result.stderr)["error"])
            link.rename(data / "index.sqlite3")
            result = self.call("status", "--root", str(data))
            self.assertEqual(result.returncode, 2)
            self.assertIn("重解析点", json.loads(result.stderr)["error"])

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
