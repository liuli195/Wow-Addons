"""仓库升级入口的轻量公开命令检查，不启动模拟或训练。"""
import json
import contextlib
import io
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/sim2gse-upgrade/scripts'


class UpgradeSkillTests(unittest.TestCase):
    def test_page_batch_sizes_follow_cumulative_targets(self):
        sys.path.insert(0, str(SCRIPTS))
        try:
            module = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
            self.assertEqual(module['search_batch_sizes']([32, 128, 256]), {32, 96, 128})
            self.assertEqual(module['search_batch_sizes']([2]), {2})
        finally:
            sys.path.remove(str(SCRIPTS))

    def test_postcheck_rejects_incomplete_index_before_loading_project(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / 'index.json'
            index.write_text(json.dumps({'scenes': []}), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPTS / 'postcheck.py'),
                                     '--project', directory, '--data-project', directory,
                                     '--evidence', str(index)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('证据索引必须包含单目标及五目标', result.stderr)

    def test_precheck_rejects_missing_project_without_creating_it(self):
        precheck = runpy.run_path(str(SCRIPTS / 'precheck.py'))
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing'
            with self.assertRaisesRegex(ValueError, '项目目录不存在'):
                precheck['prepare'](missing, missing)
            self.assertFalse(missing.exists())

    def test_precheck_rejects_foreign_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(SCRIPTS / 'precheck.py'),
                                     '--project', directory, '--data-project', directory],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('不是本仓库', result.stderr)

    def test_postcheck_rejects_unreadable_index(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            postcheck = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
            error = io.StringIO()
            arguments = [str(SCRIPTS / 'postcheck.py'), '--project', directory,
                         '--data-project', directory, '--evidence', str(Path(directory) / 'absent.json')]
            with patch.object(sys, 'argv', arguments), contextlib.redirect_stderr(error):
                self.assertEqual(postcheck['main'](), 2)
            self.assertIn('升级后核验未通过', error.getvalue())


if __name__ == '__main__':
    unittest.main()
