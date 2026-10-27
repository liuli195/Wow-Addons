"""从已验原生统计建立固定行为坐标；不读取伤害 tick 或按键尝试。"""
import math

from engine import player_report


VERSION = 'native-executions-player-buffs-v2'
# eed90915, sc_death_knight.cpp constructors and spell lookups. These are
# registered, non-quiet top-level button stats, not inferred damage effects.
UNHOLY_BUTTONS = dict(outbreak=77575, scourge_strike=55090, festering_strike=85948,
                     soul_reaper=343294, putrefy=1247378, death_coil=47541,
                     epidemic=207317, death_and_decay=43265)
# set_replacement_action/execute (6055-6075, 6242-6256): child stats' executes
# are already counted by the parent. WCL reporting mode instead leaves these
# two replacements top-level, so only their TOP-LEVEL counts are added.
UNHOLY_TOP_REPLACEMENTS = dict(death_coil=('necrotic_coil', 1242174),
                              festering_strike=('festering_scythe', 458128))


def _number(value, label, maximum=None):
    if (type(value) not in (int, float) or not math.isfinite(value) or value < 0
            or maximum is not None and value > maximum):
        raise ValueError('行为描述' + label + '无效')
    return float(value)


def _player(report, character):
    if report.get('report_version') != '2.0.0' or report.get('version') != '1210-01':
        raise ValueError('行为描述报告版本未经验证')
    player = player_report(report, character)
    for field in ('stats', 'buffs', 'buffs_constant'):
        if not isinstance(player.get(field), list):
            raise ValueError('行为描述缺少完整报告字段: ' + field)
    return player


def _owned(row, name):
    owner, actor, index = (row.get(field) for field in
                           ('sim2gse_owner_type', 'sim2gse_actor_name', 'sim2gse_actor_index'))
    if (owner not in ('player', 'owned_unit') or not isinstance(actor, str) or not actor.strip()
            or type(index) is not int or index < 0 or owner == 'player' and actor != name):
        raise ValueError('行为动作原生归属或角色身份无效')
    return owner == 'player'


def _stats(rows, ancestors=()):
    for row in rows:
        yield row, ancestors
        children = row.get('children', [])
        # Stored reports normalize an omitted optional children field to null.
        if children is None:
            children = []
        if not isinstance(children, list):
            raise ValueError('行为动作统计布局无效')
        yield from _stats(children, (*ancestors, row))


def _identity(row):
    return {key: row.get(key) for key in ('name', 'id', 'item_id')}


def _matches(player, route, name):
    matches = []
    for row, ancestors in _stats(player['stats']):
        if row.get('name') != route['name'] or not _owned(row, name):
            continue
        if _identity(row) != route:
            raise ValueError('行为动作身份与冻结映射不符: ' + route['name'])
        matches.append((row, ancestors))
    if len(matches) > 1:
        raise ValueError('行为动作统计布局重复或顶层/子项冲突: ' + route['name'])
    return matches


def _frequency(player, dimension, name):
    base = _identity(dimension)
    base_matches = _matches(player, base, name)
    if base_matches and base_matches[0][1]:
        raise ValueError('基础按钮统计布局必须为顶层')
    base_count = (_number(base_matches[0][0].get('num_executes', {}).get('mean'), '执行次数')
                  if base_matches else 0.)
    total, included = base_count, 0.
    for route in dimension.get('variants', []):
        matches = _matches(player, route, name)
        if not matches:
            continue
        row, ancestors = matches[0]
        count = _number(row.get('num_executes', {}).get('mean'), '执行次数')
        if ancestors:
            if (len(ancestors) != 1 or _identity(ancestors[0]) != base
                    or not _owned(ancestors[0], name) or not base_matches):
                raise ValueError('替换形态统计布局不属于已累计的基础按钮')
            included += count
        else:
            total += count
    if included > base_count:
        raise ValueError('替换形态统计布局的执行次数超过父项累计次数')
    return total


def context_for(report, character, capabilities):
    """参考实际出现的顶层对象证明非 quiet/非子统计，再冻结零省略规则。

    report_json.cpp 的顶层 stats 仅在无执行且无伤害时省略。
    已核实邪恶按钮注册允许未执行省略；其它未出现对象明确拒绝。
    start_attack 仅开关自动攻击，不把挥击次数当作按钮执行频率。
    首期关键玩家增益取邪恶专精注册的 runic_corruption（源码15859）；
    不把宠物 dark_transformation 或天赋触发列表按名字并入。
    """
    player = _player(report, character)
    unholy = player.get('sim2gse_class') == 'deathknight' and player.get('sim2gse_spec_id') == 252
    dimensions = []
    for action in capabilities['actions']:
        if action['kind'] == 'start_attack':
            continue
        routes = []
        for variant in [action, *action.get('variants', [])]:
            if action['kind'] == 'item':
                matches = [row for row in player['stats'] if _owned(row, character.name)
                           and row.get('item_id') == action['item_id']]
                if len(matches) != 1:
                    raise ValueError('行为动作缺少唯一原生执行统计映射: ' + variant['simc_action'])
                route = _identity(matches[0])
            else:
                spell = variant.get('native_spell_id', variant.get('spell_id'))
                route = dict(name=variant['simc_action'], id=spell, item_id=None)
                registered = unholy and (UNHOLY_BUTTONS.get(route['name']) == spell
                    or (route['name'], spell) == UNHOLY_TOP_REPLACEMENTS.get(action['simc_action']))
                if not _matches(player, route, character.name) and not registered:
                    raise ValueError('行为动作缺少唯一原生执行统计映射: ' + route['name'])
            if route not in routes:
                routes.append(route)
        if unholy and UNHOLY_BUTTONS.get(action['simc_action']) == action.get('spell_id'):
            replacement = UNHOLY_TOP_REPLACEMENTS.get(action['simc_action'])
            if replacement:
                route = dict(name=replacement[0], id=replacement[1], item_id=None)
                if route not in routes:
                    routes.append(route)
        dimension = dict(routes[0], variants=routes[1:])
        if dimension not in dimensions:
            dimensions.append(dimension)
    if not dimensions:
        raise ValueError('行为描述没有受支持的可按动作频率')
    buffs = []
    if unholy:
        matches = [row for row in player['buffs'] + player['buffs_constant']
                   if row.get('name') == 'runic_corruption']
        # sc_death_knight.cpp:15231/15859 binds spell 51460 to this player,
        # even if no candidate (including the reference) ever triggers it.
        if len(matches) > 1 or matches and (matches[0].get('spell') != 51460 or 'source' in matches[0] or 'target' in matches[0]):
            raise ValueError('玩家关键增益注册/身份依据不足或歧义: runic_corruption')
        buffs.append(dict(name='runic_corruption', spell=51460))
    context = dict(version=VERSION, actions=dimensions, buffs=buffs,
                   class_name=character.class_name, spec_id=player['sim2gse_spec_id'])
    context['reference_rate'] = sum(describe(report, character, context)['frequencies'])
    if context['reference_rate'] <= 0:
        raise ValueError('参考总执行频率必须大于零')
    return context


def describe(report, character, context):
    player = _player(report, character)
    if (context.get('version') != VERSION or context['class_name'] != character.class_name
            or context['spec_id'] != player['sim2gse_spec_id']):
        raise ValueError('行为描述冻结上下文与角色不符')
    seconds = _number(player['collected_data']['fight_length'].get('mean'), '战斗时间')
    if seconds <= 0:
        raise ValueError('行为描述战斗时间必须大于零')
    frequencies = []
    for dimension in context['actions']:
        frequencies.append(_frequency(player, dimension, character.name) * 60 / seconds)
    coverage = []
    for dimension in context['buffs']:
        named = [row for row in player['buffs'] + player['buffs_constant'] if row.get('name') == dimension['name']]
        if (len(named) > 1 or named and (named[0].get('spell') != dimension['spell']
                or 'source' in named[0] or 'target' in named[0])):
            raise ValueError('玩家关键增益身份歧义: ' + dimension['name'])
        coverage.append(_number(named[0].get('uptime', 0.) if named else 0., '增益覆盖', 100) / 100)
    return dict(frequencies=frequencies, coverage=coverage)


def distance(left, right, context, alpha):
    if any(len(row['frequencies']) != len(context['actions']) or len(row['coverage']) != len(context['buffs'])
           for row in (left, right)):
        raise ValueError('行为描述维度与冻结上下文不符')
    delta = sum(abs(a - b) for a, b in zip(left['frequencies'], right['frequencies'])) / context['reference_rate']
    frequency = delta / (1 + delta)
    if not context['buffs']:
        return frequency
    coverage = sum(abs(a - b) for a, b in zip(left['coverage'], right['coverage'])) / len(context['buffs'])
    return alpha * frequency + (1 - alpha) * coverage
