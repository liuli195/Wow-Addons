"""通用规则契约和有界静态排位过程；不执行APL、不模拟战斗。"""
from bisect import bisect_left
import math

VERSION = 'static-rule-start-v1'
RULES = (
    ('window_or_full', '窗口或满充能释放', 'CD/充能及窗口', '前移或补尝试'),
    ('reserve', '低优先消费预留', '指定低位条目及完整OR条件', '减少或后移低位消费'),
    ('near_cap', '近满资源消费', '资源缺口、完整条件和前序让位', '前移或补消费'),
    ('short_window', '短窗口指定动作', '指定Buff及动作GCD', '分散指定按钮尝试'),
    ('protected_burst', '普通循环配合固定爆发', '冻结爆发输入和普通位置', '只调整普通排列'),
    ('ordinary_cooldown', '普通CD按源条件尝试', '完整条件及前序让位', '前移或补普通CD'),
    ('maintenance', '持续效果按条件补齐', '完整持续效果条件及有来源间隔', '低频或间隔安排'),
    ('avoid_idle', '减少可避免GCD空闲', '前七项及具体可用动作证据', '仅减少已证多余等待'),
)


def _number(value, label, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or positive and value == 0):
        raise ValueError('规则起点缺少有效静态字段: ' + label)
    return value


def generate(capabilities, reference, *, binding, input_interval_ms=300, target_count=1, burst=None):
    snapshot = reference.get('static_snapshot')
    if (not isinstance(snapshot, dict) or snapshot.get('protocol') != 1
            or snapshot.get('stage') != 'precombat_initialized_before_actions'):
        raise ValueError('规则起点缺少真实角色静态快照，请重新构建引擎')
    for key in ('resources', 'actions'):
        if key not in snapshot:
            raise ValueError('规则起点缺少静态字段: ' + key)
    resource = binding['resource']
    recovery = binding.get('recovery')
    if not isinstance(recovery, dict) or recovery.get('model') not in ('none', 'parallel_discrete'):
        raise ValueError('规则起点尚不支持绑定的资源恢复模型')
    constraint = recovery.get('resource') if recovery['model'] == 'parallel_discrete' else None
    if recovery['model'] == 'parallel_discrete' and (not constraint or constraint == resource):
        raise ValueError('离散恢复模型缺少独立资源身份')
    resources = (resource, constraint) if constraint is not None else (resource,)
    initial = {}
    capacities = {}
    for name in resources:
        row = snapshot['resources'].get(name, {})
        initial[name] = _number(row.get('current'), name+'.current')
        capacities[name] = _number(row.get('maximum'), name+'.maximum', positive=True)
        if initial[name] > capacities[name]:
            raise ValueError('静态资源初值超过容量: ' + name)
    recharge, slots = 0, 0
    if recovery['model'] == 'parallel_discrete':
        recharge = _number(recovery.get('interval_ms'), 'recovery.interval_ms', positive=True)
        slots = _number(recovery.get('slots'), 'recovery.slots', positive=True)
        if (slots != int(slots) or not 1 <= slots <= capacities[constraint]
                or capacities[constraint] != int(capacities[constraint])):
            raise ValueError('离散恢复模型需要整数资源容量及有效并行槽位')
        slots = int(slots)
        if initial[constraint] != capacities[constraint]:
            raise ValueError('离散恢复模型初值非满且缺少逐单位恢复状态: ' + constraint)
    required = set(binding['generators'] + binding['cooldowns'] + binding['buff_actions'] + [binding['spender']])
    if binding['periodic_action']:
        required.add(binding['periodic_action'])
    stats = {}
    for row in snapshot['actions']:
        if row.get('name') in required:
            values = {key: row.get(key) for key in ('gcd_ms', 'cooldown_ms', 'cast_ms', 'channeled', 'costs', 'gains', 'gain_status', 'gain_timing', 'charges', 'max_charges')}
            if row['name'] in stats and stats[row['name']] != values:
                raise ValueError('同一按钮静态字段不一致: '+row['name'])
            stats[row['name']] = values
    for name in required:
        if name not in stats:
            raise ValueError('规则起点缺少动作静态字段: ' + name)
        row = stats[name]
        for key in ('gcd_ms', 'cooldown_ms', 'cast_ms'):
            _number(row[key], name+'.'+key)
        if row['channeled'] is not False or row['cast_ms'] != 0:
            raise ValueError('规则起点尚不支持施法或引导静态排位: ' + name)
        for key in ('costs', 'gains'):
            if not isinstance(row[key], dict) or set(row[key]) - set(resources):
                raise ValueError('缺少或不支持的静态多资源字段: '+name+'.'+key)
            for kind, amount in row[key].items():
                _number(amount, name+'.'+key+'.'+kind)
        row['gain_status'] = row['gain_status'] or 'unknown'
        row['gain_timing'] = row['gain_timing'] or 'unknown'
        if name in binding['generators'] and (row['gain_status'] != 'known' or
                row['gain_timing'] != 'on_cast' or row['gains'].get(resource, 0) <= 0):
            raise ValueError('资源填充动作缺少已知ON_CAST收益: '+name)
        if name in binding['cooldowns']:
            charges = _number(row['charges'], name+'.charges', positive=True)
            maximum = _number(row['max_charges'], name+'.max_charges', positive=True)
            if charges != int(charges) or maximum != int(maximum) or charges != maximum:
                raise ValueError('普通CD初始非满充能且缺少逐充能恢复状态: '+name)
        if row['gains'].get(constraint, 0):
            raise ValueError('静态离散资源返还尚无明确过程: '+name)
        if math.ceil(row['gcd_ms'] / input_interval_ms) == 2:
            raise ValueError('单空点击无法由现有WaitClicks表达: ' + name)
    if not binding['generators'] or stats[binding['spender']]['costs'].get(resource, 0) <= 0:
        raise ValueError('规则起点缺少资源生成或消费动作')
    period = (_number(binding['periodic_interval_ms'], binding['periodic_interval_source'], positive=True)
              if binding['periodic_action'] else 0)
    from program import canonicalize_search_program
    # Program owns the precombat prefix; it consumes ordinary inputs even when /nocombat skips it.
    prefix_clicks = len(canonicalize_search_program(
        [[binding['spender']]], capabilities)['form']['clicks']) - 1
    times = list(range(0, 180000, input_interval_ms))
    if burst:
        from burst import combined_inputs
        combined, sources = combined_inputs(times, burst, input_interval_ms)
        times = [at for at, source in zip(combined, sources) if source == 'loop']
    aligned_release = {}
    if burst:
        from burst import input_times as burst_input_times
        compiled = burst.get('candidate')
        if compiled:
            from sequence import compiled_program
            burst_clicks = compiled_program(compiled)
            blocks = compiled['blocks']
        else:
            blocks = burst.get('blocks', [])
            burst_clicks = [[command['simc_action'] for command in block] for block in blocks]
        burst_times = burst_input_times(burst, input_interval_ms)
        for ordinary_action, burst_action in binding['burst_alignment']:
            if ordinary_action not in required:
                continue
            if not any(command['simc_action'] == burst_action and not command.get('unavailable')
                       for block in blocks for command in block):
                continue
            first = next((index for index, commands in enumerate(burst_clicks)
                          if burst_action in commands), None)
            if first is not None and first < len(burst_times):
                index = bisect_left(times, burst_times[first])
                if index < len(times):
                    aligned_release[ordinary_action] = times[index]
    # Both passes use the existing input plan. Values below are estimates of successful actions,
    # never evidence that an attempted action actually consumed resources or satisfied its APL.
    def arrange(*, fill=False, work=None, replay=False):
        pending = [dict(row) for row in work] if work is not None else None
        balances = dict(initial)
        regeneration = []
        lanes = [0.0] * slots
        next_cd = {name: aligned_release.get(name, 0) for name in required}
        demonstrated = set()
        buff_demonstrated = set()
        consumption = 0.0
        unaccounted_gain = False
        program, positions = [], []
        click = prefix_clicks
        last_periodic = None  # ordinary-input click index; burst pauses only lengthen the gap
        generator_index = 0

        def wait(count):
            if not count:
                return
            if program and isinstance(program[-1], dict) and program[-1].get('kind') == 'WaitClicks':
                program[-1]['clicks'] += count
                positions[-1]['clicks'] += count
            elif count == 1:
                raise ValueError('单空点击无法由现有WaitClicks表达')
            else:
                program.append(dict(kind='WaitClicks', clicks=count))
                positions.append(dict(position=len(program)-1, kind='wait', clicks=count,
                                      basis='static_effective_gcd_or_resource_recovery', precision='approximate'))

        while len(program) <= 128 and click < min(len(times), 4096):
            now = times[click]
            ready = [end for end in regeneration if end <= now]
            if constraint is not None:
                balances[constraint] += len(ready)
            regeneration[:] = [end for end in regeneration if end > now]
            complete = (not pending if pending is not None else
                        set(binding['cooldowns']) <= demonstrated and consumption >= capacities[resource])
            if complete:
                return dict(program=program, positions=positions, duration_ms=now,
                            consumption=consumption, demonstrated=sorted(demonstrated), clicks=click)
            def eligible(name):
                return pending is None or any(row['action'] == name for row in pending)
            def affordable(name):
                return next_cd[name] <= now and all(balances[kind] >= amount
                         for kind, amount in stats[name]['costs'].items())
            name, reason = None, None
            periodic = binding['periodic_action'] if fill else None
            if periodic and (not replay or eligible(periodic)) and (last_periodic is None or (click - last_periodic) * input_interval_ms >= period) and affordable(periodic):
                name, reason = periodic, 'maintenance'
            spender = binding['spender']
            spending = binding['spending_decisions'](balances, capacities, uncertain=unaccounted_gain)
            selected_spend = None
            cooldown = next((candidate for candidate in binding['cooldowns']
                             if eligible(candidate) and affordable(candidate) and (fill or candidate not in demonstrated)), None)
            if name is None and binding['cooldowns_before_spender'] and cooldown:
                name = cooldown
                reason = ('window_or_full' if cooldown == binding['full_charge_action']
                          else 'ordinary_cooldown')
            if name is None and eligible(spender) and affordable(spender) and spending['high']['eligible']:
                selected_spend = spending['high']
                name, reason = spender, selected_spend['rule']
            if name is None:
                name, reason = cooldown, 'ordinary_cooldown'
            if name is None and eligible(spender) and affordable(spender) and spending['low']['eligible']:
                selected_spend = spending['low']
                name, reason = spender, selected_spend['rule']
            if name is None and fill and binding['buff_demo_needed']:
                name = next((candidate for candidate in binding['buff_actions']
                             if candidate not in buff_demonstrated and (not replay or eligible(candidate))
                             and affordable(candidate)), None)
                if name is not None:
                    reason = 'buff_maintenance_demo'
            if name is None:
                generators = binding['generators']
                ordered = generators[generator_index:] + generators[:generator_index]
                name = next((candidate for candidate in ordered if eligible(candidate) and affordable(candidate)), None)
                reason = 'resource_fill'
                if name is not None:
                    generator_index = (generators.index(name) + 1) % len(generators)
            if name is None:
                future = [*regeneration, *(time for time in next_cd.values() if time > now)]
                if not future:
                    raise ValueError('静态资源约束下无法生成规则骨架')
                after = bisect_left(times, min(future), lo=click+1)
                wait(after-click)
                click = after
                continue
            first_aligned_attempt = name in aligned_release and name not in demonstrated
            pending_entry = next((row for row in pending or [] if row['action'] == name), None)
            if pending_entry is not None:
                pending.remove(pending_entry)
            replaced_actions = list((pending_entry or {}).get('replaced_skeleton_actions', []))
            initial_full_charge = reason == 'window_or_full' and name not in demonstrated
            row = stats[name]
            # Reuse wall-clock input slots: burst pauses already supply elapsed GCD time.
            span = max(1, bisect_left(times, now + row['gcd_ms'], lo=click+1) - click)
            if click + span >= len(times):
                raise ValueError('规则起点超过现有点击或场景边界')
            if span == 2 and any(action not in demonstrated and release == times[click + span]
                                 for action, release in aligned_release.items()):
                # Keep the next aligned opportunity instead of emitting an unrepresentable
                # filler + one-empty pair. These are two deliberate pre-window empty inputs.
                if pending_entry is not None:
                    pending.insert(0, pending_entry)
                wait(span)
                click += span
                continue
            before = dict(balances)
            for kind, amount in row['costs'].items():
                balances[kind] -= amount
                if kind == resource:
                    consumption += amount
                elif kind == constraint:
                    if amount != int(amount):
                        raise ValueError('静态离散资源费用不是整数')
                    for _ in range(int(amount)):
                        lane = min(range(slots), key=lanes.__getitem__)
                        lanes[lane] = max(now, lanes[lane]) + recharge
                        regeneration.append(lanes[lane])
            if row['gain_status'] == 'known' and row['gain_timing'] == 'on_cast':
                for kind, amount in row['gains'].items():
                    balances[kind] = min(capacities[kind], balances[kind]+amount)
            elif row['gain_status'] != 'known_zero':
                unaccounted_gain = True
            if pending is not None and not replay and name == periodic and not unaccounted_gain:
                # A known same-resource ON_CAST contribution can replace resource-only work.
                # Conditional gains, extra resource costs, or slower actions are not equivalent.
                credit = balances[resource] - before[resource] + row['costs'].get(resource, 0)
                for entry in list(pending):
                    candidate = stats[entry['action']]
                    gain = candidate['gains'].get(resource, 0)
                    if (entry['action'] in binding['generators'] and gain > 0 and credit >= gain
                            and candidate['gain_status'] == 'known' and candidate['gain_timing'] == 'on_cast'
                            and set(candidate['gains']) == {resource} and set(row['gains']) == {resource}
                            and all(row['costs'].get(kind, 0) <= candidate['costs'].get(kind, 0)
                                    for kind in resources)
                            and row['gcd_ms'] <= candidate['gcd_ms']):
                        pending.remove(entry)
                        replaced_actions.append(entry['action'])
                        credit -= gain
            if reason == 'buff_maintenance_demo':
                buff_demonstrated.add(name)
            next_cd[name] = now + row['cooldown_ms']
            if name in binding['cooldowns']:
                demonstrated.add(name)
            if name == periodic:
                last_periodic = click
            program.append([name])
            positions.append(dict(position=len(program)-1, kind='action', action=name,
                estimated_ms=now, click_position=click, effective_gcd_ms=row['gcd_ms'], clicks=span,
                rule=reason, applied_rules=([reason] if reason in {item[0] for item in RULES}
                                           else ['maintenance'] if reason == 'buff_maintenance_demo' else []),
                precision='approximate', resources_before=before,
                gain_status=row['gain_status'], gain_timing=row['gain_timing'], static_gains=row['gains'],
                resource_balance_status=('unknown_unaccounted_gain' if unaccounted_gain
                                         else 'estimated_known_on_cast'),
                estimated_resources_after=dict(balances),
                replaced_skeleton_actions=replaced_actions,
                bindings=([binding['buff_demo_binding']] if reason == 'buff_maintenance_demo' else
                          [selected_spend['binding']] if selected_spend else
                          [r['id'] for r in binding['bindings'] if r['action'] == name]),
                condition_status=(selected_spend['condition_status'] if selected_spend else
                                  'static_branch_estimate' if initial_full_charge else 'dynamic_condition_unknown')))
            if selected_spend:
                positions[-1]['condition_basis'] = selected_spend['condition_basis']
            if reason == 'window_or_full':
                positions[-1]['condition_basis'] = (
                    '首次尝试采用静态快照的初始满充能证据' if initial_full_charge else
                    '仅按静态CD间距重复尝试；实际充能消耗/恢复及窗口未知，不证明满充能')
            if first_aligned_attempt:
                positions[-1]['applied_rules'].append('protected_burst')
                positions[-1]['condition_basis'] = '对齐固定爆发中的关联输入尝试；未证明该动作成功或Buff生效'
            wait(span-1)
            click += span
        raise ValueError('规则起点超过现有128节点/4096点击或场景边界')

    skeleton = arrange()
    final = arrange(fill=True, work=[row for row in skeleton['positions'] if row['kind'] == 'action'])
    periodic_edits = []
    while binding['periodic_action']:
        actions = [row for row in final['positions'] if row['kind'] == 'action']
        periodic_rows = [row for row in actions if row['action'] == binding['periodic_action']]
        if not periodic_rows:
            break
        first, last = periodic_rows[0], periodic_rows[-1]
        gap = final['clicks'] - last['click_position'] + first['click_position']
        if gap * input_interval_ms >= period:
            break
        if len(periodic_rows) > 1:
            restored = [dict(action=name, rule='resource_fill')
                        for name in last['replaced_skeleton_actions']]
            index = actions.index(last)
            actions[index:index+1] = restored
            periodic_edits.append(dict(action=last['action'], operation='remove_redundant_tail',
                                       restored_skeleton_actions=last['replaced_skeleton_actions']))
            # Reuse the same estimates/input clock. No capacity gate and no new insertions.
            final = arrange(fill=True, work=actions, replay=True)
            continue
        missing = math.ceil(period / input_interval_ms) - gap
        if final['clicks'] + missing >= min(len(times), 4096):
            raise ValueError('规则7间距超过现有点击或场景边界')
        if final['program'] and isinstance(final['program'][-1], dict):
            final['program'][-1]['clicks'] += missing
            final['positions'][-1]['clicks'] += missing
            final['positions'][-1]['basis'] = 'periodic_cross_cycle_spacing'
        elif missing == 1:
            raise ValueError('单空点击无法由现有WaitClicks表达')
        else:
            final['program'].append(dict(kind='WaitClicks', clicks=missing))
            final['positions'].append(dict(position=len(final['program'])-1, kind='wait', clicks=missing,
                                           basis='periodic_cross_cycle_spacing', precision='approximate'))
        final['positions'][-1]['applied_rules'] = ['maintenance']
        final['clicks'] += missing
        final['duration_ms'] = times[final['clicks']]
        periodic_edits.append(dict(action=last['action'], operation='extend_single_period', clicks=missing))
        break
    canonical = canonicalize_search_program(final['program'], capabilities)
    for row in final['positions']:
        row['source'] = canonical['program']['nodes'][prefix_clicks + row['position']]['source']
    return dict(version=VERSION, resource=resource, program=final['program'],
        precombat_clicks=prefix_clicks, recovery=recovery,
        behavior_identity=canonical['identity'], positions=final['positions'],
        skeleton={key: skeleton[key] for key in ('duration_ms', 'consumption', 'demonstrated')},
        duration_ms=final['duration_ms'], static_snapshot=snapshot,
        input_interval_ms=input_interval_ms, target_count=target_count,
        protected_burst=({key: burst[key] for key in ('definition_id', 'plan') if key in burst}
                         if burst else None),
        periodic_edits=periodic_edits,
        parameter_sources=binding['parameter_sources'], bindings=binding['bindings'],
        rules=[dict(id=rule, intent=intent, scope=scope, modifications=modifications,
                    application_status=('approximate_applied' if any(
                        rule in row.get('applied_rules', []) for row in final['positions']) else 'unknown_not_applied'),
                    applied_positions=[row['position'] for row in final['positions']
                                       if rule in row.get('applied_rules', [])],
                    condition='见完整专精绑定',
                    bindings=[row['id'] for row in binding['bindings'] if rule in row['rules']],
                    source='绑定中固定提交及行号；静态快照保留采集阶段',
                    priority='保留父列表及前序让位；第8项最后',
                    use='静态初始化近似；不声明学生诊断已完成',
                    expressiveness='固定尝试排列，不能执行动态APL条件')
               for rule, intent, scope, modifications in RULES],
        exact=['原生静态字段及采集时点', '普通/爆发输入暂停与位置语义', '现有GSE硬合法性'],
        approximate=['预计成功的保守排位账只累计已知ON_CAST收益；ON_HIT/未知收益未计入，不能据此证明真实余额、未溢出或资源条件成立',
                     '普通CD示范和绑定要求的增益维护尝试，不保证持续增益',
                     '固定爆发仅确定普通输入暂停及关联尝试，不推断动作成功或增益生效',
                     '短窗口动态状态未知：尚未据此独立调序；资源填充不冒称已执行短窗口规则',
                     '向上取整有效GCD点击跨度；每机会额外等待小于一个点击间隔',
                     *binding['approximate']],
        unknown=binding['unknown'])
