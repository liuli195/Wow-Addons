"""构建身份公开入口：拒绝自有源码和构建清单变化。"""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'projects/sim2gse'))
import engine
from task import parse_character
from test_character_export import sample_profile


class NativeIdentityTests(unittest.TestCase):
    def test_changed_own_source_rejects_previously_built_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = json.loads((ROOT / 'projects/sim2gse/compatibility/lock.json').read_text())
            manifest = json.loads((ROOT / '.local/sim2gse/build/baseline/build.json').read_text())
            module = root / 'projects/sim2gse/native/modules/report.cpp'
            module.parent.mkdir(parents=True)
            module.write_bytes(b'// approved source\n')
            entry = dict(path='projects/sim2gse/native/modules/report.cpp',
                         destination='engine/sim2gse/report.cpp', modes=['baseline', 'controlled'],
                         sha256=hashlib.sha256(module.read_bytes()).hexdigest())
            lock['sources'] = [entry]
            manifest['sources'] = [entry]
            for item in lock['baseline_patches']:
                target = root / item['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / item['path']).read_bytes())
            executable = root / '.tools/sim2gse/product/baseline/engine/simc.exe'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'fixture executable')
            manifest['binary_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
            for name, value in [('projects/sim2gse/compatibility/lock.json', lock),
                                ('.local/sim2gse/build/baseline/build.json', manifest)]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(value), encoding='utf-8')
            module.write_bytes(b'// unreviewed change\n')
            with patch.object(engine, 'ROOT', root), self.assertRaisesRegex(ValueError, '源码'):
                engine.identity('baseline')
            module.write_bytes(b'// approved source\n')
            manifest['sources'] = []
            (root / '.local/sim2gse/build/baseline/build.json').write_text(json.dumps(manifest), encoding='utf-8')
            with patch.object(engine, 'ROOT', root), self.assertRaisesRegex(ValueError, '源码清单'):
                engine.identity('baseline')

    def test_original_remains_a_verification_artifact_only(self):
        with self.assertRaisesRegex(ValueError, '未知引擎模式'):
            engine.identity('original')


# 仅移除本项目明确添加的报告字段；战斗数据逐值比较。
REPORT_METADATA = {
    'sim2gse_class', 'sim2gse_class_id', 'sim2gse_spec_id', 'sim2gse_spec',
    'sim2gse_resource', 'sim2gse_actions_protocol', 'sim2gse_actions',
    'sim2gse_apl_actions_protocol', 'sim2gse_apl_actions', 'sim2gse_precombat_actions',
    'sim2gse_items', 'sim2gse_actor_index', 'sim2gse_actor_name', 'sim2gse_owner_type',
}


def combat_report(value):
    if isinstance(value, dict):
        return {key: combat_report(item) for key, item in value.items() if key not in REPORT_METADATA}
    if isinstance(value, list):
        return [combat_report(item) for item in value]
    return value


class NativeComparisonTests(unittest.TestCase):
    def test_original_baseline_and_disabled_controller_keep_native_combat(self):
        manifest = json.loads((ROOT / '.local/sim2gse/build/original/build.json').read_text())
        original = ROOT / manifest['executable']
        self.assertEqual(manifest['exit_code'], 0)
        self.assertEqual(manifest['patches'], [])
        self.assertEqual(manifest['sources'], [])
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), manifest['binary_sha256'])
        _, baseline_identity = engine.identity('baseline')
        _, controlled_identity = engine.identity('controlled')
        for key in ('upstream_commit', 'upstream_tree', 'build_options', 'compiler_sha256'):
            self.assertEqual(manifest[key], baseline_identity[key])
            self.assertEqual(manifest[key], controlled_identity[key])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            character = parse_character(sample_profile())
            for targets in (1, 5):
                with self.subTest(targets=targets):
                    scene = folder / str(targets)
                    engine.reference(profile, scene / 'baseline', character, iterations=2,
                                     simulation_config={'target_count': targets})
                    engine.run(profile, scene / 'disabled', 'controlled', options=['iterations=2'],
                               simulation_config={'target_count': targets})
                    original_folder = scene / 'original'
                    original_folder.mkdir(parents=True)
                    command = [str(original), str(profile), *engine.COMMON,
                               f'desired_targets={targets}', 'iterations=2', 'max_time=180',
                               'json2=native.json', 'output=native.txt']
                    result = subprocess.run(command, cwd=original_folder, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    reports = [json.loads((scene / mode / 'native.json').read_text(encoding='utf-8'))
                               for mode in ('original', 'baseline', 'disabled')]
                    players = [combat_report(report['sim']['players']) for report in reports]
                    self.assertEqual(players[0], players[1])
                    self.assertEqual(players[1], players[2])
