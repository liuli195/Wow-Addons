"""解释已校验模板；证据只来自当前候选的同一计分批次。"""
import copy
import json
import math
import time
from runtime import diagnostic_start, diagnostic_finish

UNKNOWN = object()
VERSION = 'same-batch-template-v1'


def observation_request(initialization, *, protocol=1):
    """任务冻结后一次解析所需对象，评分热路径只携带这份有限请求。"""
    frozen = initialization.get('rule_observation_request')
    if 'rule_observation_request' in initialization:
        _validate_observation_request(frozen)
        return copy.deepcopy(frozen)
    snapshot = initialization['rule_snapshot']
    configuration = next(row for row in snapshot['resolved'] if row['key'] == initialization['configuration_key'])
    objects, required = configuration['objects'], set()
    for state in configuration['states'].values():
        if state['effect'] is not None: required.add(state['effect'])
        for binding in state['priority']:
            for read in snapshot['pack']['general']['templates'][binding['template']]['reads']:
                if isinstance(read['object'], dict) and 'arg' in read['object']:
                    ref = binding['arguments'][read['object']['arg']]
                    required.update(item for item in (ref if isinstance(ref, list) else [ref])
                                    if isinstance(item, str) and item in objects)
    pending = list(required)
    while pending:
        declaration = objects[pending.pop()]
        references = [declaration[field] for field in ('from_action', 'qualification') if field in declaration]
        references += [row['target_scope'] for row in declaration.get('components', [])]
        for ref in references:
            if ref not in required:
                required.add(ref)
                pending.append(ref)
    # 即使无规则对象，旧搜索反馈仍复用首计分输入/控制事件，不另跑index99。
    request = dict(protocol=1, objects={name: copy.deepcopy(objects[name]) for name in sorted(required)})
    if protocol == 1:
        return request
    if protocol != 2:
        raise ValueError('未支持的规则观察请求协议')
    collections = {name: {} for name in _OBSERVATION_FIELDS}

    def include(collection, names, fields):
        for name in names:
            collections[collection].setdefault(name, set()).update(fields)

    try:
        for state in configuration['states'].values():
            if state['effect'] is not None:
                include('effect_observations', [state['effect']], ['active'])
            for binding in state['priority']:
                for read in snapshot['pack']['general']['templates'][binding['template']]['reads']:
                    source = read['from']
                    if source not in _OBSERVATION_SOURCES:
                        raise Unsupported('尚未识别的采集依赖')
                    reference = read['object']
                    if reference is not None and (not isinstance(reference, dict) or set(reference) != {'arg'}):
                        raise Unsupported('尚未识别的采集对象表达式')
                    collection = _OBSERVATION_SOURCES[source]
                    if collection is None:
                        continue  # 输入、候选结构等保留原路径的完整事实。
                    if not set(read['fields']) <= _OBSERVATION_FIELDS[collection]:
                        raise Unsupported('尚未识别的采集字段')
                    if reference is None:
                        raise Unsupported('尚未识别的采集对象表达式')
                    names = binding['arguments'][reference['arg']]
                    names = names if isinstance(names, list) else [names]
                    if any(name is not None and name not in request['objects'] for name in names):
                        raise Unsupported('采集对象未解析')
                    include(collection, [name for name in names if name is not None], read['fields'])
    except (Unsupported, KeyError, TypeError):
        # 新声明不能用已知字段契约解释时，保守采集该配置全部原始对象。
        # 旧任务没有冻结请求时仍返回上面的旧 v1 闭包，不能重解释旧身份。
        return dict(protocol=1, objects=copy.deepcopy(objects))
    for name, declaration in request['objects'].items():
        if declaration['kind'] == 'action':
            include('action_observations', [name], _ACTION_AUDIT_FIELDS)
            include('action_events', [name], _ACTION_EVENT_FIELDS)
        elif declaration['kind'] in ('state', 'resource'):
            include('state_observations', [name], ['value'])
    for collection, aliases in collections.items():
        for fields in aliases.values():
            fields.update(_OBSERVATION_ID_FIELDS)
            if collection in ('effect_events', 'effect_observations'):
                fields.update(_EFFECT_AUDIT_FIELDS)
            if collection == 'effect_events':
                fields.update({'kind', 'start', 'end', 'end_reason', 'source_input_index', 'source_actual_action'})
    request.update(protocol=2, collections={name: {alias: sorted(fields) for alias, fields in aliases.items()}
                                            for name, aliases in collections.items()})
    return request


# 有限的现有原生/派生字段契约。新来源或未识别字段回退完整 v1，不猜语义。
_OBSERVATION_ID_FIELDS = {'object', 'sample_id', 'input_index', 'event_index', 'time',
                          'source_step', 'input_source'}
_ACTION_AUDIT_FIELDS = {'actual_form', 'base_button', 'attempt', 'success', 'failure_reason',
                        'native_qualified', 'input_allowed', 'known_native_requirements',
                        'native_requirements_complete', 'resource_costs', 'resource_balances',
                        'resource_as_of', 'gcd_ms', 'cast_ms', 'channel_ms', 'cooldown_remaining',
                        'earliest_execute', 'occupancy_start', 'occupancy_end', 'occupancy_domains', 'target_id'}
_ACTION_EVENT_FIELDS = {'kind', 'capture_stage', 'attempt', 'success', 'outcome', 'actual_form',
                        'ready_action', 'native_qualified', 'failure_reason', 'target_id'}
_EFFECT_AUDIT_FIELDS = {'effect_id', 'component_id', 'instance_id', 'source_id', 'target_id',
                        'applicable', 'lifecycle_complete'}
_OBSERVATION_FIELDS = {
    'action_observations': _OBSERVATION_ID_FIELDS | _ACTION_AUDIT_FIELDS | {
        'run_id', 'source_position', 'effect_completion_time', 'estimated_effect_completion_time',
        'effect_completion_estimate', 'charges_current', 'charges_maximum', 'has_cooldown',
        'execution_time', 'execution_event_index', 'execution_actual_form', 'timing_precision'},
    'action_events': _OBSERVATION_ID_FIELDS | _ACTION_EVENT_FIELDS,
    'state_observations': _OBSERVATION_ID_FIELDS | {'run_id', 'value', 'maximum', 'resource_as_of',
        'target_id', 'gcd', 'casting', 'channeling', 'queue_committed'},
    'effect_observations': _OBSERVATION_ID_FIELDS | _EFFECT_AUDIT_FIELDS | {
        'run_id', 'active', 'stacks', 'remains', 'episode_id', 'applied', 'refreshed', 'extended',
        'scheduled_expiry', 'actual_end_reason', 'source_input_index', 'gap_start', 'gap_end'},
    'effect_events': _OBSERVATION_ID_FIELDS | _EFFECT_AUDIT_FIELDS | {
        'run_id', 'kind', 'stacks', 'start', 'end', 'end_reason', 'scheduled_end',
        'source_input_index', 'source_actual_action'}}
_OBSERVATION_SOURCES = {
    **{'student.' + name: name for name in _OBSERVATION_FIELDS if name != 'action_events'},
    'student.effect_component_scopes': 'effect_observations',
    **{name: None for name in ('student.inputs', 'student.target_scope', 'student.observation_bounds',
        'candidate.structure', 'candidate.expanded_position_map', 'evaluation.prior_rule_trigger_records',
        'frozen.inputs', 'execution.policy_evidence')}}


def _validate_observation_request(request):
    if (not isinstance(request, dict) or type(request.get('protocol')) is not int
            or request['protocol'] not in (1, 2) or not isinstance(request.get('objects'), dict)):
        raise ValueError('未支持的冻结规则观察请求')
    if request['protocol'] == 2:
        collections = request.get('collections')
        if not isinstance(collections, dict) or set(collections) != set(_OBSERVATION_FIELDS):
            raise ValueError('冻结规则观察集合无效')
        for name, aliases in collections.items():
            if not isinstance(aliases, dict): raise ValueError('冻结规则观察集合无效')
            for alias, fields in aliases.items():
                if (alias not in request['objects'] or not isinstance(fields, list)
                        or any(not isinstance(field, str) for field in fields)
                        or not set(fields) <= _OBSERVATION_FIELDS[name]):
                    raise ValueError('冻结规则观察字段无效')


def rebind(diagnostic, task_run_id, *, diagnostic_logging=False):
    """缓存证据保持原批次来源；操作身份绑定当前任务的同一父结构。"""
    from search import digest
    if not diagnostic:
        return diagnostic
    if diagnostic['evidence']['task_run_id'] == task_run_id:
        return diagnostic if diagnostic_logging else {key: value for key, value in diagnostic.items() if key != 'costs'}
    result = copy.deepcopy(diagnostic)
    if not diagnostic_logging: result.pop('costs', None)
    for value in (result['evidence'], result['parent']):
        value.setdefault('source_task_run_id', value['task_run_id'])
        value['task_run_id'] = task_run_id
    result['parent_identity'] = digest(result['parent'])
    for operation in result['pool']['operations']:
        concrete = {key: operation[key] for key in ('operation', 'unit', 'source_path', 'destination_path', 'block', 'count')}
        operation['operation_id'] = digest(dict(parent_identity=result['parent_identity'], operation=concrete))
    return result


def _public(value):
    if value is UNKNOWN:
        return None
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


def _and(values):
    return False if any(value is False for value in values) else (
        UNKNOWN if any(type(value) is not bool for value in values) else True)


class Unsupported(ValueError):
    pass


class Stopped(RuntimeError):
    pass


class Rows(list):
    """已证成员与尚未判定的成员分开；未知成员不进入支持候选集合。"""
    def __init__(self, known=(), uncertain=()):
        super().__init__(known)
        self.uncertain = list(uncertain)


_DUPLICATE_TRIGGER = object()


def _prior_queries(template):
    """仅识别纯有序 any3(map(lookup_unique))，不解释业务模板名。"""
    reads = {row['as']: row for row in template['reads']
             if row['from'] == 'evaluation.prior_rule_trigger_records'}
    found = {}

    def visit(value):
        if isinstance(value, list):
            for item in value: visit(item)
        elif isinstance(value, dict):
            args = value.get('args', [])
            if value.get('op') == 'any3' and isinstance(args, list) and len(args) == 1:
                mapping = args[0]
                if isinstance(mapping, dict) and mapping.get('op') == 'map' and mapping.get('let', []) == []:
                    parts = mapping.get('args', [])
                    if isinstance(parts, list) and len(parts) == 2:
                        refs, lookup = parts
                        alias = mapping.get('as')
                        if (isinstance(refs, dict) and set(refs) == {'arg'} and isinstance(lookup, dict)
                                and lookup.get('op') == 'lookup_unique' and lookup.get('duplicate') == 'error'
                                and lookup.get('missing') == 'unknown' and lookup.get('value_field') == 'trigger'):
                            relation = lookup.get('args', [])
                            if isinstance(relation, list) and len(relation) == 2:
                                source, query = relation
                                fields = query.get('fields', {}) if isinstance(query, dict) else {}
                                key = fields.get('input_index') if isinstance(fields, dict) else None
                                view = source.get('var') if isinstance(source, dict) and set(source) == {'var'} else None
                                read = reads.get(view) if isinstance(view, str) else None
                                if (read is not None and '.' not in view and isinstance(query, dict) and read['object'] == refs
                                        and {'input_index', 'rule_name', 'trigger'} <= set(read['fields'])
                                        and query.get('op') == 'record' and set(fields) == {'input_index', 'rule_name'}
                                        and isinstance(alias, str) and '.' not in alias and alias != view
                                        and fields['rule_name'] == {'var': alias}
                                        and isinstance(key, dict) and set(key) == {'var'}
                                        and isinstance(key['var'], str) and key['var'].split('.')[0] != alias):
                                    found[id(value)] = (refs['arg'], view, key)
            for item in value.values(): visit(item)
    visit(template['diagnose'])
    visit(template['edits'])
    return found


class _PriorTriggerPrefix:
    """一个状态内前序唯一关联的有序OR；缺项/歧义保持延迟求值语义。"""
    def __init__(self, inputs):
        self.values = {row['input_index']: False for row in inputs}
        self.sample_ids = {row['sample_id'] for row in inputs}
        self.names = []
        self.valid = True

    def queries(self, specs, evaluator, views, env):
        if not self.valid: return {}
        result = {}
        for identity, (argument, alias, key) in specs.items():
            refs, view = evaluator.arguments.get(argument), views.get(alias)
            if (type(refs) is list and refs == self.names and isinstance(view, Rows)
                    and not view.uncertain and env.get(alias) is view):
                result[identity] = (key, alias, view, self.values)
        return result

    def advance(self, name, triggers, check):
        if not self.valid: return
        if name in self.names:
            self.valid = False
            return
        grouped = {}
        if triggers is not UNKNOWN:
            for row in triggers:
                check()
                if not isinstance(row, dict):
                    self.valid = False
                    return
                key = row.get('input_index')
                if (type(key) is not int or key not in self.values or isinstance(row.get('value'), dict)
                        or ('sample_id' in row and (type(row['sample_id']) is not int
                                                  or row['sample_id'] not in self.sample_ids))):
                    self.valid = False
                    return
                grouped.setdefault(key, []).append(row)
        for key, previous in self.values.items():
            check()
            if previous is True or previous is _DUPLICATE_TRIGGER: continue
            records = grouped.get(key, [])
            if len(records) > 1: self.values[key] = _DUPLICATE_TRIGGER
            elif not records: self.values[key] = UNKNOWN
            else:
                value = records[0].get('trigger', UNKNOWN)
                self.values[key] = True if value is True else previous if value is False else UNKNOWN
        self.names.append(name)


class Evaluation:
    def __init__(self, objects, arguments, gaps, check, range_contains, observation_bounds):
        self.objects, self.arguments, self.gaps = objects, arguments, gaps
        self.check = check
        self.range_contains = range_contains
        self.observation_bounds = observation_bounds
        self.indexes = {}
        self.interval_choices = {}
        self.unknown_evidence = []
        self.prior_queries = {}
        self.index_statistics = None

    @staticmethod
    def field(row, path):
        for part in path.split('.'):
            if not isinstance(row, dict) or row.get(part) is None:
                return UNKNOWN
            row = row[part]
        return row

    def join_field(self, row, field):
        if field in row:
            return UNKNOWN if row[field] is None else row[field]
        matches = [value[field] for value in row.values() if isinstance(value, dict) and field in value]
        if not matches: return UNKNOWN
        if any(value != matches[0] for value in matches[1:]):
            raise Unsupported('同次关联键来源歧义: ' + field)
        return UNKNOWN if matches[0] is None else matches[0]

    def event_intervals(self, rows, declaration):
        groups, result = {}, Rows()
        uncertain_ids = {id(row) for row in getattr(rows, 'uncertain', [])}
        for row in [*rows, *getattr(rows, 'uncertain', [])]:
            self.check()
            if row.get('coverage_unknown') is True:
                result.uncertain.append(row)
                self.unknown_evidence.append(dict(operation='pair_intervals', reason='object_coverage_unknown',
                    records=[{key: row[key] for key in ('object', 'run_id', 'sample_id') if key in row}]))
                continue
            key = tuple(self.field(row, path) for path in declaration['group_by'])
            if any(value is UNKNOWN for value in key):
                raise Unsupported('效果事件缺少实例/目标/来源身份')
            groups.setdefault(key, []).append(row)
        for events in groups.values():
            ordered = sorted(events, key=lambda row: (row['time'], row['event_index']))
            first, last = ordered[0], ordered[-1]
            if any(row.get('lifecycle_complete') is not True or id(row) in uncertain_ids for row in events):
                self.unknown_evidence.append(dict(operation='pair_intervals', reason='incomplete_lifecycle',
                    records=[{key: events[0][key] for key in ('run_id', 'batch_key', 'sample_id',
                        'effect_id', 'instance_id', 'target_id', 'source_id') if key in events[0]}]))
                result.uncertain.append(dict(first, start=first.get('start'), end=last.get('end'),
                    lifecycle_complete=False, start_event_index=first['event_index'], end_event_index=last['event_index']))
                continue
            start, end = first.get('start'), last.get('end')
            if (type(start) not in (int, float) or type(end) not in (int, float) or start > end
                    or not isinstance(last.get('end_reason'), str)):
                raise Unsupported('效果实例缺少完整实际边界/终止原因')
            result.append(dict(first, start=start, end=end, end_reason=last['end_reason'],
                start_event_index=first['event_index'], end_event_index=last['event_index'],
                terminating_source_input_index=last.get('source_input_index'),
                terminating_source_actual_action=last.get('source_actual_action')))
        return result

    def conditional_intervals(self, rows, declaration, env):
        """只在实际生命周期边沿间求条件；输入快照仅提供已证身份和需求点。"""
        events = self.value(declaration['event_rows'], env)
        bounds = self.value(declaration['bounds'], env)
        if events is UNKNOWN or bounds is UNKNOWN: return UNKNOWN
        start, end = bounds.get('start'), bounds.get('end')
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end) or start > end):
            raise Unsupported('实际条件区间缺少观察边界')
        fields = list(dict.fromkeys(['run_id', 'sample_id', *declaration['group_by']]))
        state_path = declaration['state_field'].split('.')
        classified = Rows(uncertain=getattr(events, 'uncertain', []))
        for row in events:
            (classified if type(self.field(row, declaration['state_field'])) is bool
             else classified.uncertain).append(row)
        intervals = self.event_intervals(classified, dict(group_by=declaration['event_group_by']))

        def set_field(record, path, value):
            for part in path[:-1]: record = record.setdefault(part, {})
            record[path[-1]] = value

        def boundary(row, edge):
            value = row.get(edge)
            fallback = (start, -1) if edge == 'start' else (end, math.inf)
            return (value, row.get(edge + '_event_index', fallback[1])) if type(value) in (int, float) else fallback

        groups, result = {}, Rows()
        for uncertain, members in ((False, rows), (True, getattr(rows, 'uncertain', []))):
            for row in members:
                self.check()
                key = tuple(self.field(row, field) for field in fields)
                if any(value is UNKNOWN for value in key):
                    result.uncertain.append(dict(lifecycle_complete=False))
                    continue
                group = groups.setdefault(key, Rows())
                (group.uncertain if uncertain else group).append(row)
        for key, members in groups.items():
            identity = {}
            for field, value in zip(fields, key): set_field(identity, field.split('.'), value)
            state = self.field(members[0] if members else members.uncertain[0], '.'.join(state_path[:-1]))
            alias = state.get('object') if isinstance(state, dict) else None
            identity['object'] = alias
            timed = []
            for row in members:
                at, index = self.field(row, declaration['input_time_field']), self.field(row, declaration['input_event_index_field'])
                if type(at) in (int, float) and math.isfinite(at) and type(index) is int:
                    timed.append(((at, index), row))
                else:
                    self.unknown_evidence.append(dict(operation='pair_intervals', reason='input_boundary_unknown',
                        records=[{field: row[field] for field in ('run_id', 'sample_id', 'input_index')}]))
            def matches(row):
                return tuple(self.field(row, field) for field in fields) == key
            known = [row for row in intervals if matches(row)]
            possible = [row for row in intervals.uncertain if matches(row) or (
                row.get('coverage_unknown') is True and row.get('object') == alias
                and all(row.get(field) == identity[field] for field in ('run_id', 'sample_id')))]
            points = {(start, -1), (end, math.inf)}
            for row in [*known, *possible]:
                for edge, default in (('start', -1), ('end', math.inf)):
                    value = row.get(edge)
                    if type(value) in (int, float) and start <= value <= end and not (edge == 'end' and value == end):
                        points.add((value, row.get(edge + '_event_index', default)))
            points = sorted(points)
            for left, right in zip(points, points[1:]):
                self.check()
                required = [row for point, row in timed if left <= point < right]
                if left[0] == right[0] and not required: continue
                active = any((row['start'], row['start_event_index']) <= left <
                             (row['end'], row['end_event_index']) for row in known)
                uncertain = not active and any(boundary(row, 'start') < right and
                                              boundary(row, 'end') > left for row in possible)
                local = copy.deepcopy(identity)
                set_field(local, state_path, UNKNOWN if uncertain else active)
                condition = self.value(declaration['condition'], dict(env, **{declaration['as']: local}))
                if condition is False: continue
                previous = [row for row in known if (row['end'], row['end_event_index']) <= left]
                preceding = max(previous, key=lambda row: (row['end'], row['end_event_index'])) if previous else {}
                previous_end = (preceding['end'], preceding['end_event_index']) if preceding else (start, -1)
                if any(boundary(row, 'start') < left and boundary(row, 'end') > previous_end for row in possible):
                    preceding = UNKNOWN
                gap = dict(identity, start=left[0], end=right[0], preceding_interval=preceding,
                    required_inputs=[{field: row[field] for field in ('run_id', 'sample_id', 'input_index')}
                                     for row in required])
                if left[1] >= 0: gap['start_event_index'] = left[1]
                if math.isfinite(right[1]): gap['end_event_index'] = right[1]
                (result if condition is True and members else result.uncertain).append(gap)
        return result

    def matching_rows(self, rows, fields, values, *, include_unknown=False):
        """同一不可变行集的等值关联索引，仅在一次规则求值中复用。"""
        key = (id(rows), tuple(fields))
        if self.index_statistics is not None:
            self.index_statistics['index_queries'] += 1
        if key not in self.indexes:
            if self.index_statistics is not None:
                self.index_statistics['index_builds'] += 1
                self.index_statistics['index_build_rows'] += len(rows)
            index, unknown = {}, []
            for row in rows:
                identity = tuple(self.field(row, field) for field in fields)
                if any(value is UNKNOWN for value in identity): unknown.append(row)
                else: index.setdefault(identity, []).append(row)
            self.indexes[key] = (rows, index, unknown)
        index, unknown = self.indexes[key][1:]
        result = index.get(tuple(values), []) + (unknown if include_unknown else [])
        if self.index_statistics is not None:
            self.index_statistics['index_matched_rows'] += len(result)
        return result

    @staticmethod
    def interval_key(window):
        return tuple(window.get(key) for key in ('run_id', 'sample_id', 'effect_id', 'instance_id',
            'target_id', 'source_id', 'start_event_index', 'end_event_index'))

    @staticmethod
    def within_interval(row, window, at):
        if any(row.get(key) != window.get(key) for key in ('run_id', 'sample_id')): return False
        after_start = at > window['start'] or at == window['start'] and row.get('event_index', -1) >= window['start_event_index']
        before_end = at < window['end'] or at == window['end'] and row.get('event_index', math.inf) <= window['end_event_index']
        return after_start and before_end

    def lets(self, declarations, env, *, diagnostic=None):
        if not isinstance(declarations, list):
            raise Unsupported('未支持的let声明')
        for row in declarations:
            if diagnostic is None:
                env[row['name']] = self.value(row['value'], env)
            else:
                owner, label = diagnostic
                started, value = diagnostic_start(), UNKNOWN
                try:
                    value = self.value(row['value'], env)
                    env[row['name']] = value
                finally:
                    diagnostic_finish(owner, label + '.let.' + row['name'], started,
                        rows=len(value) if isinstance(value, list) else 0,
                        uncertain_rows=len(getattr(value, 'uncertain', ())), unknown=int(value is UNKNOWN))

    def value(self, expression, env):
        if isinstance(expression, list):
            return [self.value(item, env) for item in expression]
        if not isinstance(expression, dict):
            return expression
        if 'arg' in expression:
            return self.arguments[expression['arg']]
        if 'var' in expression:
            result = env
            for part in expression['var'].split('.'):
                if not isinstance(result, dict) or part not in result or result[part] is None:
                    return UNKNOWN
                result = result[part]
            return result
        if 'op' not in expression:
            return {key: self.value(item, env) for key, item in expression.items()}
        op, args = expression['op'], expression.get('args', [])
        if op in ('and', 'or'):
            unknown = False
            for item in args:
                value = self.value(item, env)
                if value is (False if op == 'and' else True): return value
                unknown |= type(value) is not bool
            return UNKNOWN if unknown else op == 'and'
        if op == 'any3' and isinstance(args[0], dict) and args[0].get('op') == 'map':
            prepared = self.prior_queries.get(id(expression))
            if prepared is not None:
                key_expression, alias, view, values = prepared
                if env.get(alias) is view:
                    self.check()
                    key = self.value(key_expression, env)
                    if type(key) is int and key in values:
                        value = values[key]
                        if value is _DUPLICATE_TRIGGER: raise Unsupported('同次事实关联不唯一')
                        return value
            declaration = args[0]
            rows = self.value(declaration['args'][0], env)
            if rows is UNKNOWN: return UNKNOWN
            uncertain_rows = getattr(rows, 'uncertain', [])
            predicate, alias = declaration['args'][1], declaration['as']
            # any(and(..., row.key == outer.key))的非匹配行恒为false，
            # 可按声明的等值键索引；不改变未知、重复或事件顺序。
            if isinstance(predicate, dict) and predicate.get('op') == 'and':
                for term in predicate['args']:
                    if not isinstance(term, dict) or term.get('op') != 'eq': continue
                    left, right = term['args']
                    if isinstance(right, dict) and right.get('var', '').startswith(alias+'.'): left, right = right, left
                    field = left.get('var', '') if isinstance(left, dict) else ''
                    if not field.startswith(alias+'.') or '.' in field[len(alias)+1:]: continue
                    value = self.value(right, env)
                    if value is not UNKNOWN:
                        rows = self.matching_rows(rows, [field[len(alias)+1:]], [value], include_unknown=True)
                        uncertain_rows = self.matching_rows(uncertain_rows, [field[len(alias)+1:]], [value], include_unknown=True)
                        break
            unknown = False
            for uncertain, members in ((False, rows), (True, uncertain_rows)):
                for row in members:
                    self.check()
                    local = dict(env, **{alias: row})
                    self.lets(declaration.get('let', []), local)
                    value = self.value(predicate, local)
                    if value is True and not uncertain: return True
                    unknown |= type(value) is not bool or uncertain and value is True
            return UNKNOWN if unknown else False
        if op in ('map', 'filter'):
            rows = self.value(args[0], env)
            if rows is UNKNOWN:
                return UNKNOWN
            result = Rows()
            for uncertain, members in ((False, rows), (True, getattr(rows, 'uncertain', []))):
                for row in members:
                    self.check()
                    local = dict(env, **{expression['as']: row})
                    self.lets(expression.get('let', []), local)
                    value = self.value(args[1], local)
                    if op == 'map':
                        (result.uncertain if uncertain else result).append(value)
                    elif value is not False:
                        if uncertain or type(value) is not bool: result.uncertain.append(row)
                        elif value is True: result.append(row)
            return result
        if op == 'join':
            keys, joined = expression['keys'], None
            for declaration in args:
                rows = self.value(declaration['rows'], env)
                if rows is UNKNOWN: return UNKNOWN
                projected = Rows()
                for uncertain, members in ((False, rows), (True, getattr(rows, 'uncertain', []))):
                    for row in members:
                        self.check()
                        value = dict(row) if declaration['as'] is None else {declaration['as']: row}
                        for field in dict.fromkeys(['run_id', 'batch_key', 'sample_id', 'input_index', *keys]):
                            key_value = self.join_field(row, field)
                            if key_value is not UNKNOWN: value[field] = key_value
                        (projected.uncertain if uncertain else projected).append(value)
                if joined is None:
                    joined = projected
                    continue
                if not joined and not joined.uncertain: return Rows()
                index = {}
                for uncertain, members in ((False, projected), (True, projected.uncertain)):
                    for row in members:
                        key = tuple(self.join_field(row, field) for field in keys)
                        if any(value is UNKNOWN for value in key): raise Unsupported('同次关联键缺失，不能证明无匹配')
                        index.setdefault(key, []).append((uncertain, row))
                result = Rows()
                for left_uncertain, members in ((False, joined), (True, joined.uncertain)):
                    for left in members:
                        self.check()
                        key = tuple(self.join_field(left, field) for field in keys)
                        if any(value is UNKNOWN for value in key): raise Unsupported('同次关联键缺失，不能证明无匹配')
                        matches = index.get(key, [])
                        if expression.get('join_type') == 'left' and not any(not uncertain for uncertain, _ in matches):
                            if declaration['as'] is None: raise Unsupported('未命名左关联缺少来源结构')
                            # 仅可能匹配的右成员也可能不存在，缺配分支不能被候选匹配抹掉。
                            matches = [*matches, (bool(matches), {declaration['as']: UNKNOWN})]
                        for right_uncertain, right in matches:
                            collisions = set(left) & set(right)
                            if any(left[field] != right[field] for field in collisions):
                                raise Unsupported('同次关联字段冲突，不能覆盖来源')
                            (result.uncertain if left_uncertain or right_uncertain else result).append(dict(left, **right))
                joined = result
            return joined if joined is not None else Rows()
        if op == 'select':
            condition = self.value(args[0], env)
            return self.value(args[1 if condition is True else 2], env) if type(condition) is bool else UNKNOWN
        if op == 'record':
            return {key: self.value(item, env) for key, item in expression['fields'].items()}
        if op in ('first_true', 'last_true'):
            rows = self.value(args[0], env)
            unknown_rows = self.value(expression.get('unknown_evidence', []), env)
            possible = [] if unknown_rows is UNKNOWN else [*unknown_rows, *getattr(unknown_rows, 'uncertain', [])]
            if rows is not UNKNOWN: possible += getattr(rows, 'uncertain', [])
            if possible:
                self.unknown_evidence.append(dict(operation=op, records=[
                    {key: row[key] for key in ('run_id', 'batch_key', 'sample_id', 'input_index',
                                              'target_id', 'component_id', 'event_index') if key in row}
                    for row in possible]))
            if rows is UNKNOWN: return UNKNOWN
            selected = []
            for row in rows:
                self.check()
                if self.value(args[1], dict(env, **{expression['as']: row})) is True:
                    selected.append(row)
            if not selected: return UNKNOWN if unknown_rows is UNKNOWN or possible else {}
            ordered = [(self.field(row, expression['order_by']), index, row)
                       for index, row in enumerate(selected)]
            if any(type(value) not in (int, float) for value, _, _ in ordered):
                raise Unsupported('首末选择缺少已知排序时刻')
            ordered.sort(key=lambda item: (item[0], item[1]))
            return ordered[0 if op == 'first_true' else -1][2]
        values = [self.value(item, env) for item in args]
        if op == 'unknown': return any(value is UNKNOWN for value in values)
        if op == 'and': return _and(values)
        if op == 'or':
            return True if any(value is True for value in values) else (
                UNKNOWN if any(type(value) is not bool for value in values) else False)
        if op in ('any3', 'all3'):
            if values[0] is UNKNOWN: return UNKNOWN
            uncertain = getattr(values[0], 'uncertain', [])
            return (True if any(value is True for value in values[0]) else (
                UNKNOWN if any(type(value) is not bool for value in values[0]) or any(value is not False for value in uncertain)
                else False)) if op == 'any3' else (
                    False if any(value is False for value in values[0]) else
                    UNKNOWN if any(value is not True for value in uncertain) else _and(values[0]))
        if op == 'is_number': return type(values[0]) in (int, float) and math.isfinite(values[0])
        if op == 'is_integer': return type(values[0]) is int
        if op == 'is_true': return values[0] is True
        if any(value is UNKNOWN for value in values): return UNKNOWN
        if op == 'not': return not values[0] if type(values[0]) is bool else UNKNOWN
        if op == 'merge': return {key: item for value in values for key, item in value.items()}
        if op == 'eq': return values[0] == values[1]
        if op == 'compare':
            return self.value(dict(op=values[1], args=[values[0], values[2]]), env)
        if op in ('lt', 'lte', 'gt', 'gte'):
            if type(values[0]) not in (int, float) or type(values[1]) not in (int, float): return UNKNOWN
            return {'lt': lambda a,b:a<b, 'lte':lambda a,b:a<=b,
                    'gt':lambda a,b:a>b, 'gte':lambda a,b:a>=b}[op](*values)
        if op == 'entries': return [dict(key=key, value=value) for key, value in values[0].items()]
        if op == 'lookup': return values[0].get(values[1], UNKNOWN)
        if op == 'lookup_unique':
            rows = self.matching_rows(values[0], list(values[1]), list(values[1].values()))
            if len(rows) > 1: raise Unsupported('同次事实关联不唯一')
            return rows[0].get(expression['value_field'], UNKNOWN) if rows else UNKNOWN
        if op == 'contains':
            if isinstance(values[0], str) and self.objects.get(values[0], {}).get('kind') == 'range':
                return self.range_contains(values[0], values[1])
            if values[1] in values[0]: return True
            if (any(item is UNKNOWN for item in values[0]) or any(item is UNKNOWN or item == values[1]
                    for item in getattr(values[0], 'uncertain', []))): return UNKNOWN
            return False
        if op == 'object_field': return self.objects[values[0]].get(values[1], UNKNOWN)
        if op == 'block': return [dict(unit='action_block', actions=[values[0]], source_position=None)]
        if op == 'resolve_edit_gaps': return self.gaps(values[1], values[2], values[3], expression)
        if op == 'empty': return False if values[0] else UNKNOWN if getattr(values[0], 'uncertain', []) else True
        if op == 'count': return UNKNOWN if getattr(values[0], 'uncertain', []) else len(values[0])
        if op == 'subtract': return values[0] - values[1]
        if op == 'matches_native_object':
            declaration = self.objects[values[1]]
            if declaration['kind'] == 'action':
                return values[0] in declaration.get('native_forms', [declaration['native_action']])
            if declaration['kind'] == 'source' and declaration.get('value') == 'controlled_player':
                actor = self.observation_bounds.get('controlled_actor_index', UNKNOWN)
                return values[0] == actor if actor is not UNKNOWN else UNKNOWN
            if 'native_identity' in declaration: return values[0] == declaration['native_identity']
            raise Unsupported('原生对象身份读取尚未支持')
        if op == 'pair_intervals':
            if 'condition' in expression:
                if not all(key in expression for key in ('event_rows', 'event_group_by', 'bounds', 'state_field',
                                                        'input_time_field', 'input_event_index_field')):
                    raise Unsupported('条件区间缺少显式实际事件声明')
                return self.conditional_intervals(values[0], expression, env)
            return self.event_intervals(values[0], expression)
        if op == 'interval_select':
            if values[1] != 'earliest_end': raise Unsupported('未支持的区间选择方式')
            windows = sorted(values[0], key=lambda row: (row['start'], row['end'], row['start_event_index']))
            # 原实例边界不改写；各输入独立选择当前有效且结束最早的实例。
            choices = (sorted(windows, key=lambda row: (row['end'], row['end_event_index'])), {})
            for window in windows: self.interval_choices[self.interval_key(window)] = choices
            return Rows(windows, getattr(values[0], 'uncertain', []))
        if op == 'join_interval':
            window, result = values[1], Rows()
            window_key = self.interval_key(window)
            choices = self.interval_choices.get(window_key)
            uncertain_rows = getattr(values[0], 'uncertain', [])
            uncertain_ids = {id(row) for row in uncertain_rows}
            for row in [*values[0], *uncertain_rows]:
                self.check()
                at = self.field(row, expression['time_field'])
                if type(at) not in (int, float):
                    if all(row.get(key) == window.get(key) for key in ('run_id', 'sample_id')):
                        result.uncertain.append({expression['alias']: row, **{key: row[key] for key in
                            ('run_id', 'batch_key', 'sample_id', 'input_index') if key in row}})
                    continue
                if window.get('lifecycle_complete') is False:
                    if any(row.get(key) != window.get(key) for key in ('run_id', 'sample_id')): continue
                    start, end = window.get('start'), window.get('end')
                    if type(start) in (int, float) and (at < start or at == start
                            and row.get('event_index', -1) < window.get('start_event_index', -1)): continue
                    if type(end) in (int, float) and (at > end or at == end
                            and row.get('event_index', math.inf) > window.get('end_event_index', math.inf)): continue
                    result.uncertain.append({expression['alias']: row, **{key: row[key] for key in
                        ('run_id', 'batch_key', 'sample_id', 'input_index') if key in row}})
                    continue
                if choices is not None:
                    windows, selected = choices
                    identity = (row.get('run_id'), row.get('sample_id'), at, row.get('event_index'))
                    if identity not in selected:
                        selected[identity] = next((self.interval_key(item) for item in windows
                                                  if self.within_interval(row, item, at)), None)
                    included = selected[identity] == window_key
                else:
                    included = self.within_interval(row, window, at)
                if included:
                    (result.uncertain if id(row) in uncertain_ids else result).append({expression['alias']: row, **{key: row[key] for key in
                        ('run_id', 'batch_key', 'sample_id', 'input_index') if key in row}})
            return result
        if op == 'adjacent':
            if expression.get('left_edge') != 'observation_start':
                raise Unsupported('未支持的相邻区间边界')
            start = self.observation_bounds.get('start', UNKNOWN)
            if type(start) not in (int, float): return UNKNOWN
            anchors = [self.field(row, 'time') for row in values[0]]
            if any(type(value) not in (int, float) for value in anchors): return UNKNOWN
            anchors.sort()
            if len(anchors) != len(set(anchors)): raise Unsupported('冻结锚点时刻歧义')
            return [dict(left=left, right=right) for left, right in zip([start, *anchors], anchors)]
        raise Unsupported('模板操作尚未接通: ' + op)


def _structure(program):
    rows, expanded = [], []
    for index, segment in enumerate(program):
        if isinstance(segment, list):
            rows.append(dict(source_position=[index], unit='action_block', actions=segment, wait_clicks=0))
            expanded.append([index])
        elif segment['kind'] == 'Loop':
            for child, block in enumerate(segment['blocks']):
                rows.append(dict(source_position=[index, child], unit='action_block', actions=block, wait_clicks=0))
            expanded.extend([[index, child] for _ in range(segment['count']) for child in range(len(segment['blocks']))])
        elif segment['kind'] == 'WaitClicks':
            rows.append(dict(source_position=[index], unit='wait_block', actions=[], wait_clicks=segment['clicks']))
            expanded.extend([[index]] * segment['clicks'])
        else:
            expanded.append(None)
    return rows, expanded


def _observed_rows(payload, position_map, objects, burst_exclusions):
    """合并同一输入的确定执行结果，不把后态资格回写为输入前资格。"""
    collections = {name: rows for name, rows in payload.items() if isinstance(rows, list)}
    outcomes, positions = {}, {row['input_index']: row['source_position'] for row in position_map}
    for event in payload.get('action_events', []):
        identity = (event.get('object'), event.get('sample_id'), event.get('input_index'))
        outcomes.setdefault(identity, []).append(event)
    actions = []
    protected_actions = set((burst_exclusions or {}).get('actions', []))
    resource_aliases = {}
    for name, declaration in objects.items():
        if declaration['kind'] == 'resource':
            resource_aliases.setdefault(declaration['native_identity'], []).append(name)
    for original in payload.get('action_observations', []):
        row = dict(original, source_position=positions.get(original['input_index']),
                   execution_time=None, execution_event_index=None, execution_actual_form=None)
        declaration = objects.get(row.get('object'), {})
        if (declaration.get('kind') == 'action' and protected_actions.intersection(
                [declaration['native_action'], declaration['base_button'], *declaration.get('native_forms', [])])):
            # 冻结计划限制普通侧资格，须先于模板触发/高位让位判定；实际执行证据仍保留。
            row['input_allowed'] = False
        actual_form = row.get('actual_form')
        if (declaration.get('kind') == 'action' and isinstance(actual_form, str) and actual_form
                and actual_form not in declaration.get('native_forms', [declaration['native_action']])):
            # 一个已知原生形态不符即可证明负资格；不声称调用/完成过ready。
            row['native_qualified'] = False
            row['known_native_requirements'] = [*(row.get('known_native_requirements') or []),
                dict(name='configured_native_form', value=False)]
        for field in ('resource_costs', 'resource_balances'):
            if isinstance(row.get(field), dict):
                row[field] = {alias: value for name, value in row[field].items()
                              for alias in resource_aliases.get(name, [name])}
        events = outcomes.get((row.get('object'), row.get('sample_id'), row['input_index']), [])
        executed = [event for event in events if event.get('kind') == 'execute' and event.get('success') is True]
        unselected = [event for event in events if event.get('kind') == 'outcome'
                      and event.get('outcome') == 'not_attempted' and event.get('success') is False]
        qualification = [event for event in events if event.get('kind') == 'qualification']
        if executed and unselected:
            row.update(success=None, attempt=None, outcome_unknown='contradictory_execution_evidence')
        elif executed:
            row.update(success=True, attempt=True,
                       execution_event_refs=[event['event_index'] for event in executed])
            if len(executed) == 1:
                row.update(execution_time=executed[0].get('time'),
                           execution_event_index=executed[0]['event_index'],
                           execution_actual_form=executed[0].get('actual_form'))
        elif unselected:
            row.update(success=False, attempt=False,
                       outcome_event_refs=[event['event_index'] for event in unselected])
        elif qualification:
            row['attempt'] = True
        # 原生实际ready属于其事件阶段，绝不与输入前Buff/资源混成原子事实。
        row['qualification_event_refs'] = [event['event_index'] for event in qualification]
        actions.append(row)
    collections['action_observations'] = actions
    collections['inputs'] = [{**row.get('occupancy', {}), **row,
        'source_position': positions.get(row['input_index'])} for row in payload['inputs']]
    scopes = []
    for row in payload['inputs']:
        declared = row.get('target_scopes')
        for name, definition in objects.items():
            if definition['kind'] != 'target_scope': continue
            members = declared.get(name) if isinstance(declared, dict) else None
            # NULL/缺项不等于已证空目标集合；不从动作当前目标猜所需范围。
            for member in members if isinstance(members, list) else [None]:
                fields = {key: member[key] for key in ('target_id', 'required')
                          if isinstance(member, dict) and key in member}
                scopes.append(dict(row, object=name, **fields))
    collections['target_scope'] = scopes
    # 组件资格由同次原生字段提供；范围内目标不能被这里升级为applicable=True。
    collections['effect_component_scopes'] = collections.get('effect_observations', [])
    return collections


def _validate_observations(payload, requested_iterations, *, observation_request=None):
    if (not isinstance(payload, dict) or type(payload.get('protocol')) is not int
            or payload['protocol'] not in (1, 2)):
        raise Unsupported('同次计分批次缺少规则观察协议')
    if payload['protocol'] == 2:
        try:
            # typed report 的空 struct 会还原为 NULL。仅在与完整冻结请求
            # 逐值匹配后信任该形状；无冻结预期时绝不把缺项或 NULL 猜成空请求。
            _validate_observation_request(observation_request if observation_request is not None
                                          else payload.get('request'))
        except ValueError as error:
            raise Unsupported(str(error)) from error
        if not isinstance(payload.get('request'), dict) or payload['request'].get('protocol') != 2:
            raise Unsupported('观察响应与请求协议不符')
    if observation_request is not None:
        from result_store import _report_columns
        if (payload['protocol'] != observation_request['protocol'] or payload['protocol'] == 2
                and _report_columns(payload['request']) != _report_columns(observation_request)):
            raise Unsupported('观察响应与任务冻结请求不符')
    scope = payload.get('scope')
    if (not isinstance(scope, dict) or scope.get('sample_selection') != 'first_scored_complete'
            or type(scope.get('sample_id')) is not int or type(scope.get('complete')) is not bool):
        raise Unsupported('同次观察范围身份缺失')
    if payload['protocol'] == 2:
        coverage = scope.get('effect_events_complete')
        if coverage is None: coverage = {}
        if (not isinstance(coverage, dict)
                or not set(coverage) <= set(payload['request']['collections']['effect_events'] or {})
                or any(type(value) is not bool for value in coverage.values())):
            raise Unsupported('效果完整性超出任务采集范围')
    if requested_iterations is not None and scope['sample_id'] != (0 if requested_iterations == 1 else 1):
        raise Unsupported('观察不是当前批次首个真实计分样本，不能使用warmup')
    inputs = payload.get('inputs')
    if not isinstance(inputs, list): raise Unsupported('同次输入身份缺失')
    identities = set()
    for row in inputs:
        if (not isinstance(row, dict) or type(row.get('sample_id')) is not int or row['sample_id'] != scope['sample_id']
                or type(row.get('input_index')) is not int or row['input_index'] < 0):
            raise Unsupported('输入与计分样本身份不符')
        identity = (row['sample_id'], row['input_index'])
        if identity in identities: raise Unsupported('同次输入身份歧义')
        identities.add(identity)
    for collection in ('action_observations', 'action_events', 'state_observations', 'effect_observations'):
        if not isinstance(payload.get(collection, []), list): raise Unsupported('同次事实数组类型无效')
        for row in payload.get(collection, []):
            if (not isinstance(row, dict) or (row.get('sample_id'), row.get('input_index')) not in identities
                    or type(row.get('event_index')) is not int or row['event_index'] < 0):
                raise Unsupported('事实与同次输入/计分样本身份不符')
    if not isinstance(payload.get('effect_events', []), list): raise Unsupported('同次效果事件数组类型无效')
    for row in payload.get('effect_events', []):
        # 生命周期边沿没有必需的input_index；仍必须属于这个计分样本。
        if (not isinstance(row, dict) or type(row.get('sample_id')) is not int
                or row['sample_id'] != scope['sample_id']
                or type(row.get('event_index')) is not int or row['event_index'] < 0):
            raise Unsupported('效果事件与同次计分样本身份不符')
    # typed 空 struct 的 NULL 只在冻结请求已证明该集合为空时还原输出视图。
    # 不修改原始 payload，证据摘要仍绑定实际存储内容；缺 key 仍然缺失。
    if (payload['protocol'] == 2 and observation_request is not None
            and observation_request['collections']['effect_events'] == {}
            and 'effect_events_complete' in scope and scope['effect_events_complete'] is None):
        return dict(scope, effect_events_complete={})
    return scope


def feedback_observations(payload, requested_iterations, *, observation_request=None):
    """复用旧反馈解析器所需的真实控制事件；缺失不猜not_ready或未尝试。"""
    try:
        scope = _validate_observations(payload, requested_iterations, observation_request=observation_request)
        if not payload['scope']['complete']:
            raise Unsupported('首计分样本尚未完整结束')
        events = payload.get('feedback_events')
        if not isinstance(events, list): raise Unsupported('同次旧搜索反馈事件未接通')
        origins = {row['input_index']+1 for row in payload['inputs']}
        for row in events:
            if (not isinstance(row, dict) or row.get('battle') != payload['scope']['sample_id']
                    or type(row.get('origin')) is not int or row['origin'] not in origins
                    or type(row.get('step')) is not int or row['step'] < 0
                    or type(row.get('event_index')) is not int or row['event_index'] < 0
                    or not isinstance(row.get('event'), str) or row.get('source') not in ('loop', 'burst')):
                raise Unsupported('同次旧搜索反馈事件身份无效')
        return events, dict(availability='same_scoring_batch', observation_scope=scope)
    except Unsupported as error:
        return None, dict(availability='unavailable', reason=str(error))


def apply(program, operation):
    """只应用一个已枚举的结构操作；调用者仍须做原有合法性校验。"""
    result = copy.deepcopy(program)
    source, destination = operation['source_path'], operation['destination_path']
    if operation['operation'] in ('reduce_wait', 'remove_wait'):
        container = result if len(source) == 1 else result[source[0]]['blocks']
        wait = container[source[-1]]
        if not isinstance(wait, dict) or wait.get('kind') != 'WaitClicks':
            raise ValueError('等待操作来源不是完整等待块')
        count = operation['count']
        if type(count) is not int or count < 1: raise ValueError('等待改量无效')
        if operation['operation'] == 'remove_wait':
            if wait['clicks'] != count: raise ValueError('只可删除已证剩余的完整等待')
            container.pop(source[-1])
        else:
            if wait['clicks'] <= count: raise ValueError('等待减少后没有剩余点击')
            wait['clicks'] -= count
        return result
    container = result if len(destination) == 1 else result[destination[0]]['blocks']
    target = destination[-1]
    if operation['operation'] == 'move':
        if source[:-1] != destination[:-1]: raise ValueError('单步不能跨容器移动')
        block = container.pop(source[-1])
        if source[-1] < target: target -= 1
    elif operation['operation'] == 'insert': block = copy.deepcopy(operation['block'])
    else: raise ValueError('未支持的单步操作')
    container.insert(target, block)
    return result


def enqueue(state, request, config, used_seconds):
    """在原任务锁内校验确定单步并加入既有pending，不删除原起点。"""
    from program import canonicalize_search_program
    from search import digest
    if (not isinstance(request, dict) or set(request) != {'parent_identity', 'operation_id'}
            or any(not isinstance(value, str) or not value for value in request.values())):
        raise ValueError('rule_step需要明确父身份及操作ID')
    history = state.get('rule_steps', {})
    if request['operation_id'] in history:
        if history[request['operation_id']]['request'] != request:
            raise ValueError('单步请求身份不符')
        return history[request['operation_id']]['status']
    if len(state.get('evaluated_keys', [])) >= config['candidate_limit']:
        raise ValueError('候选预算已耗尽，不能执行规则单步')
    if used_seconds >= min(config['search_budget_seconds'], config['total_budget_seconds']):
        raise ValueError('时间预算已耗尽，不能执行规则单步')
    if state.get('inflight') or any(work.get('score_batches') for work in state.get('pending', [])):
        raise ValueError('已有评分中的pending，不能更换当前父单步')
    parents = [row for row in state.get('archive', [])
               if (row.get('rule_diagnostics') or {}).get('parent_identity') == request['parent_identity']]
    if len(parents) != 1: raise ValueError('规则单步父身份过期、外来或歧义')
    parent = parents[0]
    diagnostic = parent['rule_diagnostics']
    identity = diagnostic['parent']
    if (digest(identity) != request['parent_identity'] or identity['structure_identity'] != digest(parent['program'])
            or identity['behavior_identity'] != parent['key']
            or identity['rule_config_digest'] != state['rule_snapshot']['rule_config_digest']):
        raise ValueError('规则单步父程序或配置身份不符')
    options = [row for row in diagnostic['pool']['operations'] if row['operation_id'] == request['operation_id']]
    if len(options) != 1: raise ValueError('规则单步操作过期、外来或歧义')
    option = options[0]
    concrete = {key: option[key] for key in ('operation', 'unit', 'source_path', 'destination_path', 'block', 'count')}
    if digest(dict(parent_identity=request['parent_identity'], operation=concrete)) != request['operation_id']:
        raise ValueError('规则单步具体参数身份不符')
    changed = apply(parent['program'], option)
    canonical = canonicalize_search_program(changed, state['capabilities'])
    if canonical['identity'] != option['resulting_behavior_identity']:
        raise ValueError('规则单步行为身份不符')
    if canonical['identity'] in state.get('evaluated_keys', []):
        raise ValueError('规则单步候选已评分')
    step = dict(request=dict(request), parent_candidate_key=parent['key'], parent_score=parent['score'],
                operation=copy.deepcopy(option), status='queued')
    state.setdefault('rule_steps', {})[request['operation_id']] = step
    state['pending'].insert(0, dict(program=changed, start=True, rule_step=copy.deepcopy(step)))
    state.update(phase='search', status='interrupted')
    return 'queued'


def diagnose(program, capabilities, initialization, report, *, task_run_id, batch_key,
             behavior_identity, runtime, requested_iterations=None, batch_request=None):
    from engine import player_report
    from program import canonicalize_search_program
    from result_store import _report_columns
    from search import digest
    logging = runtime.diagnostic_logging
    started = diagnostic_start() if logging else None
    phase_started = started
    snapshot = initialization['rule_snapshot']
    configuration = next(row for row in snapshot['resolved'] if row['key'] == initialization['configuration_key'])
    objects = configuration['objects']
    # report已由原评分路径核验角色；这里不另行运行或补静态事实。
    players = report['sim']['players']
    raw_payload = players[0].get('sim2gse_rule_observations') if len(players) == 1 else None
    payload = raw_payload if isinstance(raw_payload, dict) else None
    payload_error = None
    observation_scope = payload.get('scope') if payload else None
    try:
        observation_scope = _validate_observations(payload, requested_iterations,
            observation_request=(batch_request or {}).get('rule_observations', {}).get('request'))
    except Unsupported as error:
        payload_error = str(error)
    if logging:
        diagnostic_finish(runtime, 'diagnostic.read_validate', phase_started, players=len(players),
                          inputs=len(payload['inputs']) if payload_error is None else 0)
        phase_started = diagnostic_start()
    if logging:
        detail_started = diagnostic_start()
        normalized_payload = _report_columns(raw_payload)
        diagnostic_finish(runtime, 'diagnostic.preprocess.normalize', detail_started)
        detail_started = diagnostic_start()
        observation_digest = digest(normalized_payload)
        del normalized_payload
        diagnostic_finish(runtime, 'diagnostic.preprocess.digest', detail_started)
        detail_started = diagnostic_start()
    else:
        observation_digest = digest(_report_columns(raw_payload))
    evidence = dict(task_run_id=task_run_id, batch_key=batch_key,
                    observation_digest=observation_digest,
                    rule_config_digest=snapshot['rule_config_digest'])
    if (batch_request or {}).get('purpose') == 'diagnostic':
        evidence.update(kind='on_demand_replay',
                        source_scoring_batch_key=batch_request['source_scoring_batch_key'])
    parent = dict(evidence, structure_identity=digest(program), behavior_identity=behavior_identity)
    parent_identity = digest(parent)
    structures, expanded = _structure(program)
    prefix = len(capabilities.get('precombat_actions', []))
    inputs = payload['inputs'] if payload_error is None else []
    position_map = []
    for row in inputs:
        click = row.get('source_step')
        path = (expanded[click-prefix] if row.get('input_source') == 'loop' and type(click) is int
                and 0 <= click-prefix < len(expanded) else None)
        position_map.append(dict(input_index=row['input_index'], source_position=path,
            parent_path=path[:-1] if path else None, occurrence=click,
            gap_before=path, gap_after=path[:-1]+[path[-1]+1] if path else None))
    if logging:
        diagnostic_finish(runtime, 'diagnostic.preprocess.positions', detail_started,
                          inputs=len(inputs), structures=len(structures), positions=len(position_map))
        detail_started = diagnostic_start()
    collections = _observed_rows(payload, position_map, objects, capabilities.get('burst_exclusions')) if payload_error is None else {}
    if logging:
        diagnostic_finish(runtime, 'diagnostic.preprocess.observed_rows', detail_started,
                          inputs=len(inputs), action_observations=len(collections.get('action_observations', ())),
                          action_events=len(collections.get('action_events', ())))

    def range_contains(range_ref, path):
        definition = objects[range_ref]
        matches = [row for row in structures if row['source_position'] == path]
        # 搜索程序只含普通序列，独立爆发不在此结构内，仍由check_loop保护。
        if definition['segments'] != 'ordinary_loop':
            raise Unsupported('编辑范围尚未支持: ' + definition['segments'])
        return len(matches) == 1 and matches[0]['unit'] in definition['allow_units']

    def gaps(source, input_index, range_ref, declaration):
        if objects[range_ref]['segments'] != 'ordinary_loop':
            raise Unsupported('编辑范围尚未支持: ' + objects[range_ref]['segments'])
        targets = [row['source_position'] for row in position_map if row['input_index'] == input_index]
        if len(targets) != 1 or targets[0] is None: raise Unsupported('输入来源位置缺失或歧义')
        target = targets[0]
        if source is None: indices = [target[-1]]
        elif declaration.get('direction') == 'later':
            container = program if len(source) == 1 else program[source[0]]['blocks']
            indices = range(source[-1]+2, len(container)+1)
            target = source
        elif source[:-1] != target[:-1]: return []
        elif source[-1] > target[-1]: indices = range(target[-1], source[-1])
        else: indices = range(source[-1]+2, target[-1]+2)
        return [dict(source_position=target[:-1]+[index]) for index in indices]

    operations, by_operation, behavior_seen, results, prior = [], {}, {behavior_identity}, [], []
    rejected_operations = {}
    rejections = {}

    def reject(reason):
        rejections[reason] = rejections.get(reason, 0) + 1

    def reject_edit(rule, edit, finding, error, source=None):
        reject('unsupported_edit')
        rule.setdefault('unsupported_edits', []).append(dict(operation=edit['operation'], unit=edit['unit'],
            source_path=source['source_position'] if source else None,
            evidence=_public(finding), reason=str(error)))

    incomplete_reason = None

    def check():
        nonlocal incomplete_reason
        from runtime import BudgetExceeded, TaskCancelled
        if incomplete_reason is not None: raise Stopped(incomplete_reason)
        try:
            runtime.check()
        except (BudgetExceeded, TaskCancelled) as error:
            incomplete_reason = 'cancelled' if isinstance(error, TaskCancelled) else 'budget_exhausted'
            raise Stopped(incomplete_reason) from error

    trigger_specs = {}
    if logging:
        detail_started = diagnostic_start()
    identity_rows = [dict(row, run_id=task_run_id, batch_key=batch_key) for row in collections.get('inputs', [])]
    effect_states = {}
    for item in collections.get('effect_observations', []):
        if isinstance(item.get('object'), str):
            key = (item['object'], item.get('sample_id'), item.get('input_index'))
            effect_states.setdefault(key, []).append(item.get('active'))
    if logging:
        diagnostic_finish(runtime, 'diagnostic.preprocess.indexes', detail_started,
                          inputs=len(identity_rows), effect_observations=len(collections.get('effect_observations', ())))
        diagnostic_finish(runtime, 'diagnostic.preprocess', phase_started, inputs=len(inputs),
                          action_observations=len(collections.get('action_observations', ())),
                          effect_observations=len(collections.get('effect_observations', ())))
        phase_started = diagnostic_start()
    states = configuration['states']
    bindings = initialization['bindings']
    state_order = list(dict.fromkeys(binding['state'] for binding in bindings))
    if (set(state_order) != {name for name, state in states.items() if state['priority']}
            or any([{key: value for key, value in binding.items() if key != 'state'}
                    for binding in bindings if binding['state'] == name] != states[name]['priority']
                   for name in state_order)):
        raise ValueError('冻结状态与有序规则绑定不一致')
    for state_name in state_order:
        state = states[state_name]
        if logging:
            detail_started = diagnostic_start()
        state_inputs, unknown_inputs = set(), []
        for row in identity_rows:
            identity = (row['sample_id'], row['input_index'])
            if state['effect'] is None:
                active = True
            else:
                matches = effect_states.get((state['effect'], *identity), [])
                active = matches[0] == state['expected'] if len(matches) == 1 and type(matches[0]) is bool else UNKNOWN
            if active is True: state_inputs.add(identity)
            elif active is UNKNOWN: unknown_inputs.append(row['input_index'])
        state_identity_rows = [row for row in identity_rows if (row['sample_id'], row['input_index']) in state_inputs]
        prior_prefix = _PriorTriggerPrefix(state_identity_rows)
        if logging:
            diagnostic_finish(runtime, 'diagnostic.state.' + state_name, detail_started,
                              inputs=len(identity_rows), known_inputs=len(state_inputs), unknown_inputs=len(unknown_inputs))
        for binding in state['priority']:
            if logging:
                binding_started = diagnostic_start()
                label = 'diagnostic.binding.' + json.dumps(
                    [state_name, binding['name'], binding['template']], ensure_ascii=False, separators=(',', ':'))
            triggers = UNKNOWN
            template = snapshot['pack']['general']['templates'][binding['template']]
            bounds = dict(start=payload.get('scope', {}).get('start_ms'), end=payload.get('scope', {}).get('end_ms'),
                          controlled_actor_index=payload.get('scope', {}).get('controlled_actor_index', UNKNOWN)) if payload else {}
            evaluator = Evaluation(objects, binding['arguments'], gaps, check, range_contains, bounds)
            if logging:
                evaluator.index_statistics = dict(index_queries=0, index_builds=0,
                                                  index_build_rows=0, index_matched_rows=0)
            env, prior_views = {}, {}
            rule = dict(name=binding['name'], state=state_name, template=binding['template'], findings=[], unknown_conditions=[])
            try:
                check()
                if payload_error: raise Unsupported(payload_error)
                if not state_inputs:
                    rule.update(status='unknown' if unknown_inputs else 'not_applicable',
                                state_unknown_inputs=unknown_inputs)
                    results.append(rule)
                    if logging:
                        diagnostic_finish(runtime, label + '.total', binding_started,
                                          inputs=0, **evaluator.index_statistics)
                    continue
                for read_index, read in enumerate(template['reads']):
                    if logging:
                        read_started = diagnostic_start()
                        read_label = label + '.read.' + str(read_index) + '.' + read['as']
                        scan_rows = 0
                    ref = evaluator.value(read['object'], env)
                    source = read['from']
                    if source == 'candidate.structure': rows = structures
                    elif source == 'candidate.expanded_position_map': rows = position_map
                    elif source == 'student.observation_bounds':
                        env[read['as']] = {key: bounds.get(key, UNKNOWN) for key in read['fields']}
                        if logging:
                            diagnostic_finish(runtime, read_label + '.select', read_started,
                                              source_scan_rows=0, rows=1, fields=len(read['fields']))
                        continue
                    elif source == 'frozen.inputs':
                        if batch_request is None: raise Unsupported('同次批次冻结输入缺失')
                        if objects[ref].get('value') != 'frozen_actual_burst_input_start':
                            raise Unsupported('未支持的冻结输入对象')
                        times, burst = batch_request.get('times'), batch_request.get('burst')
                        if burst is None: rows = []
                        elif (not isinstance(times, list) or not isinstance(burst.get('sources'), list)
                              or len(times) != len(burst['sources'])):
                            raise Unsupported('同次批次冻结爆发输入身份无效')
                        else:
                            sources = burst['sources']
                            if logging:
                                scan_rows = len(times)
                            rows = [dict(time=at) for index, (at, source_name) in enumerate(zip(times, sources))
                                    if source_name == 'burst' and (index == 0 or sources[index-1] != 'burst')]
                    elif source == 'execution.policy_evidence':
                        if objects[ref].get('value') != 'effective_execution_constraints' or batch_request is None:
                            raise Unsupported('同次有效执行约束缺失或未支持')
                        # 当前冻结执行协议只有独立爆发暂停/保护，没有隐含资源预留。
                        rows = [dict(row, protected=row.get('input_source') == 'burst', reserved=False)
                                for row in state_identity_rows]
                        if logging:
                            scan_rows = len(state_identity_rows)
                    elif source == 'evaluation.prior_rule_trigger_records':
                        if logging:
                            scan_rows = len(prior)
                        rows = [row for row in prior if row['rule_name'] in ref and row['state'] == state_name]
                    elif ref is None: rows = state_identity_rows
                    elif source.startswith('student.'):
                        if source[8:] not in collections:
                            env[read['as']] = UNKNOWN
                            if logging:
                                diagnostic_finish(runtime, read_label + '.select', read_started,
                                                  source_scan_rows=0, rows=0, unknown=1)
                            continue
                        if logging:
                            scan_rows = len(collections[source[8:]])
                        rows = [dict(row, run_id=task_run_id, batch_key=batch_key) for row in collections.get(source[8:], [])
                                if row.get('object') in (ref if isinstance(ref, list) else [ref]) and (
                                    'input_index' not in row or (row.get('sample_id'), row['input_index']) in state_inputs)]
                        if source == 'student.effect_events':
                            coverage = payload['scope'].get('effect_events_complete', {})
                            if not isinstance(coverage, dict): raise Unsupported('逐对象效果观察覆盖元数据无效')
                            rows = Rows(rows, [dict(object=name, run_id=task_run_id, batch_key=batch_key,
                                sample_id=payload['scope']['sample_id'], lifecycle_complete=False, coverage_unknown=True)
                                for name in (ref if isinstance(ref, list) else [ref])
                                if coverage.get(name) is not True])
                        # 未观察的事实保留身份行，字段缺失由表达式逐项传播未知。
                        if 'input_index' in read['fields'] and source != 'student.target_scope':
                            observed = {(row['sample_id'], row['input_index']) for row in rows}
                            rows += [row for row in state_identity_rows if (row['sample_id'], row['input_index']) not in observed]
                    else: raise Unsupported('同次读取尚未接通: ' + source)
                    if logging:
                        diagnostic_finish(runtime, read_label + '.select', read_started,
                            source_scan_rows=scan_rows, rows=len(rows),
                            uncertain_rows=len(getattr(rows, 'uncertain', ())), fields=len(read['fields']))
                        project_started = diagnostic_start()
                    # 协议完整性与同次身份始终保留；业务事实仍只按模板声明读取。
                    metadata = {'object', 'run_id', 'batch_key', 'sample_id', 'input_index', 'event_index',
                                'lifecycle_complete', 'coverage_unknown'}
                    def project(row):
                        row = dict(row['value'], **row) if isinstance(row.get('value'), dict) else row
                        return {key: value for key, value in row.items() if key in metadata or key in read['fields']}
                    env[read['as']] = Rows(map(project, rows), map(project, getattr(rows, 'uncertain', [])))
                    if logging:
                        diagnostic_finish(runtime, read_label + '.project', project_started,
                            rows=len(rows), uncertain_rows=len(getattr(rows, 'uncertain', ())),
                            fields=len(read['fields']))
                    if source == 'evaluation.prior_rule_trigger_records':
                        prior_views[read['as']] = env[read['as']]
                if logging:
                    detail_started = diagnostic_start()
                if binding['template'] not in trigger_specs:
                    trigger_specs[binding['template']] = _prior_queries(template)
                evaluator.prior_queries = prior_prefix.queries(trigger_specs[binding['template']], evaluator, prior_views, env)
                if logging:
                    diagnostic_finish(runtime, label + '.prefix_prepare', detail_started)
                    evaluator.lets(template['diagnose']['let'], env, diagnostic=(runtime, label))
                    detail_started = diagnostic_start()
                else:
                    evaluator.lets(template['diagnose']['let'], env)
                contexts = evaluator.value(template['diagnose']['for_each'], env)
                if logging:
                    diagnostic_finish(runtime, label + '.contexts', detail_started,
                        rows=len(contexts) if isinstance(contexts, list) else 0,
                        uncertain_rows=len(getattr(contexts, 'uncertain', ())), unknown=int(contexts is UNKNOWN))
                    detail_started = diagnostic_start()
                if contexts is UNKNOWN: raise Unsupported('规则必要事实未知')
                for context in getattr(contexts, 'uncertain', []):
                    rule['unknown_conditions'].append(dict(case='uncertain_context',
                        input_index=context.get('input_index') if isinstance(context, dict) else None))
                for context in contexts:
                    local = dict(env, **{template['diagnose']['as']: context})
                    for case in template['diagnose']['cases']:
                        condition = evaluator.value(case['when'], local)
                        if condition is UNKNOWN:
                            rule['unknown_conditions'].append(dict(case=case['kind'],
                                input_index=context.get('input_index') if isinstance(context, dict) else None))
                        if condition is True:
                            finding = dict(kind=case['kind'], certainty=case['certainty'],
                                           **evaluator.value(case.get('evidence', {}), local))
                            rule['findings'].append(finding)
                            local['finding'] = finding
                            for edit in template['edits']:
                                try:
                                    if evaluator.value(edit['when'], local) is not True: continue
                                    ranges = [objects[binding['arguments'][name]] for name, parameter in template['parameters'].items()
                                              if parameter['type'] == 'range_ref']
                                    if any(edit['unit'] not in row['allow_units'] for row in ranges):
                                        reject('edit_unit_not_allowed')
                                        continue
                                    sources = evaluator.value(edit['source'], local)
                                except Unsupported as error:
                                    reject_edit(rule, edit, finding, error)
                                    continue
                                # block产生一个有限源集合；map(block)保留其集合嵌套。
                                sources = [item for row in sources for item in (row if isinstance(row, list) else [row])]
                                for source in sources:
                                    try:
                                        if source['source_position'] is not None and any(
                                                not range_contains(binding['arguments'][name], source['source_position'])
                                                for name, parameter in template['parameters'].items() if parameter['type'] == 'range_ref'):
                                            reject('source_outside_edit_range')
                                            continue
                                        edit_env = dict(local, source=source)
                                        destinations = (evaluator.value(edit['destination'], edit_env) if 'destination' in edit
                                                        else [dict(source_position=source['source_position'])])
                                        count = evaluator.value(edit['count'], edit_env)
                                    except Unsupported as error:
                                        reject_edit(rule, edit, finding, error, source)
                                        continue
                                    for destination in destinations:
                                        check()
                                        operation = dict(operation=edit['operation'], unit=edit['unit'],
                                            source_path=source['source_position'], destination_path=destination['source_position'],
                                            block=source['actions'], count=count)
                                        operation_key = digest(operation)
                                        contributor = dict(rule=binding['name'], state=state_name,
                                            certainty=finding['certainty'], evidence=_public(finding))
                                        if operation_key in by_operation:
                                            by_operation[operation_key]['contributors'].append(contributor)
                                            continue
                                        if operation_key in rejected_operations:
                                            reject(rejected_operations[operation_key])
                                            continue
                                        try:
                                            changed = apply(program, operation)
                                            canonical = canonicalize_search_program(changed, capabilities)
                                        except ValueError:
                                            rejected_operations[operation_key] = 'existing_program_legality'
                                            reject('existing_program_legality')
                                            continue
                                        if canonical['identity'] in behavior_seen:
                                            rejected_operations[operation_key] = 'same_behavior'
                                            reject('same_behavior')
                                            continue
                                        behavior_seen.add(canonical['identity'])
                                        operation.update(operation_id=digest(dict(parent_identity=parent_identity, operation=operation)),
                                            contributors=[contributor], resulting_behavior_identity=canonical['identity'])
                                        by_operation[operation_key] = operation
                                        operations.append(operation)
                if logging:
                    diagnostic_finish(runtime, label + '.cases_edits', detail_started,
                                      findings=len(rule['findings']), unknown_conditions=len(rule['unknown_conditions']))
                    detail_started = diagnostic_start()
                triggers = evaluator.value(template['diagnose']['export_trigger_records'], env)
                if triggers is not UNKNOWN:
                    prior.extend(dict(row, rule_name=binding['name'], state=state_name) for row in triggers)
                rule['status'] = ('diagnosed' if rule['findings'] else
                                  'unknown' if rule['unknown_conditions'] or evaluator.unknown_evidence else 'not_applicable')
                rule['state_unknown_inputs'] = unknown_inputs
                rule['unknown_evidence'] = evaluator.unknown_evidence
                if logging:
                    diagnostic_finish(runtime, label + '.export_triggers', detail_started,
                        rows=len(triggers) if isinstance(triggers, list) else 0, unknown=int(triggers is UNKNOWN))
            except Unsupported as error:
                rule.update(status='unknown', reason=str(error))
            except Stopped as error:
                rule.update(status='unknown', reason=str(error))
            if incomplete_reason is None:
                if logging:
                    detail_started = diagnostic_start()
                try:
                    prior_prefix.advance(binding['name'], triggers, check)
                except Stopped as error:
                    rule.update(status='unknown', reason=str(error))
                finally:
                    if logging:
                        diagnostic_finish(runtime, label + '.prefix_advance', detail_started)
            results.append(_public(rule))
            if logging:
                diagnostic_finish(runtime, label + '.total', binding_started,
                                  inputs=len(state_inputs), **evaluator.index_statistics)
    if logging:
        diagnostic_finish(runtime, 'diagnostic.rules', phase_started, rules=len(results),
                          operations=len(operations))
        phase_started = diagnostic_start()
    result = dict(version=VERSION, parent_identity=parent_identity, parent=parent, evidence=evidence,
        observation_scope=observation_scope, rules=results,
        facts=dict(source=dict(batch_key=batch_key, report_field='sim.players.sim2gse_rule_observations'),
                   collection_counts={name: len(rows) for name, rows in collections.items()},
                   qualification_events_promoted_to_input_state=False),
        pool=dict(complete=incomplete_reason is None, incomplete_reason=incomplete_reason, operations=operations,
                  empty_reason=('no_supported_legal_operation' if not operations and incomplete_reason is None else None),
                  rejections=rejections))
    if logging:
        diagnostic_finish(runtime, 'diagnostic.finalize', phase_started, rules=len(results),
                          operations=len(operations))
        finished = diagnostic_start()
        result['costs'] = dict(diagnose_and_pool_seconds=(max(0.0, finished-started)
            if finished is not None and started is not None else None))
        diagnostic_finish(runtime, 'diagnostic.total', started)
    return result
