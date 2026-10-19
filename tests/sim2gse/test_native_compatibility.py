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
from sequence import evaluate
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
            module = root / 'projects/sim2gse/native/modules/report.cpp'
            module.parent.mkdir(parents=True)
            module.write_bytes(b'// approved source\n')
            entry = dict(path='projects/sim2gse/native/modules/report.cpp',
                         destination='engine/sim2gse/report.cpp', modes=['baseline', 'controlled'],
                         sha256=hashlib.sha256(module.read_bytes()).hexdigest())
            lock = dict(build_protocol=2, sources=[entry])
            manifest = dict(sources=[entry])
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
    'sim2gse_rule_observations',
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
            native = engine.reference(profile, folder / 'baseline', character, iterations=2,
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
            capabilities = engine.inspect(native, folder / 'capabilities')
            report = reports[1]
            dbc = report['sim']['options']['dbc']
            self.assertEqual(dbc['version_used'], 'Live')
            self.assertEqual(dbc['Live']['build_level'], 69933,
                             '角色目录仍使用旧客户端数据，未适配已核实的正式客户端')
            self.assertTrue(capabilities['actions'])
            snapshot = native['static_snapshot']
            self.assertIs(type(snapshot['parameters']['blightburst']), bool)
            for row in snapshot['actions']:
                if row['gain_status'] == 'known':
                    self.assertTrue(row['gains'], row['name'] + ' 已知直接收益不能丢失资源条目')
            original_actions = {'outbreak', 'putrefy', 'death_and_decay', 'death_coil',
                                'epidemic', 'festering_strike', 'festering_scythe',
                                'scourge_strike', 'soul_reaper'}
            available = {row['simc_action'] for row in capabilities['actions']}
            for name in original_actions & available:
                rows = [row for row in snapshot['actions'] if row['name'] == name]
                self.assertTrue(rows, name + ' 缺少原生静态参数')
                for row in rows:
                    for field in ('gcd_ms', 'cooldown_ms', 'cast_ms'):
                        self.assertGreaterEqual(row[field], 0, (name, field, row.get('unknown')))
                    self.assertIsInstance(row['costs'], dict)
                    self.assertIsInstance(row['gains'], dict)
                    self.assertEqual(row['gain_scope'], 'direct_action')
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
            for mode, manifest in (('baseline', baseline_identity), ('controlled', controlled_identity)):
                with self.subTest(mode=mode):
                    self.assertTrue({
                        'projects/sim2gse/native/src/catalogue.hpp',
                        'projects/sim2gse/native/src/catalogue.cpp',
                    }.issubset({entry['path'] for entry in manifest['sources']}),
                        '报告和目录尚未由共用、受身份校验的源码提供')
                    self.assertTrue(manifest['patches'])
                    self.assertTrue(all(
                        Path(entry['path']).parent.as_posix() == 'projects/sim2gse/native/hooks'
                        for entry in manifest['patches']),
                        '产品仍依赖累计历史补丁链，尚未切换最终连接补丁')


class NativeObservationTests(unittest.TestCase):
    def test_requested_dots_keep_real_component_lifetimes_and_actual_target_applicability(self):
        outbreak = dict(kind='spell', spell_id=77575, name='Outbreak', simc_action='outbreak')
        putrefy = dict(kind='spell', spell_id=1247378, name='Putrefy', simc_action='putrefy')
        commands = [outbreak, outbreak, outbreak, putrefy]
        candidate = dict(blocks=[[row] for row in commands],
                         compiled_steps=[dict(type='spell', spell=row['spell_id']) for row in commands])
        request = dict(protocol=1, objects={
            'application': dict(kind='action', native_action='putrefy', base_button='putrefy'),
            'application_enabled': dict(kind='state',
                native_identity='native.putrefy.disease_application_qualification'),
            'single': dict(kind='target_scope', value='current_attack_target'),
            'enemies': dict(kind='target_scope', value='all_currently_engaged_required_targets'),
            'diseases': dict(kind='effect', from_action='application', qualification='application_enabled',
                components=[dict(native_identity='virulent_plague', target_scope='enemies'),
                            dict(native_identity='dread_plague', target_scope='single')]),
            'missing': dict(kind='effect', components=[
                dict(native_identity='unresolved_native_dot', target_scope='enemies')]),
        })
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            options = dict(character=parse_character(sample_profile()), iterations=2, trace=False,
                           input_times=[0, 1500, 179000], simulation_config={'target_count': 2})
            observed = evaluate(profile, candidate, folder / 'observed', **options,
                                rule_observation_request=request)
            quiet = evaluate(profile, candidate, folder / 'quiet', **options)
            self.assertEqual(battle_report(observed['report']), battle_report(quiet['report']))
            facts = observed['report']['sim']['players'][0]['sim2gse_rule_observations']
            events = [row for row in facts['effect_events'] if row['object'] == 'diseases']
            self.assertTrue(events, '请求Dot的真实生命周期尚未进入同次效果事件')
            actor = facts['scope']['controlled_actor_index']
            target = facts['inputs'][0]['target_scopes']['single'][0]['target_id']
            enemies = {row['target_id'] for row in facts['inputs'][0]['target_scopes']['enemies']}
            applied = [row for row in events if row['kind'] == 'apply']
            self.assertEqual({(row['component_id'], row['target_id']) for row in applied},
                             {('virulent_plague', enemy) for enemy in enemies} | {('dread_plague', target)})
            self.assertTrue(all(row['sample_id'] == 1 and row['source_id'] == actor for row in events))
            self.assertTrue(all(row['source_input_index'] is None for row in applied),
                            'Dot边沿不能猜测异步应用来自最近输入')
            for component, owner in {('virulent_plague', enemy) for enemy in enemies} | {('dread_plague', target)}:
                component_events = [row for row in events if row['component_id'] == component and row['target_id'] == owner]
                first = next(row for row in component_events if row['kind'] == 'apply')
                refreshed = next(row for row in component_events if row['kind'] == 'refresh')
                self.assertEqual(refreshed['instance_id'], first['instance_id'])
                self.assertGreater(refreshed['scheduled_end'], first['scheduled_end'])
                expired = next(row for row in component_events if row['end_reason'] == 'expired')
                self.assertEqual(expired['instance_id'], first['instance_id'])
                self.assertEqual(expired['stacks'], 0)
                late = [row for row in component_events if row['kind'] == 'apply' and row['time'] > 170000]
                self.assertEqual(len(late), 1)
                closed = [row for row in component_events if row['instance_id'] == late[0]['instance_id']
                          and row['end_reason'] is not None]
                self.assertEqual(len(closed), 1)
                self.assertEqual(closed[0]['end_reason'], 'simulation_end')
                self.assertEqual(closed[0]['end'], facts['scope']['end_ms'])
                self.assertTrue(all(row['lifecycle_complete'] is True for row in component_events))
            self.assertIs(facts['scope']['effect_events_complete']['diseases'], True)
            self.assertIs(facts['scope']['effect_events_complete']['missing'], False)
            states = [row for row in facts['state_observations'] if row['object'] == 'application_enabled']
            self.assertTrue(states and all(row['value'] is True for row in states))
            snapshots = [row for row in facts['effect_observations'] if row['object'] == 'diseases'
                         and row['input_index'] == 1 and row['target_id'] in enemies]
            self.assertTrue(all(row['applicable'] is True for row in snapshots if row['active'] is True))
            excluded = [row for row in snapshots if row['component_id'] == 'dread_plague' and row['target_id'] != target]
            self.assertTrue(excluded and all(row['applicable'] is False for row in excluded))

    def test_audited_synchronous_effect_estimate_keeps_effect_identity_and_excludes_gcd_tail(self):
        commands = [dict(kind='spell', spell_id=spell, name=name, simc_action=name)
                    for name, spell in [('festering_strike', 85948), ('festering_strike', 85948),
                                        ('putrefy', 1247378)]]
        candidate = dict(blocks=[[row] for row in commands],
                         compiled_steps=[dict(type='spell', spell=row['spell_id']) for row in commands])
        request = dict(protocol=1, objects={
            'button': dict(kind='action', native_action='festering_strike', base_button='festering_strike'),
            'form': dict(kind='action', native_action='festering_scythe', base_button='festering_strike'),
            'delayed_action': dict(kind='action', native_action='putrefy', base_button='putrefy'),
            'impact': dict(kind='effect', native_identity='festering_scythe_tt'),
            'scythe_window': dict(kind='effect', native_identity='festering_scythe'),
            'impact_buff': dict(kind='effect', native_identity='festering_scythe_tt'),
        })
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            options = dict(character=parse_character(sample_profile()), iterations=2, trace=False,
                           input_times=[0, 1500, 3000], simulation_config={'target_count': 2})
            observed = evaluate(profile, candidate, folder / 'observed', **options,
                                rule_observation_request=request)
            quiet = evaluate(profile, candidate, folder / 'quiet', **options)
            self.assertEqual(battle_report(observed['report']), battle_report(quiet['report']))
            facts = observed['report']['sim']['players'][0]['sim2gse_rule_observations']
            rows = facts['action_observations']
            first = next(row for row in rows if row['object'] == 'button' and row['input_index'] == 0)
            self.assertEqual(first['actual_form'], 'festering_strike')
            self.assertIsNone(first['estimated_effect_completion_time'])
            self.assertIsNone(first['effect_completion_estimate'])
            self.assertTrue(all(row['estimated_effect_completion_time'] is None
                                and row['effect_completion_estimate'] is None
                                for row in rows if row['object'] == 'delayed_action'),
                            'Putrefy异步派生效果缺乏已审同步时序，必须unknown')
            scythes = [row for row in rows if row['input_index'] == 1 and row['object'] in ('button', 'form')]
            self.assertEqual(len(scythes), 2)
            actor = facts['scope']['controlled_actor_index']
            for row in scythes:
                self.assertEqual(row['effect_completion_estimate'], dict(effect_id='festering_scythe_tt',
                    target_id=actor, source_id=actor, actual_form='festering_scythe', effect_delay_ms=0,
                    precision='current_state_estimate'))
                self.assertEqual(row['estimated_effect_completion_time'], row['earliest_execute'] + row['cast_ms'])
                self.assertLess(row['estimated_effect_completion_time'], row['occupancy_end'])
                self.assertIsNone(row['effect_completion_time'], '预计时序不能冒充实际效果完成事实')
            execution = next(row for row in facts['action_events'] if row['kind'] == 'execute'
                             and row['object'] == 'button' and row['input_index'] == 1)
            applied = next(row for row in facts['effect_events'] if row['object'] == 'impact' and row['kind'] == 'apply')
            self.assertEqual(applied['time'], execution['time'])
            self.assertEqual(applied['time'], scythes[0]['estimated_effect_completion_time'])
            self.assertEqual((applied['target_id'], applied['source_id']), (actor, actor))

            events = [row for row in facts['effect_events'] if row['object'] == 'scythe_window']
            applied = next(row for row in events if row['kind'] == 'apply')
            consumed = next(row for row in events if row['kind'] == 'consume')
            self.assertEqual(consumed['instance_id'], applied['instance_id'])
            self.assertEqual(consumed['source_input_index'], 1)
            self.assertEqual(consumed['source_actual_action'], 'festering_scythe')
            self.assertEqual(consumed['end_reason'], 'consumed')
            self.assertEqual(consumed['stacks'], 0)
            self.assertEqual(consumed['time'], 1500)
            self.assertIsNone(applied['source_input_index'])
            self.assertTrue(all(row['object'] == 'scythe_window' and row['sample_id'] == 1
                                for row in events))
            self.assertEqual(applied['source_id'], facts['scope']['controlled_actor_index'])
            self.assertTrue(consumed['lifecycle_complete'])
            execution = next(row for row in facts['action_events']
                             if row['kind'] == 'execute' and row['input_index'] == 1)
            self.assertLess(execution['event_index'], consumed['event_index'])
            self.assertNotIn('effect_completion_time', consumed)
            impact_events = [row for row in facts['effect_events'] if row['object'] == 'impact_buff']
            impact_start = next(row for row in impact_events if row['kind'] == 'start')
            refreshed = next(row for row in impact_events if row['kind'] == 'refresh')
            self.assertEqual(refreshed['instance_id'], impact_start['instance_id'])
            self.assertEqual(refreshed['stacks'], impact_start['stacks'])
            self.assertGreaterEqual(refreshed['scheduled_end'], impact_start['scheduled_end'])

    def test_requested_target_scopes_and_inactive_buff_coverage_keep_unknown_applicability(self):
        command = dict(kind='spell', spell_id=85948, name='Festering Strike',
                       simc_action='festering_strike')
        candidate = dict(blocks=[[command]], compiled_steps=[dict(type='spell', spell=85948)])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            options = dict(character=parse_character(sample_profile()), iterations=2, trace=False,
                           input_times=[0], simulation_config={'target_count': 2})
            request = dict(protocol=1, objects={
                'my_actor': dict(kind='target_scope', value='controlled_player'),
                'my_target': dict(kind='target_scope', value='current_attack_target'),
                'my_enemies': dict(kind='target_scope', value='all_currently_engaged_required_targets'),
                'unresolved_scope': dict(kind='target_scope', value='unresolved_scope'),
                'window': dict(kind='effect', native_identity='festering_scythe'),
                'inactive_window': dict(kind='effect', native_identity='festering_scythe_tt'),
                'missing_window': dict(kind='effect', native_identity='missing_native_buff'),
                'diseases': dict(kind='effect', components=[
                    dict(native_identity='dread_plague', target_scope='my_target'),
                    dict(native_identity='virulent_plague', target_scope='my_enemies')]),
            })
            observed = evaluate(profile, candidate, folder / 'observed', **options,
                                rule_observation_request=request)
            quiet = evaluate(profile, candidate, folder / 'quiet', **options)
            self.assertEqual(battle_report(observed['report']), battle_report(quiet['report']))
            facts = observed['report']['sim']['players'][0]['sim2gse_rule_observations']
            scopes = facts['inputs'][0]['target_scopes']
            actor = facts['scope']['controlled_actor_index']
            self.assertEqual(scopes['my_actor'], [dict(target_id=actor, required=True)])
            self.assertEqual(len(scopes['my_target']), 1)
            self.assertEqual(len(scopes['my_enemies']), 2)
            target = scopes['my_target'][0]['target_id']
            enemies = {row['target_id'] for row in scopes['my_enemies']}
            self.assertIn(target, enemies)
            self.assertNotIn(actor, enemies)
            self.assertIsNone(scopes['unresolved_scope'])
            self.assertEqual(facts['inputs'][0]['target_scope_sources']['my_enemies'],
                             'sim.target_non_sleeping_list')
            components = [row for row in facts['effect_observations']
                          if row['object'] == 'diseases' and row['target_id'] in enemies]
            current = {row['target_id']: row for row in components if row['component_id'] == 'dread_plague'}
            self.assertIsNone(current[target]['applicable'])
            self.assertIs(current[next(iter(enemies - {target}))]['applicable'], False)
            self.assertTrue(all(row['applicable'] is None for row in components
                                if row['component_id'] == 'virulent_plague'))
            coverage = facts['scope']['effect_events_complete']
            self.assertIs(coverage['window'], True)
            self.assertIs(coverage['inactive_window'], True,
                          '已审唯一Buff全程inactive仍须提供真实对象覆盖证明')
            self.assertIs(coverage['missing_window'], False)
            self.assertIs(coverage['diseases'], True, '已解析Dot在本轮已有完整请求范围采集')
            self.assertFalse(any(row['object'] in ('inactive_window', 'missing_window')
                                 for row in facts['effect_events']), '覆盖元数据不能伪造实例或时刻')

    def test_unaudited_stat_buff_keeps_known_events_without_complete_lifecycle(self):
        text = sample_profile().replace('race=highmountain_tauren', 'race=orc')
        commands = [dict(kind='spell', spell_id=spell, name=name, simc_action=name)
                    for name, spell in [('blood_fury', 20572), ('festering_strike', 85948)]]
        candidate = dict(blocks=[[row] for row in commands],
                         compiled_steps=[dict(type='spell', spell=row['spell_id']) for row in commands])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            # Avoid creating a second unused racial Buff through the default APL.
            profile.write_text(text + '\nactions=festering_strike\n', encoding='utf-8')
            options = dict(character=parse_character(text), iterations=2, trace=False,
                           input_times=[0, 1500])
            observed = evaluate(profile, candidate, folder / 'observed', **options,
                rule_observation_request=dict(protocol=1, objects={
                    'racial_buff': dict(kind='effect', native_identity='blood_fury')}))
            quiet = evaluate(profile, candidate, folder / 'quiet', **options)
            self.assertEqual(battle_report(observed['report']), battle_report(quiet['report']))
            events = observed['report']['sim']['players'][0]['sim2gse_rule_observations']['effect_events']
            self.assertIs(observed['report']['sim']['players'][0]['sim2gse_rule_observations']
                          ['scope']['effect_events_complete']['racial_buff'], False)
            self.assertTrue(any(row['kind'] == 'apply' for row in events))
            self.assertTrue(any(row['end_reason'] == 'expired' for row in events))
            self.assertTrue(all(row['lifecycle_complete'] is False for row in events),
                            '未审stat_buff_t派生路径不能仅凭base hook声称生命周期完整')

    def test_requested_buff_natural_expiry_and_battle_end_are_distinct(self):
        command = dict(kind='spell', spell_id=85948, name='Festering Strike',
                       simc_action='festering_strike')
        candidate = dict(blocks=[[command]], compiled_steps=[dict(type='spell', spell=85948)])
        funded_commands = [dict(kind='spell', spell_id=spell, name=name, simc_action=name)
                           for name, spell in [('dark_transformation', 63560),
                               ('festering_strike', 85948), ('festering_strike', 85948),
                               ('festering_strike', 85948), ('death_coil', 47541)]]
        funded = dict(blocks=[[row] for row in funded_commands],
                      compiled_steps=[dict(type='spell', spell=row['spell_id']) for row in funded_commands])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            for at, expected in ((0, 'expired'), (179900, 'simulation_end'), ('extend', 'expired')):
                with self.subTest(at=at):
                    options = dict(character=parse_character(sample_profile()), iterations=2,
                                   trace=False, input_times=[0, 1500, 3000, 4500, 6000] if at == 'extend' else [at])
                    program = funded if at == 'extend' else candidate
                    observed = evaluate(profile, program, folder / str(at), **options,
                        rule_observation_request=dict(protocol=1, objects={
                            'window': dict(kind='effect', native_identity=
                                'dark_transformation' if at == 'extend' else 'festering_scythe')}))
                    quiet = evaluate(profile, program, folder / ('quiet-' + str(at)), **options)
                    self.assertEqual(battle_report(observed['report']), battle_report(quiet['report']))
                    facts = observed['report']['sim']['players'][0]['sim2gse_rule_observations']
                    events = facts['effect_events']
                    applied = next(row for row in events if row['kind'] == 'apply')
                    scheduled = next(row for row in events if row['kind'] == 'start')
                    ended = [row for row in events if row['end_reason'] is not None]
                    self.assertEqual(len(ended), 1, 'demise清理不能重复关闭实例')
                    self.assertEqual(ended[0]['instance_id'], applied['instance_id'])
                    self.assertEqual(ended[0]['end_reason'], expected)
                    self.assertTrue(ended[0]['lifecycle_complete'])
                    if at == 'extend':
                        extended = next(row for row in events if row['kind'] == 'extend')
                        self.assertEqual(extended['instance_id'], applied['instance_id'])
                        self.assertEqual(extended['scheduled_end'], scheduled['scheduled_end'] + 1000)
                        self.assertEqual(extended['time'], 6000)
                        self.assertIsNone(extended['source_input_index'])
                        self.assertIsNone(extended['source_actual_action'])
                        scheduled = extended
                    if expected == 'expired':
                        self.assertEqual(ended[0]['end'], scheduled['scheduled_end'])
                    else:
                        self.assertEqual(ended[0]['end'], facts['scope']['end_ms'])
                        self.assertGreater(scheduled['scheduled_end'], ended[0]['end'])

    def test_same_scored_sample_observations_do_not_change_native_combat(self):
        """同一公开评估入口，无日志也保留离散事实，且不改变原生战斗。"""
        command = dict(kind='spell', spell_id=85948, name='Festering Strike',
                       simc_action='festering_strike')
        candidate = dict(blocks=[[command]], compiled_steps=[dict(type='spell', spell=85948)])
        request = dict(protocol=1, objects={
            'button_alias': dict(kind='action', native_action='festering_strike',
                                 base_button='festering_strike'),
            'form_alias': dict(kind='action', native_action='festering_scythe',
                               base_button='festering_strike'),
            'power_alias': dict(kind='resource', native_identity='runic_power'),
            'health_alias': dict(kind='state', native_identity='current_target.health_pct'),
            'true_alias': dict(kind='state', native_identity='literal.true'),
            'busy_alias': dict(kind='state', native_identity='controlled_input.occupancy'),
            'buff_alias': dict(kind='effect', native_identity='sudden_doom'),
            'disease_alias': dict(kind='effect', components=[
                dict(native_identity='virulent_plague', target_scope='arbitrary_scope')]),
            'arbitrary_scope': dict(kind='target_scope', value='current_attack_target'),
            'source_alias': dict(kind='source', value='controlled_player'),
        })
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            character = parse_character(sample_profile())
            observed = evaluate(profile, candidate, folder / 'observed', character=character,
                                iterations=2, trace=False, input_times=[0, 300, 1500, 3000],
                                rule_observation_request=request)
            quiet = evaluate(profile, candidate, folder / 'quiet', character=character,
                             iterations=2, trace=False, input_times=[0, 300, 1500, 3000])
            self.assertEqual(battle_report(observed['report']), battle_report(quiet['report']))
            facts = observed['report']['sim']['players'][0].get('sim2gse_rule_observations')
            self.assertIsInstance(facts, dict, '同次原生观察尚未接入评分报告')
            self.assertEqual(facts['protocol'], 1)
            self.assertEqual(facts['scope']['sample_selection'], 'first_scored_complete')
            self.assertEqual(facts['scope']['sample_id'], 1, '多次评分不能取warmup（预热）')
            self.assertTrue(facts['scope']['complete'])
            self.assertIs(type(facts['scope']['controlled_actor_index']), int)
            self.assertEqual([row['input_index'] for row in facts['inputs']], [0, 1, 2, 3])
            self.assertEqual([row['time'] for row in facts['inputs']], [0, 300, 1500, 3000])
            rows = facts['action_observations']
            executions = [row for row in facts['action_events'] if row['kind'] == 'execute']
            self.assertTrue(any(row['success'] is True for row in executions))
            scythes = [row for row in executions if row['input_index'] == 2
                       and row['actual_form'] == 'festering_scythe' and row['success'] is True]
            self.assertEqual({row['object'] for row in scythes}, {'button_alias', 'form_alias'},
                             '真实替换形态计数必须关联原输入与基础/形态两种别名')
            self.assertEqual({row['object'] for row in rows}, {'button_alias', 'form_alias'})
            self.assertTrue(all(row['sample_id'] == 1 for key in ('inputs', 'action_observations',
                'state_observations', 'effect_observations') for row in facts[key]))
            first = next(row for row in rows if row['input_index'] == 0 and row['object'] == 'button_alias')
            self.assertIn(executions[0]['actual_form'],
                          ('festering_strike', 'festering_scythe'))
            self.assertIsNone(first['native_qualified'])
            self.assertIn(first['actual_form'], ('festering_strike', 'festering_scythe'))
            self.assertIsInstance(first['resource_costs'], dict)
            self.assertGreater(first['gcd_ms'], 0)
            self.assertEqual(first['cast_ms'], 0)
            self.assertEqual(first['channel_ms'], 0)
            self.assertEqual(first['timing_precision'], 'current_state_estimate')
            self.assertGreater(first['occupancy_end'], first['earliest_execute'])
            qualification = next(row for row in facts['action_events'] if row['kind'] == 'qualification')
            self.assertIs(type(qualification['native_qualified']), bool)
            self.assertGreater(qualification['event_index'], first['event_index'])
            self.assertGreater(first['resource_balances']['rune'], 0)
            self.assertEqual(first['charges_current'], 1)
            states = {row['object']: row for row in facts['state_observations']
                      if row['input_index'] == 0}
            self.assertTrue(states['true_alias']['value'])
            self.assertEqual(states['health_alias']['value'], 100)
            self.assertIn('power_alias', states)
            self.assertIn('busy_alias', states)
            self.assertTrue(facts['effect_observations'])
            self.assertFalse(any(row.get('lifecycle_complete') is True
                                 for row in facts['effect_observations']))
            diseases = [row for row in facts['effect_observations'] if row['object'] == 'disease_alias']
            self.assertEqual(len(diseases), 4, '组件范围须由声明的value解析')
            self.assertTrue(all(row['source_id'] == facts['scope']['controlled_actor_index']
                                and row['target_id'] == states['health_alias']['target_id']
                                for row in diseases))
            request['objects']['renamed_scope'] = request['objects'].pop('arbitrary_scope')
            request['objects']['disease_alias']['components'][0]['target_scope'] = 'renamed_scope'
            renamed = evaluate(profile, candidate, folder / 'renamed', character=character,
                               iterations=2, trace=False, input_times=[0, 300, 1500, 3000],
                               rule_observation_request=request)
            renamed_facts = renamed['report']['sim']['players'][0]['sim2gse_rule_observations']
            for row in renamed_facts['inputs']:
                for field in ('target_scopes', 'target_scope_sources'):
                    row[field]['arbitrary_scope'] = row[field].pop('renamed_scope')
            self.assertEqual(facts, renamed_facts,
                             '范围别名改名不能改变原生事实')
            feedback = facts['feedback_events']
            self.assertTrue(feedback)
            self.assertEqual([row['origin'] for row in feedback if row['event'] == 'input'], [1, 2, 3, 4])
            self.assertTrue(all(row['battle'] == 1 and row['source'] == 'loop' for row in feedback))
            self.assertTrue(all({'event', 'ms', 'origin', 'step', 'signature', 'action', 'battle',
                                 'rp', 'source', 'source_origin', 'sequence_step', 'sequence_member'}
                                <= row.keys() for row in feedback))

    def test_single_iteration_observations_keep_burst_inputs_out_of_ordinary_opportunities(self):
        command = dict(kind='spell', spell_id=85948, name='Festering Strike',
                       simc_action='festering_strike')
        candidate = dict(blocks=[[command]], compiled_steps=[dict(type='spell', spell=85948)])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'sample.simc'
            profile.write_text(sample_profile(), encoding='utf-8')
            observed = evaluate(profile, candidate, folder / 'observed',
                character=parse_character(sample_profile()), iterations=1, trace=False,
                input_times=[0, 300], burst_candidate=candidate, input_sources=['loop', 'burst'],
                rule_observation_request=dict(protocol=1, objects={
                    'button': dict(kind='action', native_action='festering_strike',
                                   base_button='festering_strike'),
                    'unselected': dict(kind='action', native_action='death_coil',
                                       base_button='death_coil')}))
            facts = observed['report']['sim']['players'][0]['sim2gse_rule_observations']
            self.assertEqual(facts['scope']['sample_id'], 0)
            self.assertTrue(facts['scope']['complete'])
            self.assertEqual([(row['input_source'], row['source_step'])
                              for row in facts['inputs']], [('loop', 0), ('burst', 1)])
            self.assertEqual([row['input_allowed'] for row in facts['action_observations']
                              if row['object'] == 'button'],
                             [True, False])
            unselected = [row for row in facts['action_observations'] if row['object'] == 'unselected']
            self.assertTrue(all(row['native_qualified'] is None for row in unselected))
            outcomes = [row for row in facts['action_events'] if row['object'] == 'unselected'
                        and row['kind'] == 'outcome']
            self.assertTrue(outcomes)
            self.assertTrue(all(row['outcome'] == 'not_attempted' and row['success'] is False
                                and row['attempt'] is False for row in outcomes))


class NativeCatalogueTests(unittest.TestCase):
    def test_reference_reads_initialized_replacement_forms_without_claiming_availability(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            text = sample_profile()
            profile = folder / 'forms.simc'
            profile.write_text(text + '\nactions=death_coil\nactions+=/epidemic\nactions+=/scourge_strike\n'
                               'actions+=/festering_strike\nactions+=/chains_of_ice,if=0\n',
                               encoding='utf-8')
            native = engine.reference(profile, folder / 'reference', parse_character(text),
                                      iterations=2, simulation_config={'target_count': 1})
            rows = native['static_snapshot']['actions']
            for name, spell_id in [('necrotic_coil', 1242174), ('graveyard', 383269)]:
                forms = [row for row in rows if row['name'] == name]
                self.assertTrue(forms, name)
                for row in forms:
                    self.assertEqual(row['spell_id'], spell_id)
                    self.assertGreater(row['gcd_ms'], 0, row.get('unknown'))
                    self.assertEqual(row['cast_ms'], 0)
                    self.assertEqual(row['channel_ms'], 0)
                    self.assertIsInstance(row['costs'], dict)
                    self.assertEqual(row['gain_status'], 'known_zero')
                    self.assertEqual(row['gains'], {})

            rows = [row for row in native['static_snapshot']['actions']
                    if row['name'] == 'chains_of_ice']
            self.assertTrue(rows, '已初始化的受支持普通动作不能被原九技能白名单排除')
            self.assertFalse(any(row['name'] == 'chains_of_ice'
                                 for row in native['executed_actions']))
            for row in rows:
                self.assertGreater(row['gcd_ms'], 0)
                self.assertGreater(row['costs']['rune'], 0)
                self.assertEqual(row['gain_status'], 'known')
                self.assertEqual(row['gain_scope'], 'direct_action')
                self.assertGreater(row['gains']['runic_power'], 0)

    def test_reference_reads_audited_player_haste_and_executed_precombat_occupancy(self):
        import re
        # Public fixed-source sample data, not a specialization strategy dispatch.
        talents = 'CwPAAAAAAAAAAAAAAAAAAAAAAAwMjZMDDz2MzMTjZmxYGDAAAAAAAAzDMMGAsMDzsZmxMzYgBmxiGLbA2mYDAzAYmZmZMDmZwMzYA'
        text = re.sub(r'(?m)^talents=.*$', 'talents=' + talents, sample_profile())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = folder / 'haste.simc'
            profile.write_text(text + '\nactions.precombat=raise_dead\nactions=festering_strike\n'
                               'actions+=/death_coil\n', encoding='utf-8')
            native = engine.reference(profile, folder / 'reference', parse_character(text),
                                      iterations=1, simulation_config={'target_count': 1})
            snapshot = native['static_snapshot']
            self.assertEqual(snapshot['hero_subtree_ids'], [31])
            self.assertGreater(snapshot['parameters']['rune_recharge_ms'], 0)
            self.assertGreater(snapshot['parameters']['precombat_occupancy_ms'], 0)
            self.assertEqual(snapshot['precombat_precision'], 'native_static_estimate')
            self.assertIn('raise_dead', [row['name'] for row in native['precombat_sequence']])
            for row in snapshot['actions']:
                if row['name'] in ('raise_dead', 'festering_strike', 'death_coil'):
                    self.assertGreater(row['gcd_ms'], 0, row.get('unknown'))
                    self.assertEqual(row['cast_ms'], 0)

    def test_reference_collects_non_dk_cast_and_complete_channel_timing(self):
        """原生实验性样本仅核采集和时序，不声明治疗专精评分支持。"""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            character_text = (ROOT / 'tests/sim2gse/fixtures/discipline.simc').read_text()
            profile = folder / 'discipline.simc'
            profile.write_text(character_text + '\nallow_experimental_specializations=1\n'
                               'actions.precombat=smite\n'
                               'actions=penance\nactions+=/smite\n'
                               'actions+=/shadow_word_death,if=0\n', encoding='utf-8')
            native = engine.reference(profile, folder / 'reference', parse_character(character_text),
                                      iterations=1, simulation_config={'target_count': 1})
            snapshot = native['static_snapshot']
            self.assertIsInstance(snapshot, dict, '公共初始化快照入口仍限于DK专有路径')
            self.assertEqual(snapshot['protocol'], 2)
            self.assertEqual(snapshot['stage'], 'precombat_initialized_before_actions')
            rows = {row['name']: row for row in snapshot['actions']}
            self.assertGreater(rows['smite']['cast_ms'], 0)
            self.assertEqual(rows['smite']['channel_ms'], 0)
            self.assertGreater(rows['penance']['channel_ms'], rows['penance']['gcd_ms'])
            self.assertEqual(rows['penance']['cast_ms'], 0)
            self.assertTrue(rows['penance']['channeled'])
            self.assertGreater(snapshot['parameters']['precombat_occupancy_ms'], 0)
            self.assertEqual(snapshot['precombat_precision'], 'native_static_estimate')
            self.assertIn('smite', [row['name'] for row in native['precombat_sequence']])
            self.assertTrue({'smite', 'penance'}.issubset(
                row['name'] for row in native['executed_actions']))

            self.assertIn('costs', rows['smite']['unknown'])
            unknown = rows['shadow_word_death']
            self.assertFalse(unknown['channeled'])
            self.assertEqual(unknown['channel_ms'], 0)
            self.assertNotIn('channel_ms', unknown['unknown'])
            self.assertNotIn('cast_ms', unknown)
            self.assertIn('cast_ms', unknown['unknown'])

    def test_reference_does_not_count_unexecuted_precombat_cast(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            text = (ROOT / 'tests/sim2gse/fixtures/discipline.simc').read_text()
            profile = folder / 'discipline.simc'
            profile.write_text(text + '\nallow_experimental_specializations=1\n'
                               'actions.precombat=smite,if=0\n'
                               'actions=smite\n', encoding='utf-8')
            native = engine.reference(profile, folder / 'reference', parse_character(text),
                                      iterations=1, simulation_config={'target_count': 1})
            self.assertEqual(native['precombat_sequence'], [])
            snapshot = native['static_snapshot']
            self.assertEqual(snapshot['parameters']['precombat_occupancy_ms'], 0)
            self.assertEqual(snapshot['parameters']['precombat_gcd_ms'], 0)
