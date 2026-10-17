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
    def test_unknown_build_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = json.loads((ROOT / 'projects/sim2gse/compatibility/lock.json').read_text())
            lock['build_protocol'] = 99
            target = root / 'projects/sim2gse/compatibility/lock.json'
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(lock), encoding='utf-8')
            with patch.object(engine, 'ROOT', root), self.assertRaisesRegex(ValueError, '构建协议'):
                engine.identity('baseline')

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
    'sim2gse_resource', 'sim2gse_actions_protocol', 'sim2gse_actions', 'sim2gse_static_snapshot',
    'sim2gse_apl_actions_protocol', 'sim2gse_apl_actions', 'sim2gse_precombat_actions',
    'sim2gse_items', 'sim2gse_actor_index', 'sim2gse_actor_name', 'sim2gse_owner_type',
    'sim2gse_availability_protocol', 'sim2gse_unavailable_actions', 'sim2gse_skipped_commands',
}


def combat_report(value):
    if isinstance(value, dict):
        return {key: combat_report(item) for key, item in value.items() if key not in REPORT_METADATA}
    if isinstance(value, list):
        return [combat_report(item) for item in value]
    return value


def battle_report(report):
    """只扣除构建时间与实际运行耗时；保留目标、全场效果和战斗汇总。"""
    result = combat_report(report)
    for key in ('build_date', 'build_time', 'timestamp'):
        result.pop(key, None)
    for key in ('elapsed_cpu_seconds', 'elapsed_time_seconds', 'init_time_seconds',
                'merge_time_seconds', 'analyze_time_seconds'):
        result['sim']['statistics'].pop(key, None)
    return result


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
            engine.reference(profile, folder / 'baseline', character, iterations=2,
                             simulation_config={'target_count': 1})
            engine.run(profile, folder / 'disabled', 'controlled', options=['iterations=2'],
                       simulation_config={'target_count': 1})
            original_folder = folder / 'original'
            original_folder.mkdir(parents=True)
            command = [str(original), str(profile), *engine.COMMON,
                       'desired_targets=1', 'iterations=2', 'max_time=180',
                       'json2=native.json', 'output=native.txt']
            result = subprocess.run(command, cwd=original_folder, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            reports = [json.loads((folder / mode / 'native.json').read_text(encoding='utf-8'))
                       for mode in ('original', 'baseline', 'disabled')]
            combat = [battle_report(report) for report in reports]
            self.assertEqual(combat[0], combat[1])
            self.assertEqual(combat[1], combat[2])


class NativeCatalogueTests(unittest.TestCase):
    def test_reference_uses_the_confirmed_live_client_data(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            native = engine.reference(profile, folder / 'reference',
                                      parse_character(sample_profile()), iterations=2)
            capabilities = engine.inspect(native, folder / 'capabilities')
            report = json.loads((folder / 'reference/native.json').read_text(encoding='utf-8'))
            dbc = report['sim']['options']['dbc']
            self.assertEqual(dbc['version_used'], 'Live')
            self.assertEqual(dbc['Live']['build_level'], 69933,
                             '角色目录仍使用旧客户端数据，未适配已核实的正式客户端')
            self.assertTrue(capabilities['actions'])
            snapshot = native['static_snapshot']
            self.assertIs(type(snapshot['parameters']['blightburst']), bool)
            if any(row['simc_action'] == 'soul_reaper' for row in capabilities['actions']):
                reapers = [row for row in snapshot['actions'] if row['name'] == 'soul_reaper']
                self.assertTrue(reapers, '可用灵魂收割必须提供真实静态参数供初始化CD示范')
                for row in reapers:
                    self.assertGreater(row['gcd_ms'], 0)
                    self.assertGreater(row['cooldown_ms'], 0)
            strikes = [row for row in snapshot['actions'] if row['spell_id'] == 85948]
            self.assertTrue(strikes)
            for row in strikes:
                self.assertEqual(row['gain_timing'], 'on_hit')
                self.assertEqual(row['gain_status'], 'known')
                self.assertGreater(row['gains']['runic_power'], 0)
            if snapshot['parameters']['festering_scythe']:
                scythes = [row for row in snapshot['actions'] if row['spell_id'] == 458128]
                self.assertTrue(scythes, '已构造的替换动作必须独立采集，不能继承基础按钮收益')
                for row in scythes:
                    self.assertEqual(row['gain_timing'], 'none')
                    self.assertEqual(row['gain_status'], 'known_zero')
                    self.assertEqual(row['gains'], {})
            for mode in ('baseline', 'controlled'):
                with self.subTest(mode=mode):
                    _, manifest = engine.identity(mode)
                    self.assertTrue({
                        'projects/sim2gse/native/src/catalogue.hpp',
                        'projects/sim2gse/native/src/catalogue.cpp',
                    }.issubset({entry['path'] for entry in manifest['sources']}),
                        '报告和目录尚未由共用、受身份校验的源码提供')

    def test_product_builds_use_the_final_hooks_without_the_historical_chain(self):
        for mode in ('baseline', 'controlled'):
            with self.subTest(mode=mode):
                _, manifest = engine.identity(mode)
                self.assertTrue(manifest['patches'])
                self.assertTrue(all(
                    Path(entry['path']).parent.as_posix() == 'projects/sim2gse/native/hooks'
                    for entry in manifest['patches']),
                    '产品仍依赖累计历史补丁链，尚未切换最终连接补丁')
