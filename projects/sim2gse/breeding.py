"""一次只给一个合法编辑；参考只引导，伤害仍由原评分决定。"""
from copy import deepcopy
from fractions import Fraction
from itertools import groupby
import json

from action_summary import button_key, checked, scoped

VERSION = 1
ORDER = ('target', 'random', 'crossover')


def apply_edit(program, edit):
    """随机与目标共用的增加、删除、替换、交换、移动执行原语。"""
    result = deepcopy(program)
    container = result
    for part in edit.get('path', ()):
        container = container[part]
    index, operation = edit['index'], edit['operation']
    if operation == 'insert':
        container.insert(index, deepcopy(edit['value']))
    elif operation == 'delete':
        del container[index]
    elif operation == 'replace':
        container[index] = deepcopy(edit['value'])
    elif operation == 'swap':
        target = edit['target']
        container[index], container[target] = container[target], container[index]
    elif operation == 'move':
        count = edit.get('count', 1)
        fragment = container[index:index + count]
        del container[index:index + count]
        target = edit['target']
        container[target:target] = fragment
    else:
        raise ValueError('未知基础编辑')
    return result


def _occurrences(program, capabilities):
    keys = {a['simc_action']: button_key(a) for a in capabilities['actions']}
    for a in capabilities['actions']:
        keys.update((v['simc_action'], button_key(a)) for v in a.get('variants', []))
    rows = []
    for segment, node in enumerate(program):
        if isinstance(node, list):
            blocks = [((), segment, node)]
        elif node['kind'] == 'Loop':
            blocks = [((segment, 'blocks'), i, b) for i, b in enumerate(node['blocks'])]
        elif node['kind'] == 'CastSequence':
            blocks = [((segment, 'members'), i, [name]) for i, name in enumerate(node['members'])]
        else:
            continue
        for path, index, block in blocks:
            for member, name in enumerate(block):
                if name not in keys:
                    raise ValueError('目标建议遇到未映射的源按钮')
                scalar = path and path[-1] == 'members'
                rows.append(dict(key=keys[name], path=path, index=index,
                    replace_path=path if scalar else (*path, index),
                    member=index if scalar else member))
    return rows


def _count(container, path):
    for part in path:
        container = container[part]
    return len(container)


def _token(edit):
    return json.dumps(edit, sort_keys=True, separators=(',', ':'))


def _legal_edits(program, edits, legal):
    choices, seen = [], set()
    for edit in edits:
        token = _token(edit)
        if token in seen:
            continue
        seen.add(token)
        result = apply_edit(program, edit)
        if result == program:
            continue
        try:
            legal(result)
        except ValueError:
            continue
        choices.append(edit)
    return choices


def _moves(program, row):
    for target in range(_count(program, row['path'])):
        if target != row['index']:
            yield dict(operation='move', path=row['path'], index=row['index'], target=target)


def _insertions(program, name, capacity):
    if len(program) < capacity:
        for index in range(len(program) + 1):
            yield dict(operation='insert', path=(), index=index, value=[name])


def target_mutation(program, capabilities, rng, reference, current, legal):
    """频率与相邻关系各最多一条；无建议保持原样，不补一次随机。"""
    if not isinstance(reference, dict) or not isinstance(current, dict):
        raise ValueError('目标变异缺少当前条件的父本或参考成功摘要')
    reference = scoped(checked(reference, reference.get('samples')), capabilities)
    current = scoped(checked(current, current.get('samples')), capabilities)
    rows = _occurrences(program, capabilities)
    actions = {button_key(a): a['simc_action'] for a in reversed(capabilities['actions'])}
    capacity = 128 - len(capabilities.get('precombat_actions', []))
    differences = {key: Fraction(reference['successes'].get(key, 0), reference['duration_ms'])
        - Fraction(current['successes'].get(key, 0), current['duration_ms']) for key in actions}
    ordered = sorted(actions, key=lambda key: (-abs(differences[key]), key))
    frequency = None
    for key in ordered:
        delta = differences[key]
        if not delta:
            continue
        own = [row for row in rows if row['key'] == key]
        if delta > 0:
            additions = _legal_edits(program, _insertions(program, actions[key], capacity), legal)
            if own:
                movements = _legal_edits(program, (edit for row in own for edit in _moves(program, row)), legal)
                # Choose the operation family first: landing-point count never
                # turns the agreed 50/50 choice into a different probability.
                families = [group for group in (additions, movements) if group]
                if families:
                    frequency = (rng.choice(rng.choice(families)), ['frequency_insufficient'])
            else:
                if additions:
                    frequency = (rng.choice(additions), ['frequency_missing'])
                else:
                    replacements = [dict(operation='replace', path=row['replace_path'], index=row['member'],
                        value=actions[key]) for row in rows if differences[row['key']] < 0]
                    choices = _legal_edits(program, replacements, legal)
                    if choices:
                        frequency = (rng.choice(choices), ['frequency_missing_replace'])
        else:
            deficient = [k for k in ordered if differences[k] > 0]
            replacements = [dict(operation='replace', path=row['replace_path'], index=row['member'],
                value=actions[k]) for k in deficient for row in own]
            choices = _legal_edits(program, replacements, legal)
            if not choices:
                deletes = []
                for row in own:
                    # Delete the whole one-command block; never leave an empty
                    # ordinary block that would silently turn into a wait.
                    path = row['replace_path']
                    if not (row['path'] and row['path'][-1] == 'members') and _count(program, path) == 1:
                        deletes.append(dict(operation='delete', path=row['path'], index=row['index']))
                    else:
                        deletes.append(dict(operation='delete', path=path, index=row['member']))
                choices = _legal_edits(program, deletes, legal)
            if choices:
                frequency = (rng.choice(choices), ['frequency_excess'])
        if frequency:
            break

    def probability(summary, a, b):
        denominator = summary['outgoing'].get(a, 0)
        return Fraction(summary['pairs'].get(a + '>' + b, 0), denominator) if denominator else None

    # Rebind all runtime clicks once, including shared behavior-cache hits.
    # Rebuilding a 4096-click expansion separately for each click is quadratic.
    from search import _parent_positions
    steps = sorted({int(position.rsplit('@', 1)[1]) for position, count in current.get('positions', {}).items() if count})
    bound = _parent_positions(program, capabilities,
        [dict(click_position=step, action_position=None) for step in steps])
    sources = {row['click_position']:row['source_position'] for row in bound}
    def locations_for_step(step, key):
        source = sources.get(step)
        if source is None:
            return []
        path = ((source['segment'], 'blocks') if 'loop_block' in source else
                (source['segment'], 'members') if isinstance(program[source['segment']], dict)
                    and program[source['segment']]['kind'] == 'CastSequence' else ())
        index = source.get('loop_block', source['segment'])
        matches = [row for row in rows if row['key'] == key and row['path'] == path
                   and (path and path[-1] == 'members' or row['index'] == index)]
        return [] if path and path[-1] == 'members' and len(matches) > 1 else matches

    successful = {}
    unbound_buttons = set()
    for position, count in current.get('positions', {}).items():
        if count:
            key, step = position.rsplit('@', 1)
            matches = locations_for_step(int(step), key)
            units = {(tuple(row['path']), row['index']) for row in matches}
            if len(units) != 1:
                unbound_buttons.add(key)
            for row in matches:
                successful[_token(row)] = row
    def unit(row):
        return (tuple(row['path']), row['index'])
    by_button = {}
    for row in successful.values():
        by_button.setdefault(row['key'], {})[unit(row)] = row
    adjacent = {}
    def add_pair(a, b, first, last):
        adjacent.setdefault((a, b), {})[(unit(first), unit(last))] = (first, last)
    # An aggregate actual pair is unambiguous when every success of each button
    # belongs to just one source node. Multiple source nodes need a real witness.
    for pair, count in current['pairs'].items():
        a, b = pair.split('>')
        left, right = list(by_button.get(a, {}).values()), list(by_button.get(b, {}).values())
        if count and a not in unbound_buttons and b not in unbound_buttons and len(left) == len(right) == 1:
            add_pair(a, b, left[0], right[0])
    step_keys = {}
    for position, count in current.get('positions', {}).items():
        if count:
            key, step = position.rsplit('@', 1)
            step_keys.setdefault(int(step), set()).add(key)
    for pair, witness in current.get('witnesses', {}).items():
        first, last = pair.split('>')
        middle = step_keys.get(witness[1], set())
        if len(middle) != 1:
            continue
        middle = next(iter(middle))
        triple = [(first, witness[0]), (middle, witness[1]), (last, witness[2])]
        for (a, i), (b, j) in zip(triple, triple[1:]):
            if not current['pairs'].get(a + '>' + b, 0):
                raise ValueError('成功三点见证与相邻计数不符')
            left, right = locations_for_step(i, a), locations_for_step(j, b)
            # A single runtime click can contain repeated castsequence members;
            # do not guess which source member produced the witnessed event.
            if len(left) == len(right) == 1:
                add_pair(a, b, left[0], right[0])
    temporal = None
    pairs = [(a, b) for a in sorted(actions) for b in sorted(actions)]
    for rule in ('reverse', 'repeat', 'connection'):
        proposals = []
        for a, b in pairs:
            r_ab, c_ab = probability(reference, a, b), probability(current, a, b)
            if r_ab is None or c_ab is None:
                continue
            if rule == 'reverse':
                r_ba, c_ba = probability(reference, b, a), probability(current, b, a)
                if (a == b or r_ba is None or c_ba is None or not
                        (r_ab > r_ba and c_ba > c_ab and r_ab > c_ab)):
                    continue
                strength, reason = r_ab - c_ab, 'sequence_reverse'
            elif rule == 'repeat':
                r_aa, c_aa = probability(reference, a, a), probability(current, a, a)
                if (a == b or r_aa is None or c_aa is None or c_aa <= r_aa or not r_ab):
                    continue
                followers = [(probability(reference, a, k), k) for k in actions if k != a]
                best = sorted(((-p, k) for p, k in followers if p is not None and p > 0))
                if not best or b != best[0][1]:
                    continue
                strength, reason = c_aa - r_aa, 'sequence_repeat'
            else:
                if a == b or r_ab <= c_ab:
                    continue
                strength, reason = r_ab - c_ab, 'sequence_connection_soft'
            if rule == 'reverse':
                locations = [(last, first) for first, last in adjacent.get((b, a), {}).values()]
            elif rule == 'repeat':
                locations = []
                for first, last in adjacent.get((a, a), {}).values():
                    if first['path'] != last['path']:
                        continue
                    locations.extend((first, row) for row in rows if row['key'] == b
                        and row['path'] == first['path'] and unit(row) not in (unit(first), unit(last)))
            else:
                locations = [(first, second) for first in rows if first['key'] == a
                    for second in rows if second['key'] == b and first['path'] == second['path']]
            for first, second in locations:
                if first['path'] != second['path']:
                    continue
                proposals.append((strength, a, b, dict(operation='move', path=second['path'],
                    index=second['index'], target=first['index'] + (second['index'] > first['index'])), reason))
                if rule == 'reverse':
                    proposals.append((strength, a, b, dict(operation='swap', path=first['path'],
                        index=first['index'], target=second['index']), reason))
            if rule == 'connection':
                witness = current.get('witnesses', {}).get(a + '>' + b)
                if witness:
                    firsts, lasts = locations_for_step(witness[0], a), locations_for_step(witness[2], b)
                    # Only a uniquely identified middle button proves a blocker;
                    # a multi-command runtime click alone cannot prove its key.
                    middle_keys = step_keys.get(witness[1], set())
                    if len(middle_keys) == 1 and middle_keys.isdisjoint({a, b}):
                        for first in firsts:
                            for last in lasts:
                                if first['path'] == last['path']:
                                    proposals.append((strength, a, b, dict(operation='move', path=last['path'],
                                        index=last['index'], target=first['index'] + (last['index'] > first['index'])),
                                        'sequence_connection_witness'))
        priority = lambda item: (-item[0], item[1], item[2], item[4] != 'sequence_connection_witness')
        ordered_proposals = sorted(proposals, key=lambda item: (*priority(item), _token(item[3])))
        for _, group in groupby(ordered_proposals, priority):
            equivalent = {}
            for _, a, b, edit, reason in group:
                if _legal_edits(program, [edit], legal):
                    equivalent.setdefault(_token(edit), (edit, reason))
            if equivalent:
                edit, reason = rng.choice(list(equivalent.values()))
                temporal = (edit, [reason])
                break
        if temporal:
            break
    suggestions = {}
    for suggestion in (frequency, temporal):
        if suggestion is None:
            continue
        edit, evidence = suggestion
        token = _token(edit)
        if token not in suggestions:
            suggestions[token] = (edit, [])
        suggestions[token][1].extend(evidence)
    if not suggestions:
        return deepcopy(program), dict(actual_mutation='no_change', evidence=[])
    edit, evidence = rng.choice(list(suggestions.values()))
    return apply_edit(program, edit), dict(actual_mutation=edit['operation'],
        modification_position=edit, evidence=sorted(set(evidence)))


def random_operations(program, capabilities, reset_flags=()):
    """先移除明显无效类型；复杂语法仍交现有实现处理。"""
    from simulation_config import syntax_for
    syntax = syntax_for(capabilities.get('search_syntax'))
    capacity = 128 - len(capabilities.get('precombat_actions', []))
    ordinary = [b for b in program if isinstance(b, list)]
    loops = [b for b in program if isinstance(b, dict) and b['kind'] == 'Loop']
    sequences = [b for b in program if isinstance(b, dict) and b['kind'] == 'CastSequence']
    names = [a['simc_action'] for a in capabilities['actions']]
    spells = {a['simc_action'] for a in capabilities['actions'] if a['kind'] == 'spell'}
    from sequence import select
    def legal_block(block):
        try:
            select(capabilities, [block])
            return True
        except ValueError:
            return False
    can_replace = any(legal_block(block[:i] + [name] + block[i+1:])
        for block in ordinary for i, old in enumerate(block) for name in names if name != old)
    can_grow = len(program) < capacity and sum(len(b['blocks']) if isinstance(b, dict) and b['kind'] == 'Loop' else 1
        for b in program if not isinstance(b, dict) or b['kind'] != 'WaitClicks') < capacity
    distinct = len({_token({'value': b}) for b in program}) > 1
    operations = []
    if len(program) > 1 and distinct:
        operations.append('swap')
    if can_replace:
        operations.append('replace')
    if can_grow:
        operations.append('insert')
    if len(program) > 1:
        operations.append('delete')
    if len(program) > 2 and distinct:
        operations.append('move')
    if syntax['multi_command_blocks'] and any(len(block) > 1 or any(legal_block(block+[name]) for name in names)
            for block in ordinary):
        operations.append('block')
    if syntax['loop'] and (loops or ordinary):
        operations.append('repeat_count' if loops else 'loop')
    if syntax['wait_clicks'] and (can_grow or any(isinstance(b, dict) and b['kind'] == 'WaitClicks' for b in program)):
        operations.append('wait_clicks')
    if syntax['castsequence']:
        if sequences and len(spells) > 1:
            operations.append('castsequence_member')
        elif not sequences and any(isinstance(a, list) and isinstance(b, list) and len(a) == len(b) == 1
                and a[0] in spells and b[0] in spells for a, b in zip(program, program[1:])):
            operations.append('castsequence')
        if sequences:
            operations.append('castsequence_reset')
            if reset_flags:
                operations.append('castsequence_reset_flag')
    return operations
