"""仓库升级入口的轻量公开命令检查，不启动模拟或训练。"""
import json
import contextlib
import io
import runpy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


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
        with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            postcheck = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
        error = io.StringIO()
        with patch.object(Path, 'read_text', return_value=json.dumps({'scenes': []})), \
                patch.object(sys, 'argv', ['postcheck.py', '--project', 'unused',
                                          '--data-project', 'unused', '--evidence', 'index.json']), \
                contextlib.redirect_stderr(error):
            self.assertEqual(postcheck['main'](), 2)
        self.assertIn('证据索引必须包含单目标及五目标', error.getvalue())

    def test_precheck_rejects_missing_project_without_creating_it(self):
        precheck = runpy.run_path(str(SCRIPTS / 'precheck.py'))
        missing = Path('missing-project')
        with patch.object(Path, 'is_dir', return_value=False), patch.object(Path, 'mkdir') as mkdir, \
                self.assertRaisesRegex(ValueError, '项目目录不存在'):
            precheck['prepare'](missing, missing)
        mkdir.assert_not_called()

    def test_precheck_rejects_foreign_repository(self):
        precheck = runpy.run_path(str(SCRIPTS / 'precheck.py'))
        error = io.StringIO()
        with patch.object(Path, 'is_dir', return_value=True), \
                patch.object(Path, 'is_file', return_value=False), \
                patch.object(sys, 'argv', ['precheck.py', '--project', 'foreign', '--data-project', 'foreign']), \
                contextlib.redirect_stderr(error):
            self.assertEqual(precheck['main'](), 2)
        self.assertIn('不是本仓库', error.getvalue())

    def test_postcheck_rejects_unreadable_index(self):
        with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            postcheck = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
        error = io.StringIO()
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError('absent.json')), \
                patch.object(sys, 'argv', ['postcheck.py', '--project', 'unused',
                                          '--data-project', 'unused', '--evidence', 'absent.json']), \
                contextlib.redirect_stderr(error):
            self.assertEqual(postcheck['main'](), 2)
        self.assertIn('升级后核验未通过', error.getvalue())


if __name__ == '__main__':
    unittest.main()
