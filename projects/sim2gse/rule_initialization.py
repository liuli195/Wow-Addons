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
    ('maintenance', '持续效果按条件补齐', '完整疾病条件及有来源间隔', '低频或间隔安排'),
    ('avoid_idle', '减少可避免GCD空闲', '前七项及具体可用动作证据', '仅减少已证多余等待'),
)


def _number(value, label, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or positive and value == 0):
        raise ValueError('规则起点缺少有效静态字段: ' + label)
    return value


def generate(capabilities, reference, *, input_interval_ms=300, target_count=1, burst=None):
    snapshot = reference.get('static_snapshot')
    if (not isinstance(snapshot, dict) or snapshot.get('protocol') != 1
            or snapshot.get('stage') != 'precombat_initialized_before_actions'):
        raise ValueError('规则起点缺少真实角色静态快照，请重新构建引擎')
    if reference.get('identity', {}).get('spec_id') != 252:
        raise ValueError('当前专精尚无已审核的规则起点绑定')
    from unholy_rules import bind
    for key in ('resources', 'parameters', 'actions'):
        if key not in snapshot:
            raise ValueError('规则起点缺少静态字段: ' + key)
    params = snapshot['parameters']
    for key in ('cycle_of_death', 'festering_scythe'):
        if type(params.get(key)) is not bool:
            raise ValueError('规则起点缺少静态天赋字段: ' + key)
    binding = bind(capabilities, snapshot, target_count)
    resource, constraint = binding['resource'], binding['constrained_resource']
    initial = {}
    capacities = {}
    for name in (resource, constraint):
        row = snapshot['resources'].get(name, {})
        initial[name] = _number(row.get('current'), name+'.current')
        capacities[name] = _number(row.get('maximum'), name+'.maximum', positive=True)
        if initial[name] > capacities[name]:
            raise ValueError('静态资源初值超过容量: ' + name)
    recharge = _number(params.get('rune_recharge_ms'), 'rune_recharge_ms', positive=True)
    slots = _number(params.get('rune_recharge_slots'), 'rune_recharge_slots', positive=True)
    if slots != int(slots) or not 1 <= slots <= capacities[constraint]:
        raise ValueError('缺少静态离散资源恢复槽位')
    slots = int(slots)
    if initial[constraint] != capacities[constraint]:
        raise ValueError('静态符文初值非满且缺少逐符文恢复状态')
    required = set(binding['generators'] + binding['cooldowns'] + [binding['spender']])
    if binding['periodic_action']:
        required.add(binding['periodic_action'])
    stats = {}
    for row in snapshot['actions']:
        if row.get('name') in required:
            values = {key: row.get(key) for key in ('gcd_ms', 'cooldown_ms', 'cast_ms', 'channeled', 'costs', 'gains', 'charges', 'max_charges')}
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
            if not isinstance(row[key], dict) or set(row[key]) - {resource, constraint}:
                raise ValueError('缺少或不支持的静态多资源字段: '+name+'.'+key)
            for kind, amount in row[key].items():
                _number(amount, name+'.'+key+'.'+kind)
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
    period = (_number(params.get(binding['interval_parameter']), binding['interval_parameter'], positive=True)
              if binding['periodic_action'] else 0)
    times = list(range(0, 180000, input_interval_ms))
    if burst:
        from burst import combined_inputs
        combined, sources = combined_inputs(times, burst, input_interval_ms)
        times = [at for at, source in zip(combined, sources) if source == 'loop']
    # Both passes use the existing input plan. Values below are estimates of successful actions,
    # never evidence that an attempted action actually consumed resources or satisfied its APL.
    def arrange(*, fill=False, minimum_ms=0):
        balances = dict(initial)
        regeneration = []
        lanes = [0.0] * slots
        next_cd = {name: 0 for name in required}
        demonstrated = set()
        consumption = 0.0
        program, positions = [], []
        click = 0
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
            balances[constraint] += len(ready)
            regeneration[:] = [end for end in regeneration if end > now]
            complete = (set(binding['cooldowns']) <= demonstrated
                        and consumption >= capacities[resource])
            if complete and (not fill or now >= minimum_ms and
                             (last_periodic is None or (click - last_periodic) * input_interval_ms >= period)):
                return dict(program=program, positions=positions, duration_ms=now,
                            consumption=consumption, demonstrated=sorted(demonstrated))
            def affordable(name):
                return next_cd[name] <= now and all(balances[kind] >= amount
                         for kind, amount in stats[name]['costs'].items())
            name, reason = None, None
            periodic = binding['periodic_action'] if fill else None
            if periodic and (last_periodic is None or (click - last_periodic) * input_interval_ms >= period) and affordable(periodic):
                name, reason = periodic, 'maintenance'
            spender = binding['spender']
            deficit = capacities[resource] - balances[resource]
            high_spend = (deficit <= binding['near_cap_deficit'] if binding['near_cap_inclusive']
                          else deficit < binding['near_cap_deficit'])
            high_spend |= (binding['near_cap_runes'] is not None and
                           balances[constraint] < binding['near_cap_runes'])
            low_spend = (binding['reserve_deficit'] is None or deficit < binding['reserve_deficit'])
            cooldown = next((candidate for candidate in binding['cooldowns']
                             if affordable(candidate) and (fill or candidate not in demonstrated)), None)
            if name is None and binding['cooldowns_before_spender'] and cooldown:
                name = cooldown
                reason = ('window_or_full' if cooldown == binding['full_charge_action']
                          else 'ordinary_cooldown')
            if name is None and affordable(spender) and high_spend:
                name, reason = spender, 'near_cap'
            if name is None:
                name, reason = cooldown, 'ordinary_cooldown'
            if name is None and affordable(spender) and low_spend:
                name, reason = spender, ('reserve' if binding['reserve_deficit'] is not None
                                         else 'low_priority_spend')
            if name is None:
                generators = binding['generators']
                ordered = generators[generator_index:] + generators[:generator_index]
                name = next((candidate for candidate in ordered if affordable(candidate)), None)
                reason = ('short_window' if fill and name == binding['short_window_action']
                          else 'resource_fill')
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
            initial_full_charge = reason == 'window_or_full' and name not in demonstrated
            row = stats[name]
            span = max(1, math.ceil(row['gcd_ms'] / input_interval_ms))
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
            for kind, amount in row['gains'].items():
                balances[kind] = min(capacities[kind], balances[kind]+amount)
            next_cd[name] = now + row['cooldown_ms']
            if name in binding['cooldowns']:
                demonstrated.add(name)
            if name == periodic:
                last_periodic = click
            program.append([name])
            positions.append(dict(position=len(program)-1, kind='action', action=name,
                estimated_ms=now, effective_gcd_ms=row['gcd_ms'], clicks=span,
                rule=reason, precision='approximate', resources_before=before,
                estimated_resources_after=dict(balances),
                bindings=([binding['high_spender_binding'] if reason == 'near_cap' else
                           binding['low_spender_binding']] if name == spender else
                          [r['id'] for r in binding['bindings'] if r['action'] == name]),
                condition_status=('static_branch_estimate' if
                                  (name == spender and reason != 'low_priority_spend') or initial_full_charge
                                  else 'dynamic_condition_unknown')))
            if reason == 'window_or_full':
                positions[-1]['condition_basis'] = (
                    '首次尝试采用静态快照的初始满充能证据' if initial_full_charge else
                    '仅按静态CD间距重复尝试；实际充能消耗/恢复及窗口未知，不证明满充能')
            wait(span-1)
            click += span
        raise ValueError('规则起点超过现有128节点/4096点击或场景边界')

    skeleton = arrange()
    final = arrange(fill=True, minimum_ms=skeleton['duration_ms'])
    from program import canonicalize_search_program
    canonical = canonicalize_search_program(final['program'], capabilities)
    return dict(version=VERSION, resource=resource, program=final['program'],
        behavior_identity=canonical['identity'], positions=final['positions'],
        skeleton={key: skeleton[key] for key in ('duration_ms', 'consumption', 'demonstrated')},
        duration_ms=final['duration_ms'], static_snapshot=snapshot,
        input_interval_ms=input_interval_ms, target_count=target_count,
        protected_burst=({key: burst[key] for key in ('definition_id', 'plan') if key in burst}
                         if burst else None),
        parameter_sources=binding['parameter_sources'], bindings=binding['bindings'],
        rules=[dict(id=rule, intent=intent, scope=scope, modifications=modifications,
                    condition='见完整专精绑定',
                    bindings=[row['id'] for row in binding['bindings'] if rule in row['rules']],
                    source='绑定中固定提交及行号；静态快照保留采集阶段',
                    priority='保留父列表及前序让位；第8项最后',
                    use='静态初始化近似；不声明学生诊断已完成',
                    expressiveness='固定尝试排列，不能执行动态APL条件')
               for rule, intent, scope, modifications in RULES],
        exact=['原生静态字段及采集时点', '普通/爆发输入暂停与位置语义', '现有GSE硬合法性'],
        approximate=['预计成功资源账、普通CD示范和填充顺序',
                     '固定爆发仅确定普通输入暂停；不推断爆发成功、Army冷却或Buff生效',
                     '短窗口动作分散尝试；未观察随机Buff窗口，不保证及时命中',
                     '以原生持续时间作为低频间隔；不保证全场疾病状态',
                     '向上取整有效GCD点击跨度；每机会额外等待小于一个点击间隔'],
        unknown=binding['unknown'])
