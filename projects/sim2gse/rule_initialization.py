"""按可编辑有序起手生成循环候选；静态估计不是成功施放证据。"""
import copy
from bisect import bisect_left
import math

VERSION = 'ordered-guide-start-v2'


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('规则起点缺少有效静态字段: ' + label)
    return value


def context(capabilities, reference, *, target_count=1, scene=None, rule_snapshot=None):
    """共享范围与诊断绑定不依赖是否生成规则起点。"""
    from rule_config import load, bind
    rule_snapshot = rule_snapshot or load()
    binding = bind(capabilities, reference.get('static_snapshot'), target_count,
        spec_id=reference.get('identity', {}).get('spec_id'), rule_snapshot=rule_snapshot, scene=scene)
    return dict(rule_config_digest=rule_snapshot['rule_config_digest'],
        configuration_key=binding['configuration_key'], bindings=binding['bindings'],
        static_snapshot=reference.get('static_snapshot')), binding


def generate(capabilities, reference, *, binding, input_interval_ms=300, target_count=1,
             burst=None, rule_snapshot=None):
    from program import canonicalize_search_program
    snapshot = reference.get('static_snapshot')
    if (not isinstance(snapshot, dict) or type(snapshot.get('protocol')) is not int
            or snapshot['protocol'] not in (1, 2)
            or snapshot.get('stage') != 'precombat_initialized_before_actions'):
        raise ValueError('规则起点缺少真实角色静态快照，请重新构建引擎')
    if not isinstance(snapshot.get('resources'), dict) or not isinstance(snapshot.get('actions'), list):
        raise ValueError('规则起点缺少静态字段: resources/actions')
    opener = binding['opener']
    actions = binding['spec']['actions']
    stats = {}
    for row in snapshot['actions']:
        values = {key: row.get(key) for key in ('gcd_ms', 'cast_ms', 'channel_ms', 'channeled', 'costs',
                   'gains', 'gain_status', 'gain_timing')}
        values['unknown'] = row.get('unknown', {})
        if row.get('name') in stats and stats[row['name']] != values:
            raise ValueError('同一动作静态字段不一致: ' + row['name'])
        stats[row.get('name')] = values
    program, positions, source_steps = [], [], []
    unknown = list(binding['unknown'])
    balances = {key: _number(row.get('current'), key+'.current')
                for key, row in snapshot['resources'].items()}
    capacities = {key: _number(row.get('maximum'), key+'.maximum')
                  for key, row in snapshot['resources'].items()}
    if any(value > capacities[key] for key, value in balances.items()):
        raise ValueError('原生当前资源超过上限，不能生成起手')

    def action_stats(name):
        row = stats.get(name)
        if row is None:
            raise ValueError('规则起点缺少动作静态字段: ' + name)
        _number(row.get('gcd_ms'), name+'.gcd_ms')
        cast_ms = _number(row.get('cast_ms'), name+'.cast_ms')
        if type(row.get('channeled')) is not bool:
            raise ValueError('规则起点缺少有效静态字段: ' + name + '.channeled')
        channel_ms = row.get('channel_ms')
        if (channel_ms is None and snapshot['protocol'] == 1 and not row['channeled']
                and cast_ms == 0 and 'channel_ms' not in row['unknown']):
            channel_ms = 0  # 旧协议只支持明确的非引导瞬发动作。
        row['channel_ms'] = _number(channel_ms, name+'.channel_ms')
        if not row['channeled'] and row['channel_ms'] != 0:
            raise ValueError('非引导动作时长矛盾: ' + name + '.channel_ms')
        row['occupancy_ms'] = max(row['gcd_ms'], cast_ms + row['channel_ms'])
        for key in ('costs', 'gains'):
            if row.get(key) is None and key in row['unknown']:
                note = name + '.' + key + ': ' + str(row['unknown'][key])
                if note not in unknown:
                    unknown.append(note)
                continue
            if not isinstance(row.get(key), dict) or set(row[key]) - set(balances):
                raise ValueError('缺少或不支持的静态多资源字段: '+name+'.'+key)
            for resource, amount in row[key].items():
                _number(amount, name+'.'+key+'.'+resource)
        return row

    def consume(row):
        if row['costs'] is None:
            balances.update({key: None for key in balances})
        for resource, amount in (row['costs'] or {}).items():
            balance = balances[resource]
            balances[resource] = balance - amount if balance is not None and balance >= amount else None
        if row.get('gain_status') == 'known' and row.get('gain_timing') == 'on_cast':
            for resource, amount in row['gains'].items():
                if balances[resource] is not None:
                    balances[resource] = min(capacities[resource], balances[resource]+amount)
        elif row.get('gain_status') != 'known_zero':
            for resource in row['gains'] or balances:
                balances[resource] = None

    prefix = len(capabilities.get('precombat_actions', []))
    parameters = snapshot.get('parameters', {})
    precombat_gcd = parameters.get('precombat_gcd_ms') if prefix else 0
    if precombat_gcd is not None:
        _number(precombat_gcd, 'precombat_gcd_ms')
    precombat_ms = 0
    if prefix:
        # 新字段来自已有战前实际输出；旧协议仅认证过瞬发战前动作。
        if 'precombat_occupancy_ms' in snapshot.get('parameter_unknown', {}):
            precombat_ms = None
        else:
            precombat_ms = parameters.get('precombat_occupancy_ms',
                precombat_gcd if snapshot['protocol'] == 1 else None)
        if precombat_ms is None:
            raise ValueError('战前有效GCD或实际占用未知：无法估计起手及首次爆发')
        _number(precombat_ms, 'precombat_occupancy_ms')
    click = max(prefix, math.ceil(precombat_ms / input_interval_ms))
    elapsed = click * input_interval_ms
    precombat_occupancy = dict(gcd_ms=precombat_gcd, occupancy_ms=precombat_ms,
                              first_loop_ms=elapsed, precision='native_static_estimate')
    padding = click - prefix
    if padding == 1:
        raise ValueError('单空点击无法由现有WaitClicks表达: 战前占用')
    if padding:
        program.append(dict(kind='WaitClicks', clicks=padding))
        positions.append(dict(kind='wait', position=0, clicks=padding,
                              basis='native_precombat_occupancy', precision='approximate'))
    first_burst_ms = None
    if burst and 'first_burst_step' in opener:
        estimate = elapsed
        for step in opener['steps']:
            if step['source_step'] == opener['first_burst_step']:
                first_burst_ms = estimate
                break
            if step.get('mapping', 'loop') != 'loop':
                raise ValueError('首次爆发前的独立映射不可静默略过')
            action = actions[step['action']]
            name = step.get('native_form', action['native_action'])
            row = action_stats(name)
            estimate += max(1, math.ceil(row['occupancy_ms'] /
                                         input_interval_ms)) * input_interval_ms
        if first_burst_ms is None or not 0 < first_burst_ms < 180000:
            raise ValueError('首次爆发时点超出已有输入计划范围')
    times = list(range(0, 180000, input_interval_ms))
    burst_locations = {}
    if burst:
        from burst import combined_inputs, input_times
        from sequence import compiled_program
        burst_times = input_times(burst, input_interval_ms)
        for block_index, block in enumerate(compiled_program(burst['candidate'])):
            for command_index, name in enumerate(block):
                burst_locations.setdefault(name, dict(native_action=name, block=block_index,
                    command=command_index, input_ms=burst_times[block_index]))
        combined, sources = combined_inputs(times, burst, input_interval_ms)
        times = [at for at, source in zip(combined, sources) if source == 'loop']
    elapsed = times[click]
    for step in opener['steps']:
        action = actions[step['action']]
        name = step.get('native_form', action['native_action'])
        mapped = dict(copy.deepcopy(step), button=action['button'], native_action=name,
                      estimated_ms=elapsed, source=opener['source'])
        source_steps.append(mapped)
        if step['source_step'] == opener.get('first_burst_step') and first_burst_ms is None:
            first_burst_ms = elapsed
        if step.get('mapping', 'loop') == 'burst':
            mapped['mapping_status'] = 'independent_burst' if burst else 'independent_burst_disabled'
            if burst:
                names = [actions[row['action']]['native_action'] for row in
                         step.get('commands', [dict(action=step['action'])])]
                missing = [name for name in names if name not in burst_locations]
                if missing:
                    raise ValueError('独立爆发宏未包含来源动作: ' + ','.join(missing))
                mapped['burst_mapping'] = [dict(burst_locations[name]) for name in names]
                mapped['estimated_ms'] = min(row['input_ms'] for row in mapped['burst_mapping'])
                mapped['mapping_loss'] = '映射到现有独立宏的实际块/命令及输入时刻；源顺序不改变宏内顺序，尝试不代表成功'
            continue
        row = action_stats(name)
        gcd = row['gcd_ms']
        span = max(1, bisect_left(times, elapsed + row['occupancy_ms'], lo=click+1) - click)
        if span == 2:
            raise ValueError('单空点击无法由现有WaitClicks表达: ' + name)
        before = dict(balances)
        consume(row)
        mapped.update(mapping_status='loop_attempt', position=len(program), click_position=click)
        program.append([action['button']])
        positions.append(dict(kind='action', position=len(program)-1, action=action['button'],
            native_action=name, source_step=step['source_step'], source=opener['source'],
            estimated_ms=elapsed, click_position=click,
            effective_gcd_ms=gcd,
            estimated_gcd_ms=gcd, gcd_basis='native_static_snapshot', clicks=span,
            cast_ms=row['cast_ms'], channel_ms=row['channel_ms'], occupancy_ms=row['occupancy_ms'],
            precision='approximate', costs=copy.deepcopy(row['costs']), resources_before=before,
            estimated_resources_after=dict(balances),
            parameter_stage=snapshot['stage'], condition_status='dynamic_condition_unknown',
            condition_basis='按源顺序尝试；战前费用和收益不能证明战中替换形态或成功',
            applied_rules=[], bindings=[]))
        if span > 1:
            program.append(dict(kind='WaitClicks', clicks=span-1))
            positions.append(dict(kind='wait', position=len(program)-1, clicks=span-1,
                basis='static_action_occupancy', precision='approximate'))
        click += span
        if click >= len(times):
            raise ValueError('规则起点超过现有点击或场景边界')
        elapsed = times[click]
        if len(program) > 128 or click > 4096 or elapsed >= 180000:
            raise ValueError('规则起点超过现有128节点/4096点击或场景边界')
    if not program:
        raise ValueError('起手没有可表达的普通循环动作')
    canonical = canonicalize_search_program(program, capabilities)
    for row in positions:
        row['guide_source'] = opener['source']
        row['source'] = canonical['program']['nodes'][prefix + row['position']]['source']
        if row['kind'] == 'action':
            row['commands'] = canonical['form']['clicks'][row['click_position']]
    initialization = dict(version=VERSION, rule_snapshot=rule_snapshot,
        rule_config_digest=rule_snapshot['rule_config_digest'],
        configuration_key=binding['configuration_key'], states=binding['states'],
        source_opener=binding['configuration']['opener'],
        resource=reference.get('identity', {}).get('resource'),
        program=program, positions=positions, source_steps=source_steps,
        opener_id=opener['id'], precombat_clicks=prefix, precombat_occupancy=precombat_occupancy, duration_ms=elapsed,
        first_burst_ms=first_burst_ms,
        behavior_identity=canonical['identity'], static_snapshot=snapshot,
        input_interval_ms=input_interval_ms, target_count=target_count,
        protected_burst=({key: burst[key] for key in ('definition_id', 'plan') if key in burst} if burst else None),
        parameter_sources=binding['parameter_sources'], bindings=binding['bindings'],
        action_mapping=binding['native_buttons'],
        rules=[dict(id=key, application_status='declared_not_diagnosed', applied_positions=[])
               for key in rule_snapshot['pack']['general']['templates']],
        exact=['源顺序、重复次数、按钮映射和现有GSE硬合法性'],
        approximate=['动作占用按输入间隔向上取整；静态资源账不足或动态收益时保留未知',
                     '起手映射为可搜索循环，不能保证一次性或指南动态条件', *binding['approximate']],
        unknown=unknown)
    from rule_diagnostics import observation_request
    initialization['rule_observation_request'] = observation_request(initialization, protocol=2)
    return initialization
