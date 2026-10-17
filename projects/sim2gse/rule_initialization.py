"""通用规则契约和有界静态排位过程；不执行APL、不模拟战斗。"""
from bisect import bisect_left
import math

VERSION = 'static-rule-start-v1'



def _number(value, label, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or positive and value == 0):
        raise ValueError('规则起点缺少有效静态字段: ' + label)
    return value


def generate(capabilities, reference, *, binding, input_interval_ms=300, target_count=1, burst=None, rule_snapshot=None):
    from rule_config import evaluate
    rules = tuple((key, row['intent'], row['scope'], row['modifications'])
                   for key, row in rule_snapshot['pack']['general']['templates'].items())
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
    required = {entry['action'] for entry in binding['entries']}
    if binding['periodic_action']:
        required.add(binding['periodic_action'])
    native_buttons = {entry['native_action']: entry['button']
                      for entry in binding['spec']['actions'].values() if entry['button'] in required}
    stats = {}
    for row in snapshot['actions']:
        name = native_buttons.get(row.get('name'))
        if name in required:
            values = {key: row.get(key) for key in ('gcd_ms', 'cooldown_ms', 'cast_ms', 'channeled', 'costs', 'gains', 'gain_status', 'gain_timing', 'charges', 'max_charges')}
            if name in stats and stats[name] != values:
                raise ValueError('同一按钮静态字段不一致: '+name)
            stats[name] = values
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
        if any(entry['action'] == name and entry.get('require_full_charges') for entry in binding['entries']):
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
        counts = {}
        for entry in binding['entries']:
            if ('fill' if fill else 'skeleton') in entry['phases']:
                counts.setdefault(entry['coverage_id'], entry['count'])
        attempted = {}
        last_attempt = {}
        consumption = 0.0
        unaccounted_gain = False
        credit = credited = 0.0
        funded_completed = preconsumption_attempts = edits_applied = 0
        funding = binding['funding']
        program, positions = [], []
        click = prefix_clicks
        last_periodic = None  # ordinary-input click index; burst pauses only lengthen the gap


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
            phase = 'fill' if fill else 'skeleton'
            values = dict(binding['facts'])
            for key, fact in binding['spec']['facts'].items():
                if fact['from'].startswith('estimate.resource.'):
                    resource_key = fact['resource']
                    values[key] = (balances[resource_key] if fact['from'].endswith('.current')
                                   else capacities[resource_key] - balances[resource_key])
            required_ids = {entry['coverage_id'] for entry in binding['entries']
                            if entry['required'] and phase in entry['phases']}
            values.update({'plan.qualified_credit': None if unaccounted_gain else credit,
                           'plan.target_cost': stats[binding['spender']]['costs'].get(resource, 0),
                           'plan.required_attempts_remaining': sum(counts[key] for key in required_ids),
                           'plan.pending_attempts_remaining': len(pending or []),
                           'plan.edits_applied': edits_applied})
            stop = binding['initialization']['edit_stop' if fill else 'stop']
            if evaluate(stop, values) is True:
                if fill and pending:
                    raise ValueError('二层停止条件早于剩余待办完成；不能交付截断序列')
                return dict(program=program, positions=positions, duration_ms=now,
                            consumption=consumption, demonstrated=sorted(demonstrated), clicks=click, edits_applied=edits_applied,
                            funding=dict(completed=funded_completed, credited=credited,
                                         preconsumption_attempts=preconsumption_attempts))
            def affordable(name):
                return next_cd[name] <= now and all(balances[kind] >= amount
                         for kind, amount in stats[name]['costs'].items())
            selected = None
            for entry in binding['entries']:
                name = entry['action']
                if phase not in entry['phases'] or counts.get(entry['coverage_id'], 0) <= 0:
                    continue
                if pending is not None and not any(row['action'] == name for row in pending):
                    if replay or not entry.get('insert'):
                        continue
                if (entry.get('interval_ms') and name in last_attempt and
                        (click - last_attempt[name]) * input_interval_ms < entry['interval_ms']):
                    continue
                values['plan.current_action_attempts'] = attempted.get(name, 0)
                applicable = evaluate(entry['when'], values)
                if applicable is None and entry['unknown'] == 'error':
                    raise ValueError('规则配置动作条件unknown: ' + entry['binding'])
                if applicable is not True and not (applicable is None and entry['unknown'] == 'attempt_with_report'):
                    continue
                if (not fill and funding['enabled'] and entry['coverage_id'] == funding['coverage_id']
                        and evaluate(funding['completion'], values) is not True):
                    continue
                if affordable(name):
                    selected = entry
                    break
            name = selected['action'] if selected else None
            reason = selected['reason'] if selected else None
            periodic = binding['periodic_action'] if fill else None
            if name is None:
                future = [*regeneration, *(next_cd[entry['action']] for entry in binding['entries']
                          if next_cd[entry['action']] > now and counts.get(entry['coverage_id'], 0) > 0
                          and phase in entry['phases'])]
                if not future:
                    raise ValueError('静态资源约束下无法完成规则骨架：无法证明来源额度或剩余动作不可达')
                after = bisect_left(times, min(future), lo=click+1)
                wait(after-click)
                click = after
                continue
            first_aligned_attempt = name in aligned_release and name not in demonstrated
            pending_entry = next((row for row in pending or [] if row['action'] == name), None)
            if pending is not None and not replay:
                edits_applied += int(pending_entry is None or pending[0] is not pending_entry)
                if edits_applied > binding['initialization']['edit_limit']:
                    raise ValueError('二层编辑达到配置上限，不能继续修改')
            if pending_entry is not None:
                pending.remove(pending_entry)
            replaced_actions = list((pending_entry or {}).get('replaced_skeleton_actions', []))
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
            qualifies = (not fill and funding['enabled'] and
                         selected['coverage_id'] == funding['coverage_id'] and
                         evaluate(funding['completion'], values) is True)
            for kind, amount in row['costs'].items():
                balances[kind] -= amount
                if kind == resource:
                    consumption += amount
                    credit = max(0, credit - amount)
                elif kind == constraint:
                    if amount != int(amount):
                        raise ValueError('静态离散资源费用不是整数')
                    for _ in range(int(amount)):
                        lane = min(range(slots), key=lanes.__getitem__)
                        lanes[lane] = max(now, lanes[lane]) + recharge
                        regeneration.append(lanes[lane])
            if row['gain_status'] == 'known' and row['gain_timing'] == 'on_cast':
                for kind, amount in row['gains'].items():
                    effective_gain = min(capacities[kind]-balances[kind], amount)
                    balances[kind] += effective_gain
                    if not fill and funding['enabled'] and kind == resource and name in binding['generators']:
                        if unaccounted_gain:
                            raise ValueError('资源来源unknown：此前未知/ON_HIT收益，不能证明容量余量及来源完成')
                        credit += effective_gain
                        credited += effective_gain
            elif row['gain_status'] != 'known_zero':
                unaccounted_gain = True
            if (pending is not None and not replay and selected.get('replace_actions')
                    and row['gain_status'] == 'known' and row['gain_timing'] == 'on_cast'):
                # Credit belongs only to this known contribution in the conservative ledger;
                # earlier unaccounted gains keep the balance unknown, not this contribution.
                # Conditional gains, extra resource costs, or slower actions are not equivalent.
                credit = balances[resource] - before[resource] + row['costs'].get(resource, 0)
                for entry in list(pending):
                    candidate = stats[entry['action']]
                    gain = candidate['gains'].get(resource, 0)
                    if (entry['action'] in selected['replace_actions'] and gain > 0 and credit >= gain
                            and candidate['gain_status'] == 'known' and candidate['gain_timing'] == 'on_cast'
                            and set(candidate['gains']) == {resource} and set(row['gains']) == {resource}
                            and all(row['costs'].get(kind, 0) <= candidate['costs'].get(kind, 0)
                                    for kind in resources)
                            and row['gcd_ms'] <= candidate['gcd_ms']):
                        edits_applied += 1
                        if edits_applied > binding['initialization']['edit_limit']:
                            raise ValueError('二层编辑达到配置上限，不能继续修改')
                        pending.remove(entry)
                        replaced_actions.append(entry['action'])
                        credit -= gain
            counts[selected['coverage_id']] -= 1
            funded_completed += int(qualifies)
            if selected['coverage_id'] == funding['preconsumption_coverage']:
                preconsumption_attempts += 1
            attempted[name] = attempted.get(name, 0) + 1
            last_attempt[name] = click
            next_cd[name] = now + row['cooldown_ms']
            if selected.get('report_demonstrated'):
                demonstrated.add(name)
            program.append([name])
            positions.append(dict(position=len(program)-1, kind='action', action=name,
                estimated_ms=now, click_position=click, effective_gcd_ms=row['gcd_ms'], clicks=span,
                rule=reason, applied_rules=list(selected['rules']), coverage_id=selected['coverage_id'],
                precision='approximate', resources_before=before,
                gain_status=row['gain_status'], gain_timing=row['gain_timing'], static_gains=row['gains'],
                resource_balance_status=('unknown_unaccounted_gain' if unaccounted_gain
                                         else 'estimated_known_on_cast'),
                estimated_resources_after=dict(balances),
                replaced_skeleton_actions=replaced_actions, bindings=[selected['binding']],
                condition_status=('dynamic_condition_unknown' if unaccounted_gain and selected.get('status_uses_resource_balance') else
                                  evaluate(selected.get('condition_status', 'dynamic_condition_unknown'), values)),
                condition_basis=selected['basis']))
            if first_aligned_attempt:
                positions[-1]['applied_rules'].extend(selected.get('alignment_rules', []))
                positions[-1]['condition_basis'] = '对齐固定爆发中的关联输入尝试；未证明该动作成功或Buff生效'
            wait(span-1)
            click += span
        raise ValueError('规则起点超过现有128节点/4096点击或场景边界')

    skeleton = arrange()
    limit = binding['initialization']['edit_limit']
    disabled = not limit or evaluate(binding['initialization']['edit_stop'], {
        'plan.edits_applied': 0, 'plan.pending_attempts_remaining':
        sum(row['kind'] == 'action' for row in skeleton['positions'])}) is True
    final = skeleton if disabled else arrange(fill=True, work=[row for row in skeleton['positions'] if row['kind'] == 'action'])
    periodic_edits = []
    cross_cycle = next((entry.get('cross_cycle') for entry in binding['entries']
                        if entry['action'] == binding['periodic_action']), None)
    while not disabled and cross_cycle == 'remove_redundant_tail_or_pad':
        actions = [row for row in final['positions'] if row['kind'] == 'action']
        periodic_rows = [row for row in actions if row['action'] == binding['periodic_action']]
        if not periodic_rows:
            break
        first, last = periodic_rows[0], periodic_rows[-1]
        gap = final['clicks'] - last['click_position'] + first['click_position']
        if gap * input_interval_ms >= period:
            break
        if final['edits_applied'] + len(periodic_edits) >= limit:
            raise ValueError('跨循环编辑达到配置上限')
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
            raise ValueError('配置间距超过现有点击或场景边界')
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
        final['positions'][-1]['applied_rules'] = next(
            entry['rules'] for entry in binding['entries'] if entry['action'] == binding['periodic_action'])
        final['clicks'] += missing
        final['duration_ms'] = times[final['clicks']]
        periodic_edits.append(dict(action=last['action'], operation='extend_single_period', clicks=missing))
        break
    canonical = canonicalize_search_program(final['program'], capabilities)
    for row in final['positions']:
        row['source'] = canonical['program']['nodes'][prefix_clicks + row['position']]['source']
    return dict(version=VERSION, rule_snapshot=rule_snapshot,
        rule_config_digest=rule_snapshot['rule_config_digest'] if rule_snapshot else None,
        resource=resource, program=final['program'],
        precombat_clicks=prefix_clicks, recovery=recovery,
        behavior_identity=canonical['identity'], positions=final['positions'],
        skeleton=dict({key: skeleton[key] for key in ('duration_ms', 'consumption', 'demonstrated', 'funding')},
                      attempts=[dict(action=row['action'], rule=row['rule'], estimated_ms=row['estimated_ms'])
                                for row in skeleton['positions'] if row['kind'] == 'action']),
        duration_ms=final['duration_ms'], static_snapshot=snapshot,
        input_interval_ms=input_interval_ms, target_count=target_count,
        protected_burst=({key: burst[key] for key in ('definition_id', 'plan') if key in burst}
                         if burst else None),
        periodic_edits=periodic_edits,
        parameter_sources=binding['parameter_sources'], bindings=binding['bindings'],
        action_mapping=binding['native_buttons'],
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
               for rule, intent, scope, modifications in rules],
        exact=['原生静态字段及采集时点', '普通/爆发输入暂停与位置语义', '现有GSE硬合法性'],
        approximate=['预计成功的保守排位账只累计已知ON_CAST收益；ON_HIT/未知收益未计入，不能据此证明真实余额、未溢出或资源条件成立',
                     '普通CD示范和绑定要求的增益维护尝试，不保证持续增益',
                     '固定爆发仅确定普通输入暂停及关联尝试，不推断动作成功或增益生效',
                     '短窗口动态状态未知：尚未据此独立调序；资源填充不冒称已执行短窗口规则',
                     '向上取整有效GCD点击跨度；每机会额外等待小于一个点击间隔',
                     *binding['approximate']],
        unknown=binding['unknown'])
