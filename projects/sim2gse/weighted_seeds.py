"""The pilot's 50/50 proposal rule, shared with manual source preparation."""
from action_summary import button_key


def generate(capabilities, reference, rng, *, count, excluded, legal, check,
             progress=None, checkpoint=None):
    from search import _tuple
    actions = capabilities['actions']
    total = sum(reference['successes'].values())
    if not actions or total <= 0:
        raise ValueError('参考成功总量或合法技能池无效')
    weights = [.5 * reference['successes'].get(button_key(a), 0) / total + .5 / len(actions)
               for a in actions]
    names = [a['simc_action'] for a in actions]
    bound = 128 - len(capabilities.get('precombat_actions', []))
    if bound < 1:
        raise ValueError('战前动作占满长度，无法新增普通循环')
    state = progress if progress is not None else dict(programs=[], attempts=0, invalid=0, duplicates=0)
    if 'rng' in state:
        rng.setstate(_tuple(state['rng']))
    seen = set(excluded) | {legal(p) for p in state['programs']}
    while len(state['programs']) < count and state['attempts'] < 11 * count:
        check()
        state['attempts'] += 1
        program = [[name] for name in rng.choices(names, weights, k=rng.randint(1, bound))]
        try:
            identity = legal(program)
        except ValueError:
            state['invalid'] += 1
        else:
            if identity in seen:
                state['duplicates'] += 1
            else:
                seen.add(identity)
                state['programs'].append(program)
        state['rng'] = rng.getstate()
        if checkpoint:
            checkpoint(state)
    if len(state['programs']) != count:
        raise ValueError(f'新增起点在{11 * count}次提案内未补足{count}个不同行为')
    return state
