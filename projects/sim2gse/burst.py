"""人工审核的专精爆发定义；不搜索或自动发布内容。"""
import copy
import hashlib
import json
import re
from result_store import read_records, write


def definition_id(definition):
    content = {key: value for key, value in definition.items() if key != 'definition_id'}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def talent_hash(character):
    values = {key: character.fields.get(key, '') for key in ('talents', 'omnium_talents')}
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(definition):
    if (not isinstance(definition, dict) or definition.get('protocol') != 1
            or definition.get('status') != 'reviewed'
            or not all(isinstance(definition.get(key), str) and definition[key]
                       for key in ('version', 'class_key', 'data_version', 'reviewer', 'reviewed_at',
                                   'instructions', 'applicability'))
            or type(definition.get('spec_id')) is not int or definition['spec_id'] <= 0):
        raise ValueError('爆发定义未审核或记录格式无效')
    for key in ('sources', 'talent_hashes'):
        values = definition.get(key)
        if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
            raise ValueError('爆发定义缺少来源或已审核天赋')
    if any(re.fullmatch(r'[0-9a-f]{64}', value) is None for value in definition['talent_hashes']):
        raise ValueError('爆发定义天赋身份无效')
    plan = definition.get('plan', {})
    if (not isinstance(plan, dict) or any(type(plan.get(k)) is not int or plan[k] <= 0
            for k in ('start_ms', 'repeat_ms', 'window_ms', 'interval_ms'))
            or plan['start_ms'] >= 180000 or plan['window_ms'] >= plan['repeat_ms']
            or plan['interval_ms'] >= plan['window_ms']
            or plan.get('pause_loop') is not True or plan.get('preserve_position') is not True):
        raise ValueError('爆发按键计划无效')
    blocks = definition.get('blocks')
    if (not isinstance(blocks, list) or not 1 <= len(blocks) <= 128
            or any(not isinstance(b, list) or not 1 <= len(b) <= 16 for b in blocks)):
        raise ValueError('爆发动作块无效')
    excluded = definition.get('excluded_spell_ids')
    if not isinstance(excluded, list) or any(type(v) is not int or v <= 0 for v in excluded):
        raise ValueError('爆发排除身份无效')
    for block in blocks:
        for command in block:
            if not isinstance(command, dict) or command.get('kind') not in {'spell', 'item', 'potion'}:
                raise ValueError('爆发包含不支持的动作')
            if (not isinstance(command.get('name'), str) or not command['name']
                    or '\n' in command['name'] or '\r' in command['name']):
                raise ValueError('爆发动作名称无效')
            if command['kind'] == 'spell':
                if (type(command.get('spell_id')) is not int or command['spell_id'] not in excluded
                        or not isinstance(command.get('simc_action'), str)
                        or re.fullmatch(r'[a-z0-9_]+', command['simc_action']) is None):
                    raise ValueError('爆发技能身份无效')
            elif command['kind'] == 'item':
                if command.get('slot') not in (13, 14) or command.get('simc_action') != (
                        'use_item,slot=trinket1' if command['slot'] == 13 else 'use_item,slot=trinket2'):
                    raise ValueError('爆发饰品槽位无效')
            elif (definition.get('potion') != 'potion_of_recklessness'
                  or command.get('item_id') != 241289 or command.get('simc_action') != 'potion'
                  or command['name'] != '鲁莽药水'):
                raise ValueError('爆发药水身份无效')


def publish(definition):
    """显式发布已审核内容；先保留历史，再原子替换本专精的当前记录。"""
    row = copy.deepcopy(definition)
    validate(row)
    row['definition_id'] = definition_id(row)
    previous = read_records('burst_definitions', f"current_{row['spec_id']}")
    if previous and previous[0].get('version') == row['version'] and previous[0].get('definition_id') != row['definition_id']:
        raise ValueError('同版本爆发内容不同，请使用新版本号')
    write('burst_definitions', 'history_' + row['definition_id'], [row])
    write('burst_definitions', f"current_{row['spec_id']}", [row])
    return row


def load(spec_id):
    rows = read_records('burst_definitions', f'current_{spec_id}')
    if not rows:
        raise ValueError('此专精没有已审核的爆发定义')
    if len(rows) != 1:
        raise ValueError('爆发定义记录不唯一')
    row = rows[0]
    validate(row)
    if row.get('definition_id') != definition_id(row) or row['spec_id'] != spec_id:
        raise ValueError('爆发定义身份不符')
    return row


def select_definition(character):
    """原生初始化前选定审核记录；随后仍核验原生专精编号。"""
    from result_store import query, iter_rows
    with query("SELECT table_name FROM information_schema.tables WHERE table_name='burst_definitions'") as cursor:
        if not cursor.fetchone():
            raise ValueError('此专精没有已审核的爆发定义')
    ids = iter_rows('SELECT DISTINCT spec_id FROM burst_definitions WHERE class_key = ?',
                    [character.class_name])
    matches = []
    for row in ids:
        rows = read_records('burst_definitions', f"current_{row['spec_id']}")
        if rows and talent_hash(character) in rows[0].get('talent_hashes', []):
            matches.append(load(row['spec_id']))
    if len(matches) != 1:
        raise ValueError('当前角色天赋没有唯一适用的已审核爆发定义')
    return matches[0]


def prepare(definition, character, capabilities, native_identity):
    """按真实角色目录解析审核命令，不删除缺失动作。"""
    validate(definition)
    if (character.class_name != definition['class_key']
            or native_identity['spec_id'] != definition['spec_id']
            or native_identity.get('data_version') != definition['data_version']
            or talent_hash(character) not in definition['talent_hashes']):
        raise ValueError('当前角色、天赋或模拟版本不适用此爆发定义')
    blocks = []
    for block in definition['blocks']:
        commands = []
        for requested in block:
            if requested['kind'] == 'potion':
                command = dict(requested, potion=definition['potion'], gcd_ms=0)
            else:
                matches = [action for action in capabilities['actions'] if
                           (action['kind'] == 'spell' and requested['kind'] == 'spell'
                            and action['spell_id'] == requested['spell_id'])
                           or (action['kind'] == 'item' and requested['kind'] == 'item'
                               and action['slot'] == requested['slot'])]
                if len(matches) != 1:
                    raise ValueError('爆发动作不适用当前角色: ' + requested['name'])
                command = dict(matches[0], name=requested['name'])
            commands.append(command)
        if len({c.get('base_spell_id', c['simc_action']) for c in commands if c.get('gcd_ms', 0) > 0}) > 1:
            raise ValueError('爆发同块包含多个公共冷却动作，需要分别按键')
        blocks.append(commands)
    return blocks


def input_times(definition, interval_ms=None):
    plan = definition['plan']
    interval = plan['interval_ms'] if interval_ms is None else interval_ms
    if type(interval) is not int or interval < 1:
        raise ValueError('爆发按键间隔无效')
    times = [at for start in range(plan['start_ms'], 180000, plan['repeat_ms'])
             for at in range(start, min(start + plan['window_ms'], 180000), interval)]
    if len(times) > 4096:
        raise ValueError('爆发输入次数超过限制')
    return times


def combined_inputs(loop_times, definition, interval_ms):
    """爆发窗口不发循环输入；窗口后续原循环位置，不补同刻点击。"""
    plan = definition['plan']
    windows = list(range(plan['start_ms'], 180000, plan['repeat_ms']))
    loop = [at for at in loop_times if not any(start <= at < start + plan['window_ms'] for start in windows)]
    rows = sorted([(at, 'loop') for at in loop] + [(at, 'burst') for at in input_times(definition, interval_ms)])
    if len(rows) > 4096 or any(a[0] == b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('双来源按键时间重复或超过限制')
    return [row[0] for row in rows], [row[1] for row in rows]


def search_capabilities(capabilities, blocks):
    """排除实际审核块里的按钮及其替换形态，不改原生伤害目录。"""
    policy = dict(spell_ids=[], actions=[], slots=[], item_ids=[])
    for block in blocks:
        for command in block:
            policy['actions'].append(command['simc_action'])
            if command['kind'] == 'spell':
                for variant in [command, *command.get('variants', [])]:
                    policy['spell_ids'].extend(value for value in
                        (variant.get('spell_id'), variant.get('base_spell_id')) if value)
            elif command['kind'] == 'item':
                policy['slots'].append(command['slot'])
                if command.get('item_id'):
                    policy['item_ids'].append(command['item_id'])
    policy = {key: sorted(set(values)) for key, values in policy.items()}
    filtered = copy.deepcopy(capabilities)
    filtered['burst_exclusions'] = policy
    for key in ('actions', 'baseline_actions', 'precombat_actions'):
        if key in filtered:
            filtered[key] = [action for action in filtered[key] if not _excluded(action, policy)]
    if not filtered['actions']:
        raise ValueError('爆发排除后没有可搜索的循环动作')
    return filtered


def _excluded(command, policy):
    variants = [command, *command.get('variants', [])]
    return any(value.get('simc_action') in policy['actions']
               or value.get('spell_id') in policy['spell_ids']
               or value.get('base_spell_id') in policy['spell_ids']
               or value.get('kind') == 'item' and (
                   value.get('slot') in policy['slots'] or value.get('item_id') in policy['item_ids'])
               for value in variants)


def check_loop(program, capabilities):
    """编译前递归核对循环树；含排除动作则拒绝整条，不局部删除。"""
    policy = capabilities.get('burst_exclusions')
    if policy is None:
        return
    def visit(nodes):
        for node in nodes:
            if node.get('kind') == 'Loop':
                visit(node['body'])
            for command in node.get('commands', []):
                commands = ([action for action in command.get('actions', [])
                             if action.get('simc_action') in command.get('members', [])]
                            if command.get('kind') == 'castsequence' else [command])
                if any(_excluded(action, policy) for action in commands):
                    raise ValueError('普通循环包含当前爆发宏的动作，整条候选不可使用')
    visit(program['nodes'])


def compile_context(definition, character, capabilities, native_identity, folder, runtime):
    from program import from_action_blocks, compile_program
    blocks = prepare(definition, character, capabilities, native_identity)
    program = from_action_blocks(blocks)
    program['metadata'].update(purpose='burst', instructions=definition['instructions'])
    candidate = compile_program(program, folder, identity=native_identity, runtime=runtime)
    candidate['source'] = 'burst'
    return dict(definition_id=definition['definition_id'], plan=definition['plan'],
                candidate=candidate, instructions=definition['instructions'])
