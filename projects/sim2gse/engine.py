"""只调用本项目锁定的独立引擎，保留原生输出与错误。"""
from pathlib import Path
import hashlib
import json
import math
import os
from runtime import replace_file
from runtime import BudgetExceeded, ProcessTimeout, TaskCancelled, TaskRuntime, run_command
from simulation_config import config_for, engine_options

class CandidateError(ValueError):
    """单个合法候选没有有效伤害或单批超时；不代表原生兼容性正常。"""


ROOT = Path(__file__).resolve().parents[2]
# 可接受的原生报告构建号。历史报告在其对应版本上依然有效，客户端升级时追加新编号，
# 不删除旧编号；清单之外的版本仍照旧拒绝。
ACCEPTED_BUILD_LEVELS = (69587, 69814)
COMMON = ['item_db_source=local', 'threads=1', 'seed=20260912', 'target_error=0',
          'fixed_time=1', 'vary_combat_length=0', 'fight_style=Patchwerk',
          'optimal_raid=0', 'potion=disabled', 'flask=disabled', 'food=disabled',
          'augmentation=disabled', 'temporary_enchant=disabled', 'override.allow_potions=0',
          'override.allow_food=0', 'override.allow_flasks=0', 'override.allow_augmentations=0']


def identity(mode, runtime=None):
    if runtime:
        runtime.check()
        if mode in runtime.identities:
            return runtime.identities[mode]
    lock = json.loads((ROOT / 'projects/sim2gse/compatibility/lock.json').read_text())
    manifest = json.loads((ROOT / '.local/sim2gse/build' / mode / 'build.json').read_text())
    executable = ROOT / '.tools/sim2gse/product' / mode / 'engine/simc.exe'
    if (manifest['exit_code'] or manifest['upstream_commit'] != lock['upstream_commit'] or
            manifest['upstream_tree'] != lock['upstream_tree'] or
            manifest['build_options'] != lock['build_options'] or
            manifest['binary_sha256'] != hashlib.sha256(executable.read_bytes()).hexdigest()):
        raise ValueError('独立引擎身份或构建状态不符，请重新构建')
    if mode == 'tc':
        expected = lock['patches'] + [lock['tc_patch']]
    elif mode == 'controlled':
        expected = lock['patches']
    elif mode == 'baseline':
        expected = lock['baseline_patches']
    else:
        raise ValueError('未知引擎模式')
    if manifest['patches'] != expected:
        raise ValueError('引擎补丁身份已变化')
    for patch in expected:
        patch_bytes = (ROOT / patch['path']).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(patch_bytes).hexdigest() != patch['sha256']:
            raise ValueError('补丁与受检引擎不符')
    if runtime:
        runtime.check()
        runtime.identities[mode] = (executable, manifest)
    return executable, manifest


def run(profile, folder, mode='baseline', options=(), *, runtime=None, timeout_seconds=30,
        simulation_config=None):
    runtime = runtime or TaskRuntime(timeout_seconds)
    simulation_config = config_for(simulation_config)
    executable, manifest = identity(mode, runtime)
    folder.mkdir(parents=True, exist_ok=True)
    command = [str(executable), os.path.relpath(profile, folder), *COMMON, *engine_options(simulation_config),
               'iterations=100', 'max_time=180',
               'json2=native.json', 'output=native.txt', *options]
    try:
        proc = run_command(command, folder, timeout_seconds=timeout_seconds, runtime=runtime)
    except ProcessTimeout as error:
        (folder / 'process.log').write_text(str(error), encoding='utf-8')
        raise CandidateError('原生引擎运行超时，已停止本次进程') from error
    except (TaskCancelled, BudgetExceeded):
        raise
    log = (proc.stdout + proc.stderr).decode('utf-8', errors='replace')
    (folder / 'process.log').write_text(log, encoding='utf-8')
    (folder / 'invocation.json').write_text(json.dumps(dict(command=command, identity=manifest,
                                                           exit_code=proc.returncode,
                                                           elapsed_seconds=proc.elapsed_seconds), indent=2), encoding='utf-8')
    if proc.returncode:
        raise ValueError('原生引擎失败，参见 ' + str(folder / 'process.log'))
    return log


def inspect(reference, folder):
    """基准决定范围，原生标记决定身份；不枚举其他角色能力。"""
    if reference.get('actions_protocol') != 1:
        raise ValueError('基准没有返回完整的原生动作标记，请重新构建')
    actions = {}
    precombat_actions = {}
    sources = []
    unsupported = []
    items = reference['active_items']
    used_precombat = {row.get('name') for row in reference.get('precombat_sequence', [])
                      if not row.get('queue_failed')}
    for native in [*reference['executed_actions'], *reference.get('precombat_definitions', [])]:
        row = dict(native)
        sources.append(row)
        name = row['signature'].split(',', 1)[0]
        if (not row['signature'] or not row['player_owned'] or (row['background'] and name != 'use_item') or row['quiet'] or row['passive'] or
                row['type'] in ('call_action_list', 'action_variable', 'sequence') or name == 'use_items'):
            row['status'] = 'native_non_button'
            continue
        if row['precombat'] and row['name'] not in used_precombat:
            row['status'] = 'native_non_button'
            continue
        action = None
        if row['name'] == 'auto_attack':
            action = dict(kind='start_attack', simc_action=name, name='开始自动攻击')
        elif name == 'use_item':
            options = dict(part.split('=', 1) for part in row['signature'].split(',')[1:] if '=' in part)
            matches = [item for item in items if
                       (options.get('slot') == item['slot'] or options.get('name') == item['name'])]
            if len(matches) != 1:
                unsupported.append(f"{row['name']}: 无法确定基准使用的装备槽位")
            else:
                item = matches[0]
                if item['slot'] not in ('trinket1', 'trinket2'):
                    unsupported.append(f"尚不支持的主动物品使用方式: {item['slot']}")
                else:
                    action = dict(kind='item', slot=13 if item['slot']=='trinket1' else 14,
                                  item_id=item['id'], driver_spell_id=item['driver_spell_id'], simc_action=f"use_item,slot={item['slot']}",
                                  name=f"使用{item['slot']}", gcd_ms=row['gcd_ms'])
        elif row['data_id'] > 0 and name:
            if not row['data_valid'] or not row['base_spell_id']:
                unsupported.append(f"{name}: 基准动作与原生法术编号不一致")
            else:
                action = dict(kind='spell', spell_id=row['data_id'], simc_action=name, name=name,
                              gcd_ms=row['gcd_ms'], base_spell_id=row['base_spell_id'])
        else:
            if row['harmful']:
                unsupported.append(f"{row['name']}: 原生伤害代理没有可导出的法术身份")
            # 非伤害、无法术身份的场景设施不作为伤害技能按钮。
            row['status'] = 'native_non_button'
            continue
        row['status'] = ('mapped_precombat' if row['precombat'] else 'mapped') if action else 'unsupported'
        if action:
            action['native_name'] = row['name']
            target = precombat_actions if row['precombat'] else actions
            target.setdefault(row['name'] if row['precombat'] else action['simc_action'], action)
    buttons = {}
    for action in actions.values():
        key = ('spell', action['base_spell_id']) if action['kind']=='spell' else ('action', action['simc_action'])
        buttons.setdefault(key, []).append(action)
    grouped = []
    for variants in buttons.values():
        primary = next((a for a in variants if a.get('spell_id') == a.get('base_spell_id')), variants[0])
        grouped.append(dict(primary, variants=variants) if len(variants)>1 else primary)
    import_actions = []
    seen_import_actions = set()

    def add_import_action(action):
        key = (action.get('kind'), action.get('spell_id'), action.get('slot'),
               action.get('item_id'), action.get('simc_action'))
        if key not in seen_import_actions:
            seen_import_actions.add(key)
            import_actions.append(action)

    for action in grouped:
        for variant in action.get('variants', [action]):
            add_import_action(dict(variant))
    for row in reference.get('import_action_candidates', []):
        if (row.get('kind') == 'spell' and type(row.get('spell_id')) is int
                and row['spell_id'] > 0 and row.get('data_valid')
                and row.get('native_spell_id') and row.get('simc_action')
                and row.get('available') is True and row.get('background') is False
                and row.get('passive') is False and row.get('quiet') is False):
            add_import_action(dict(kind='spell', spell_id=row['spell_id'],
                                   native_spell_id=row['native_spell_id'], name=row['name'],
                                   simc_action=row['simc_action'], gcd_ms=row.get('gcd_ms', 0)))
    for item in items:
        slot = {'trinket1': 13, 'trinket2': 14}.get(item.get('slot'))
        if slot is not None and type(item.get('id')) is int and item['id'] > 0:
            add_import_action(dict(kind='item', slot=slot, item_id=item['id'],
                                   simc_action=f'use_item,slot={item["slot"]}',
                                   name=item.get('name', ''),
                                   driver_spell_id=item.get('driver_spell_id')))
    precombat_program = [dict(precombat_actions[row['name']])
                         for row in reference.get('precombat_sequence', [])
                         if not row.get('queue_failed') and row.get('name') in precombat_actions]
    result = dict(actions=grouped, precombat_actions=precombat_program, sources=sources, protocol=3,
                  import_actions=import_actions,
                  scope='baseline_executed_player_actions', coverage='all_baseline_iterations')
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'catalogue.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if unsupported:
        raise ValueError('主动能力不完整，停止模拟与导出: ' + '; '.join(unsupported))
    if not any(a['kind'] != 'start_attack' for a in actions.values()):
        raise ValueError('基准未取得可模拟的主动能力')
    return result


def player_report(report, character):
    players = [p for p in report['sim']['players']
               if p['name'] == character.name and p.get('sim2gse_class') == character.class_name]
    if len(players) != 1:
        raise ValueError('原生报告无法唯一确定输入角色')
    return players[0]


def check_report(report, character, iterations, *, simulation_config=None):
    simulation_config = config_for(simulation_config)
    sim = report['sim']
    if len(sim['targets']) != simulation_config['target_count']:
        raise ValueError('原生报告的目标数量不符')
    player = player_report(report, character)
    if (player['sim2gse_class'] != character.class_name or player['level'] != character.level or
            (character.spec_id is not None and player['sim2gse_spec_id'] != character.spec_id) or
            (character.spec_id is not None and player['race'] != character.race) or player['talents'] != character.fields['talents'] or
            sim['options']['dbc']['Live']['build_level'] not in ACCEPTED_BUILD_LEVELS or
            sim['options']['dbc']['version_used'] != 'Live'):
        raise ValueError('原生报告没有保持角色或固定版本')
    metadata_only = []
    for slot, item in character.equipment.items():
        if slot in ('shirt', 'tabard'):
            continue
        actual = player['gear'][{'shoulder': 'shoulders', 'wrist': 'wrists'}.get(slot, slot)]['encoded_item']
        expected_fields = dict(part.split('=', 1) for part in item.raw.split(',') if '=' in part)
        actual_fields = dict(part.split('=', 1) for part in actual.split(',') if '=' in part)
        for key, value in expected_fields.items():
            # 固定上游 item.cpp 的 DUMMY_CRAFTING_QUALITY 只接收此第三方标签。
            # 原文保留，明确报告未参与计算；实际奖励编号及制作属性仍核对。
            if key == 'crafting_quality':
                metadata_only.append(dict(slot=slot, field=key, value=value, reason='upstream_metadata_only'))
                continue
            observed = actual_fields.get(key)
            # 原生装备加载会重排奖励编号；数量与编号仍须逐项一致。
            if key == 'bonus_id' and observed is not None:
                value, observed = sorted(map(int, value.split('/'))), sorted(map(int, observed.split('/')))
            if observed != value:
                raise ValueError(f'原生报告装备不符: {slot}/{key}')
    data = player['collected_data']
    metric = 'raid_dps' if len(sim['players']) > 1 else 'dps'
    damage = sim['statistics']['raid_dps'] if metric == 'raid_dps' else data['dps']
    mean, count = damage['mean'], damage['count']
    if not math.isfinite(mean) or mean <= 0 or count != max(1, iterations - 1) or data['fight_length']['mean'] != 180:
        raise ValueError('原生参考数值或实际样本数无效')
    return dict(dps=mean, metric=metric, personal_dps=data['dps']['mean'], samples=count, seconds=180, metadata_only=metadata_only, notices=report.get('logs', []),
                identity=dict(class_id=player['sim2gse_class_id'], spec_id=player['sim2gse_spec_id'],
                              spec=player['sim2gse_spec'], race=player['race'], role=player['role'], resource=player['sim2gse_resource']))


def _profile_with_import_queries(profile, folder, spell_ids):
    if not spell_ids:
        return profile
    if (not isinstance(spell_ids, (list, tuple)) or len(spell_ids) > 256
            or any(type(spell_id) is not int or spell_id <= 0 for spell_id in spell_ids)):
        raise ValueError('GSE 动作核对的法术编号无效')
    text = Path(profile).read_text(encoding='utf-8')
    probe_profile = Path(folder) / 'import-action-query.simc'
    probe_profile.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not text or text.endswith(('\n', '\r')) else '\n'
    probe_profile.write_text(text + separator +
                             'sim2gse_action_ids=' + ','.join(map(str, sorted(set(spell_ids)))) + '\n',
                             encoding='utf-8')
    return probe_profile


def reference(profile, folder, character, *, runtime=None, iterations=100, seed=20260912,
              simulation_config=None, import_spell_ids=()):
    folder = Path(folder)
    runtime = runtime or TaskRuntime()
    probe_profile = _profile_with_import_queries(profile, folder, import_spell_ids)
    run(profile, folder, options=[f'iterations={iterations}', f'seed={seed}',
        'json2=native.pending.json'], runtime=runtime, simulation_config=simulation_config)
    try:
        report = json.loads((folder / 'native.pending.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('原生参考报告缺失或不是有效 JSON') from error
    if 'dps' not in player_report(report, character)['collected_data']:
        messages = '; '.join(row['message'] for row in report.get('logs', []))
        raise ValueError('原生未提供此角色的伤害模拟：' + messages)
    result = dict(check_report(report, character, iterations, simulation_config=simulation_config),
                  mode='native_free_selection')
    replace_file(folder / 'native.pending.json', folder / 'native.json')
    player = player_report(report, character)
    result['action_sequence'] = player['collected_data'].get('action_sequence', [])
    result['precombat_sequence'] = player['collected_data'].get('action_sequence_precombat', [])
    result['actions_protocol'] = player.get('sim2gse_actions_protocol')
    result['executed_actions'] = player.get('sim2gse_actions', [])
    result['precombat_definitions'] = player.get('sim2gse_precombat_actions', [])
    result['active_items'] = player.get('sim2gse_items', [])
    result['import_action_candidates'] = []
    if import_spell_ids:
        probe_folder = folder / 'import_action_probe'
        run(probe_profile, probe_folder, options=['iterations=1', 'max_time=1'],
            runtime=runtime, simulation_config=simulation_config)
        try:
            probe_report = json.loads((probe_folder / 'native.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ValueError('原生动作查询报告缺失或不是有效 JSON') from error
        probe_player = player_report(probe_report, character)
        result['import_action_candidates'] = probe_player.get('sim2gse_import_actions', [])
    return result
