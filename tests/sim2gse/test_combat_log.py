from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "projects" / "sim2gse" / "combat_log.py"


class CombatLogToolTests(unittest.TestCase):
    def run_tool(self, combat: Path, *args: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(TOOL), str(combat), "--player", "测试者", *args],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_preserves_real_training_damage_after_the_dummy_reaches_one_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            combat = Path(directory) / "WoWCombatLog.txt"
            combat.write_text("\n".join([
                '9/13/2026 16:41:19.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"训练假人",0,0,50842,"血液沸腾",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,20532,20532,20531,1,0,0,0,nil,nil,nil,ST',
                '9/13/2026 16:41:20.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"训练假人",0,0,50842,"血液沸腾",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,13002,13002,13001,1,0,0,0,nil,nil,nil,ST',
            ]), encoding="utf-8")

            result = self.run_tool(
                combat, "--duration", "2", "--primary-target", "Creature-1"
            )

            self.assertEqual(result["primary_target"]["damage"], 33534)
            self.assertEqual(result["primary_target"]["overkill"], 33532)
            self.assertEqual(result["primary_target"]["effective_damage"], 2)
            self.assertEqual(result["primary_target"]["dps"], 16767)
            self.assertEqual(result["primary_target"]["effective_dps"], 1)
            self.assertEqual(result["total_damage"], 33534)
            self.assertEqual(result["total_overkill"], 33532)
            self.assertEqual(result["total_effective_damage"], 2)
            source = result["damage_sources"][0]
            self.assertEqual(source["damage"], 33534)
            self.assertEqual(source["overkill"], 33532)
            self.assertEqual(source["effective_damage"], 2)

    def test_reports_normal_kill_damage_at_every_target_level(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            combat = Path(directory) / "WoWCombatLog.txt"
            combat.write_text("\n".join([
                '9/13/2026 16:41:19.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"主目标",0,0,50842,"血液沸腾",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,1000,1000,200,1,0,0,0,nil,nil,nil,ST',
                '9/13/2026 16:41:20.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-2,"次目标",0,0,50842,"血液沸腾",0,Creature-2,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,500,500,100,1,0,0,0,nil,nil,nil,AOE',
            ]), encoding="utf-8")

            result = self.run_tool(
                combat, "--duration", "2", "--primary-target", "Creature-1"
            )

            self.assertEqual(result["primary_target"]["effective_dps"], 400)
            self.assertEqual(result["other_affected_targets"], [{
                "guid": "Creature-2", "name": "次目标", "damage": 500,
                "dps": 250, "overkill": 100, "overkill_dps": 50,
                "effective_damage": 400, "effective_dps": 200,
            }])
            self.assertEqual(result["secondary_dps"], 250)
            self.assertEqual(result["secondary_overkill_dps"], 50)
            self.assertEqual(result["secondary_effective_dps"], 200)
            self.assertEqual(result["total_dps"], 750)
            self.assertEqual(result["total_overkill_dps"], 150)
            self.assertEqual(result["total_effective_dps"], 600)

    def test_reports_primary_target_without_calling_splash_a_multitarget_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            combat = root / "WoWCombatLog.txt"
            combat.write_text(
                "\n".join(
                    [
                        '9/13/2026 15:00:00.0000  SPELL_DAMAGE,Pet-old,"常驻宠物",0,0,Creature-old,"旧假人",0,0,1,"宠物攻击",0,Creature-old,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,9999,9999,-1,1,0,0,0,nil,nil,nil,ST',
                        '9/13/2026 16:41:18.9500  SPELL_DAMAGE,Pet-2,"常驻宠物",0,0,Creature-1,"主训练假人",0,0,1,"宠物攻击",0,Creature-1,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,250,250,-1,1,0,0,0,nil,nil,nil,ST',
                        '9/13/2026 16:41:19.0000  SPELL_SUMMON,Player-1,"测试者-服务器-CN",0,0,Pet-1,"符文武器",0,0,49028,"符文刃舞",0',
                        '9/13/2026 16:41:19.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"主训练假人",0,0,206930,"心脏打击",0,Creature-1,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,1000,1000,-1,1,0,0,0,nil,nil,nil,ST',
                        '9/13/2026 16:41:19.5000  SPELL_DAMAGE,Pet-1,"符文武器",0,0,Creature-1,"主训练假人",0,0,49998,"灵界打击",0,Creature-1,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,500,500,-1,1,0,0,0,nil,nil,nil,ST',
                        '9/13/2026 16:41:19.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-2,"附近假人",0,0,1264146,"爬行瘟疫",0,Creature-2,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,100,100,-1,1,0,0,0,nil,nil,nil,AOE',
                        '9/13/2026 16:41:20.0000  SPELL_CAST_SUCCESS,Player-1,"测试者-服务器-CN",0,0,Creature-1,"主训练假人",0,0,206930,"心脏打击",0',
                        '9/13/2026 16:41:20.0500  SPELL_CAST_SUCCESS,Player-1,"测试者-服务器-CN",0,0,Creature-1,"主训练假人",0,0,49998,"灵界打击",0',
                        '9/13/2026 16:41:20.1000  SPELL_CAST_FAILED,Player-1,"测试者-服务器-CN",0,0,0000000000000000,nil,0,0,49028,"符文刃舞",0,"尚未恢复"',
                        '9/13/2026 16:41:20.8000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"主训练假人",0,0,49998,"灵界打击",0,Creature-1,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,2000,2000,-1,1,0,0,0,nil,nil,nil,ST',
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_tool(combat, "--duration", "2", "--owned-source", "常驻宠物")
            self.assertEqual(result["primary_target"]["name"], "主训练假人")
            self.assertEqual(result["primary_target"]["damage"], 3750)
            self.assertEqual(result["primary_target"]["dps"], 1875)
            self.assertEqual(result["primary_target_selection"], {
                "method": "successful_cast_destination",
                "evidence_count": 2,
            })
            self.assertEqual(result["affected_target_count"], 2)
            self.assertEqual(result["other_affected_target_count"], 1)
            self.assertEqual(result["other_affected_targets"], [
                {
                    "guid": "Creature-2",
                    "name": "附近假人",
                    "damage": 100,
                    "dps": 50,
                    "overkill": 0,
                    "overkill_dps": 0,
                    "effective_damage": 100,
                    "effective_dps": 50,
                }
            ])
            self.assertEqual(result["secondary_damage"], 100)
            self.assertEqual(result["successful_casts"]["心脏打击"]["count"], 1)
            self.assertEqual(result["failed_casts"]["符文刃舞"]["尚未恢复"], 1)

    def test_groups_damage_by_spell_id_owner_and_button_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            combat = root / 'WoWCombatLog.txt'
            combat.write_text('\n'.join([
                '9/13/2026 16:41:19.0000  SPELL_CAST_SUCCESS,Player-1,"测试者-服务器-CN",0,0,Creature-1,"假人",0,0,100,"同名伤害",0',
                '9/13/2026 16:41:19.0100  SPELL_SUMMON,Player-1,"测试者-服务器-CN",0,0,Pet-1,"召唤物",0,0,300,"召唤",0',
                '9/13/2026 16:41:19.1000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"假人",0,0,100,"同名伤害",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,1000,1000,-1,1,0,0,0,nil,nil,nil,ST',
                '9/13/2026 16:41:19.2000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"假人",0,0,200,"同名伤害",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,500,500,-1,1,0,0,0,nil,nil,nil,ST',
                '9/13/2026 16:41:19.3000  SPELL_DAMAGE,Pet-1,"召唤物",0,0,Creature-1,"假人",0,0,300,"撕咬",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,250,250,-1,1,0,0,0,nil,nil,nil,ST',
            ]), encoding='utf-8')
            simulation = root / 'simulation.json'
            simulation.write_text(json.dumps({'sim': {
                'options': {'max_time': 2, 'desired_targets': 1},
                'players': [{'name': '测试者', 'sim2gse_actions': [
                    {'data_id': 100, 'background': False, 'passive': False, 'type': 'spell'},
                ], 'collected_data': {'dps': {
                    'mean': 1875, 'min': 1700, 'max': 2000, 'std_dev': 50,
                }}, 'stats': [
                    {'id': 100, 'spell_name': '同名伤害', 'name': 'button', 'type': 'damage',
                     'actual_amount': {'mean': 2000}, 'num_executes': {'mean': 5},
                     'children': [
                         {'id': 200, 'spell_name': '同名伤害', 'name': 'derived',
                          'type': 'damage', 'actual_amount': {'mean': 1000},
                          'num_executes': {'mean': 10}},
                         {'id': 300, 'spell_name': '撕咬', 'name': 'bite',
                          'type': 'damage', 'actual_amount': {'mean': 500},
                          'num_executes': {'mean': 4}, 'sim2gse_owner_type': 'owned_unit',
                          'sim2gse_actor_index': 7, 'sim2gse_actor_name': '召唤物'},
                         {'id': 400, 'spell_name': '骑士攻击', 'name': 'rider_hit',
                          'type': 'damage', 'actual_amount': {'mean': 250},
                          'num_executes': {'mean': 2}, 'sim2gse_owner_type': 'owned_unit',
                          'sim2gse_actor_index': 8, 'sim2gse_actor_name': '骑士'},
                     ]},
                ], 'stats_pets': {'召唤物': [
                    {'id': 300, 'spell_name': '撕咬', 'name': 'bite', 'type': 'damage',
                     'actual_amount': {'mean': 500}, 'num_executes': {'mean': 4},
                     'sim2gse_owner_type': 'owned_unit', 'sim2gse_actor_index': 7,
                     'sim2gse_actor_name': '召唤物'},
                ], '骑士': [
                    {'id': 401, 'spell_name': '防御统计', 'name': 'defense', 'type': 'damage',
                     'actual_amount': None, 'sim2gse_owner_type': 'owned_unit',
                     'sim2gse_actor_index': 8, 'sim2gse_actor_name': '骑士'},
                ]}}],
            }}), encoding='utf-8')

            result = self.run_tool(combat, '--duration', '2', '--simulation', str(simulation),
                                   '--primary-target', 'Creature-1')
            actual = {(row['owner_type'], row['spell_id']): row for row in result['damage_sources']}
            self.assertEqual(actual[('player', 100)]['category'], 'button')
            self.assertEqual(actual[('player', 200)]['category'], 'derived')
            self.assertEqual(actual[('owned_unit', 300)]['category'], 'owned_unit')
            self.assertEqual(actual[('player', 100)]['damage'], 1000)
            comparison = {(row['owner_type'], row['spell_id']): row
                          for row in result['damage_source_comparison']}
            self.assertEqual(comparison[('owned_unit', 400)]['simulation_dps'], 125)
            self.assertEqual(comparison[('player', 100)]['actual_dps'], 500)
            self.assertEqual(comparison[('player', 100)]['simulation_dps'], 1000)
            self.assertEqual(comparison[('player', 100)]['percent_of_simulation'], 50)
            self.assertNotIn(('unattributed', -1), comparison)
            self.assertEqual(sum(row['simulation_dps'] for row in comparison.values()), 1875)
            self.assertEqual(result['successful_casts_by_spell_id']['100']['count'], 1)

    def test_rejects_overcounted_simulation_damage_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            combat = root / 'WoWCombatLog.txt'
            combat.write_text(
                '9/13/2026 16:41:19.0000  SPELL_DAMAGE,Player-1,"测试者",0,0,Creature-1,"假人",0,0,1,"技能",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,100,100,-1,1,0,0,0,nil,nil,nil,ST',
                encoding='utf-8',
            )
            simulation = root / 'simulation.json'
            simulation.write_text(json.dumps({'sim': {
                'options': {'max_time': 1, 'desired_targets': 1},
                'players': [{'name': '测试者', 'collected_data': {'dps': {
                    'mean': 100, 'min': 90, 'max': 110, 'std_dev': 5,
                }}, 'stats': [{'id': 1, 'type': 'damage',
                               'actual_amount': {'mean': 101}}]}],
            }}), encoding='utf-8')

            invalid = subprocess.run(
                [sys.executable, str(TOOL), str(combat), '--player', '测试者',
                 '--duration', '1', '--simulation', str(simulation),
                 '--primary-target', 'Creature-1'],
                text=True, encoding='utf-8', capture_output=True)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn('SimC 伤害来源重复', invalid.stderr)

    def test_uses_latest_gse_session_and_compares_primary_dps_with_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            combat = root / "WoWCombatLog.txt"
            combat.write_text(
                '\n'.join([
                    '9/13/2026 15:50:09.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-old,"旧假人",0,0,206930,"心脏打击",0,Creature-old,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,9000,9000,-1,1,0,0,0,nil,nil,nil,ST',
                    '9/13/2026 16:41:19.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-new,"新假人",0,0,206930,"心脏打击",0,Creature-new,0,10000,10000,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,3000,3000,-1,1,0,0,0,nil,nil,nil,ST',
                ]), encoding='utf-8')
            debug = root / 'gse-debug.txt'
            debug.write_text('\n'.join([
                'S2G:1,1,1789285808,旧技能,(1) Found in Spell Book,Able To Cast,Resources Available,GCD Free,Not Casting,旧技能,block:1',
                'S2G:1,2,1789285808,旧技能,(1) Found in Spell Book,Able To Cast,Resources Available,GCD Free,Not Casting,旧技能,block:2',
                'S2G:1,1,1789288879,新技能,(2) Found in Spell Book,Able To Cast,Resources Available,GCD Free,Not Casting,新技能,block:1',
                'S2G:1,2,1789288879,新技能,(2) Found in Spell Book,Not Able to Cast,Resources Not Available,GCD In Cooldown,Not Casting,新技能,block:2',
                'S2G:1,3,1789288880,新技能,(2) Found in Spell Book,Not Able to Cast,Resources Available,GCD In Cooldown,Not Casting,新技能,block:3',
                'S2G:1,4,1789288883,尾部技能,(3) Found in Spell Book,Not Able to Cast,Resources Not Available,GCD In Cooldown,Not Casting,尾部技能,block:4',
            ]), encoding='utf-8')
            simulation = root / 'simulation.json'
            simulation.write_text(json.dumps({
                'sim': {
                    'options': {'max_time': 2, 'desired_targets': 1},
                    'players': [
                        {'name': '其他角色', 'collected_data': {'dps': {'mean': 9999}}},
                        {'name': '测试者', 'collected_data': {'dps': {
                            'mean': 2000, 'min': 1400, 'max': 2600, 'std_dev': 300,
                        }}},
                    ],
                }
            }), encoding='utf-8')

            result = self.run_tool(
                combat, '--duration', '2', '--gse-debug', str(debug), '--simulation', str(simulation),
                '--primary-target', '新假人')

            self.assertEqual(result['primary_target']['name'], '新假人')
            self.assertEqual(result['gse_debug']['rows'], 3)
            self.assertEqual(result['gse_debug']['estimated_average_input_interval_ms'], 500)
            self.assertEqual(result['gse_debug']['attempts_by_spell'], {'新技能': 3})
            self.assertEqual(result['gse_debug']['blocked_reasons'], {
                'GCD In Cooldown': 2,
                'Not Able to Cast': 2,
                'Resources Not Available': 1,
            })
            self.assertEqual(result['simulation_dps'], 2000)
            self.assertEqual(result['simulation_conditions'], {
                'duration_seconds': 2, 'targets': 1,
                'actual_affected_targets': 1, 'secondary_damage_excluded': 0,
                'damage_metric': 'logged_amount',
            })
            self.assertEqual(result['simulation_conditions_not_verifiable_from_combat_log'], [
                'specialization', 'talents', 'gear', 'game_version', 'sequence',
                'enemy_attack_timeline', 'enemy_health_timeline',
                'target_defenses', 'target_skill_coverage', 'input_timing',
            ])
            self.assertEqual(result['primary_target_percent_of_simulation'], 75)
            self.assertEqual(result['simulation_comparison'], {
                'status': 'conditions_unverified',
                'accuracy_assessed': False,
                'damage_metric': 'logged_amount',
                'throughput_percent': 75,
                'unverified_conditions': [
                    'specialization', 'talents', 'gear', 'game_version', 'sequence',
                    'enemy_attack_timeline', 'enemy_health_timeline',
                    'target_defenses', 'target_skill_coverage', 'input_timing',
                ],
            })
            self.assertEqual(result['simulation_dps_distribution'], {
                'mean': 2000, 'min': 1400, 'max': 2600, 'std_dev': 300,
            })
            self.assertTrue(result['primary_target_within_simulation_sample_range'])

    def test_rejects_ambiguous_comparison_and_malformed_debug(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            combat = root / 'WoWCombatLog.txt'
            combat.write_text('\n'.join([
                '9/13/2026 16:41:19.0000  SPELL_CAST_SUCCESS,Player-1,"测试者-服务器-CN",0,0,Creature-1,"假人一",0,0,1,"技能一",0',
                '9/13/2026 16:41:19.1000  SPELL_CAST_SUCCESS,Player-1,"测试者-服务器-CN",0,0,Creature-2,"假人二",0,0,2,"技能二",0',
                '9/13/2026 16:41:19.2000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"假人一",0,0,1,"技能一",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,100,100,-1,1,0,0,0,nil,nil,nil,ST',
                '9/13/2026 16:41:19.3000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-2,"假人二",0,0,2,"技能二",0,Creature-2,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,100,100,-1,1,0,0,0,nil,nil,nil,ST',
            ]), encoding='utf-8')
            simulation = root / 'simulation.json'
            simulation.write_text(json.dumps({'sim': {
                'options': {'max_time': 2, 'desired_targets': 1},
                'players': [{'name': '测试者', 'collected_data': {'dps': {
                    'mean': 100, 'min': 80, 'max': 120, 'std_dev': 10,
                }}}],
            }}), encoding='utf-8')
            ambiguous = subprocess.run(
                [sys.executable, str(TOOL), str(combat), '--player', '测试者',
                 '--duration', '2', '--simulation', str(simulation)],
                text=True, encoding='utf-8', capture_output=True)
            self.assertNotEqual(ambiguous.returncode, 0)
            self.assertIn('--primary-target', ambiguous.stderr)

            mismatched_targets = subprocess.run(
                [sys.executable, str(TOOL), str(combat), '--player', '测试者',
                 '--duration', '2', '--simulation', str(simulation),
                 '--primary-target', '假人一'],
                text=True, encoding='utf-8', capture_output=True)
            self.assertEqual(mismatched_targets.returncode, 0, mismatched_targets.stderr)
            compared = json.loads(mismatched_targets.stdout)
            self.assertEqual(compared['simulation_conditions']['actual_affected_targets'], 2)
            self.assertEqual(compared['simulation_conditions']['secondary_damage_excluded'], 100)

            malformed = root / 'gse-debug.txt'
            malformed.write_text('S2G:1,1,1789288879', encoding='utf-8')
            invalid = subprocess.run(
                [sys.executable, str(TOOL), str(combat), '--player', '测试者',
                 '--duration', '2', '--gse-debug', str(malformed)],
                text=True, encoding='utf-8', capture_output=True)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn('GSE 调试记录格式错误', invalid.stderr)

    def test_rejects_non_finite_and_inconsistent_simulation_distributions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            combat = root / 'WoWCombatLog.txt'
            combat.write_text(
                '9/13/2026 16:41:19.0000  SPELL_DAMAGE,Player-1,"测试者-服务器-CN",0,0,Creature-1,"假人",0,0,1,"技能",0,Creature-1,0,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,90,100,100,-1,1,0,0,0,nil,nil,nil,ST',
                encoding='utf-8',
            )
            simulation = root / 'simulation.json'
            for distribution in (
                {'mean': float('nan'), 'min': 80, 'max': 120, 'std_dev': 10},
                {'mean': 130, 'min': 80, 'max': 120, 'std_dev': 10},
                {'mean': 100, 'min': 80, 'max': 120, 'std_dev': False},
            ):
                simulation.write_text(json.dumps({'sim': {
                    'options': {'max_time': 2, 'desired_targets': 1},
                    'players': [{'name': '测试者', 'collected_data': {'dps': distribution}}],
                }}), encoding='utf-8')
                invalid = subprocess.run(
                    [sys.executable, str(TOOL), str(combat), '--player', '测试者',
                     '--duration', '2', '--simulation', str(simulation),
                     '--primary-target', '假人'],
                    text=True, encoding='utf-8', capture_output=True)
                self.assertNotEqual(invalid.returncode, 0)
                self.assertIn('SimC 玩家 DPS 分布无效', invalid.stderr)


if __name__ == "__main__":
    unittest.main()
