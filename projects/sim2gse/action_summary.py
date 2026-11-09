"""核验原生业务成功摘要；不从排队或伤害次数猜玩家按键。"""

from collections import Counter
import re
import json

VERSION = 1


def window_text(plan):
    """爆发全失败也须按原冻结窗口断段，不从成功事件猜边界。"""
    if (not isinstance(plan, dict) or any(type(plan.get(k)) is not int for k in
            ('start_ms', 'repeat_ms', 'window_ms'))):
        raise ValueError('成功摘要缺少冻结爆发窗口')
    start, repeat, width = (plan[k] for k in ('start_ms', 'repeat_ms', 'window_ms'))
    if not 0 <= start < 180000 or not 1 <= width <= repeat:
        raise ValueError('成功摘要爆发窗口无效')
    return '/'.join(f'{at},{min(180000, at + width)}' for at in range(start, 180000, repeat))


def checked(value, samples, *, expected_scope=None, position_buttons=None):
    """原始整数计数与有效评分场数一致才可作为引导数据。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as error:
            raise ValueError('原生成功摘要存储文本损坏') from error
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != VERSION:
        raise ValueError('原生成功摘要版本缺失或不支持')
    if type(samples) is not int or samples < 1:
        raise ValueError('原生成功摘要样本无效')
    if (type(value.get('samples')) is not int or value['samples'] != samples
            or type(value.get('duration_ms')) is not int or value['duration_ms'] != samples * 180000):
        raise ValueError('原生成功摘要有效样本或时长不符')
    for field in ('successes', 'pairs', 'outgoing'):
        entries = value.get(field)
        if (not isinstance(entries, dict) or any(not isinstance(k, str) or not k
                or type(n) is not int or n < 0 for k, n in entries.items())):
            raise ValueError('原生成功摘要计数无效: ' + field)
    scope = value.get('scope')
    if (not isinstance(scope, dict) or set(scope) != {'allowed', 'excluded', 'windows', 'policy', 'controlled'}
            or not isinstance(scope['windows'], str) or not isinstance(scope['policy'], str)
            or type(scope['controlled']) is not bool
            or any(not isinstance(scope[k], dict) or any(not isinstance(b, str) or not b or v is not True
                for b, v in scope[k].items()) for k in ('allowed', 'excluded'))
            or set(value['successes']) - set(scope['allowed'])
            or set(value['successes']) & set(scope['excluded'])):
        raise ValueError('原生成功摘要按钮范围身份无效')
    if expected_scope is not None and any(scope.get(k) != v for k, v in expected_scope.items()):
        raise ValueError('原生成功摘要与本次请求范围身份不符')
    successes = value['successes']
    outgoing = Counter()
    for pair, count in value['pairs'].items():
        parts = pair.split('>')
        if len(parts) != 2 or any(key not in successes for key in parts):
            raise ValueError('原生成功摘要相邻按钮无效')
        outgoing[parts[0]] += count
    if dict(outgoing) != value['outgoing'] or any(n > successes.get(k, 0) for k, n in outgoing.items()):
        raise ValueError('原生成功摘要相邻分母不符')
    if not isinstance(value.get('positions', {}), dict):
        raise ValueError('原生成功摘要来源位置无效')
    positions = Counter()
    for key, count in value.get('positions', {}).items():
        button, separator, step = key.rpartition('@')
        if (not separator or re.fullmatch(r'(0|[1-9][0-9]*)', step) is None
                or button not in successes or type(count) is not int or count < 0):
            raise ValueError('原生成功摘要来源位置无效')
        if position_buttons is not None and button not in position_buttons.get(int(step), set()):
            raise ValueError('原生成功摘要位置不属于当前程序')
        positions[button] += count
    if (any(n != successes.get(k) for k, n in positions.items())
            or scope['controlled'] and dict(positions) != successes):
        raise ValueError('原生成功摘要来源次数不符')
    witnesses = value.get('witnesses', {})
    if not isinstance(witnesses, dict) or any(
            len(k.split('>')) != 2 or any(b not in successes for b in k.split('>'))
            or not isinstance(v, list) or len(v) != 3
            or any(type(i) is not int or i < 0 for i in v) for k, v in witnesses.items()):
        raise ValueError('原生成功摘要相邻见证无效')
    if position_buttons is not None and any(
            key.split('>')[0] not in position_buttons.get(steps[0], set())
            or key.split('>')[1] not in position_buttons.get(steps[2], set())
            or not position_buttons.get(steps[1]) for key, steps in witnesses.items()):
        raise ValueError('原生成功摘要见证不属于当前程序')
    return value


def scoped(value, capabilities):
    """删掉排除按钮及与它相连的边；绝不把其前后重新接成相邻。"""
    from copy import deepcopy
    keys = sorted({f"spell:{a.get('base_spell_id', a.get('spell_id'))}" if a['kind'] == 'spell'
                   else a['simc_action'] for a in capabilities['actions']})
    result = deepcopy(value)
    result['ordinary_buttons'] = keys
    result['successes'] = {k: v for k, v in value['successes'].items() if k in keys}
    result['pairs'] = {k: v for k, v in value['pairs'].items() if all(b in keys for b in k.split('>'))}
    outgoing = Counter()
    for k, v in result['pairs'].items():
        outgoing[k.split('>')[0]] += v
    result['outgoing'] = dict(outgoing)
    result['positions'] = {k: v for k, v in value.get('positions', {}).items() if k.rpartition('@')[0] in keys}
    result['witnesses'] = {k: v for k, v in value.get('witnesses', {}).items() if all(b in keys for b in k.split('>'))}
    # A middle witness could refer to an excluded skill. Reference witnesses are
    # empty; candidate summaries already exclude burst at the original input.
    return result


def button_key(command):
    return (f"spell:{command.get('base_spell_id', command['spell_id'])}"
            if command['kind'] == 'spell' else command['simc_action'])


def candidate_scope(candidate, burst_candidate=None, windows=''):
    commands = candidate['blocks'] + (burst_candidate['blocks'] if burst_candidate else [])
    allowed = sorted({button_key(c) for block in commands for c in block})
    scope = dict(allowed=dict.fromkeys(allowed, True), excluded={}, windows=windows,
                 policy='/'.join(allowed), controlled=True)
    # Runtime clicks are rebound to this candidate, never to an earlier source tree.
    positions = {i: {button_key(c) for c in block} for i, block in enumerate(candidate['blocks'])
                 if i >= candidate.get('precombat_count', 0)}
    return scope, positions
