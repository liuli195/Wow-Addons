"""两个逻辑规则库的单包读取；所有任务使用已校验快照。"""
import copy
import json
import math
import os
import threading
from pathlib import Path

from search import digest

DEFAULT_PATH = Path(__file__).with_name('rules.json')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSON对象键重复: ' + key)
        result[key] = value
    return result


def load(path=None):
    path = Path(path) if path is not None else Path(os.environ.get('SIM2GSE_RULE_CONFIG', DEFAULT_PATH))
    try:
        with path.open('rb') as handle:
            raw = handle.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('超过1MiB配置上限')
        pack = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
        resolved = validate(pack)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        raise ValueError(f'规则配置 {path}: {error}') from error
    return dict(pack=pack, resolved=resolved, rule_config_digest=digest(pack), source=str(path.resolve()),
                schema_version=1, executor_version='configured-opener-v2')


_SAVE_LOCK = threading.Lock()


def save(draft, expected_digest):
    from task import _task_lease, _write_json
    snapshot = load(draft)
    target = Path(os.environ.get('SIM2GSE_RULE_CONFIG', DEFAULT_PATH))
    with _SAVE_LOCK, _task_lease(target.parent, lock_name=target.name + '.lock',
                               conflict_message='规则配置正由其他写者保存，请重试'):
        current = load(target)
        if current['rule_config_digest'] != expected_digest:
            raise ValueError('规则配置摘要冲突：当前版本已变化，请重新读取后保存')
        _write_json(target, snapshot['pack'], atomic=True)
    return dict(status='saved', rule_config_digest=snapshot['rule_config_digest'], source=str(target.resolve()))


UNKNOWN = None


def evaluate(expression, facts):
    """有限数据操作；None是unknown，不执行字符串或职业回调。"""
    if not isinstance(expression, dict):
        return expression
    if len(expression) != 1:
        raise ValueError('规则配置表达式必须恰有一个操作')
    operation, args = next(iter(expression.items()))
    if operation == 'fact':
        return facts.get(args)
    if operation == 'unknown':
        return UNKNOWN
    if operation == 'select':
        for row in args:
            if evaluate(row['when'], facts) is True:
                return evaluate(row['value'], facts)
        return UNKNOWN
    if operation == 'not':
        value = evaluate(args, facts)
        return None if value is None else not value
    values = [evaluate(arg, facts) for arg in args]
    if operation in ('and', 'or'):
        decisive = operation == 'or'
        if any(value is decisive for value in values):
            return decisive
        return None if None in values else not decisive
    if None in values:
        return None
    from operator import eq, ne, lt, le, gt, ge, add, sub, mul, truediv
    operations = dict(eq=eq, ne=ne, lt=lt, lte=le, gt=gt, gte=ge,
                      add=add, subtract=sub, multiply=mul, divide=truediv,
                      min=min, max=max)
    if operation not in operations:
        raise ValueError('规则配置不支持的操作: ' + operation)
    try:
        return operations[operation](*values)
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError('规则配置操作错误: ' + operation) from error


def facts_for(spec, capabilities, snapshot, target_count, *, balances=None, capacities=None, scene=None):
    values = {}
    available = {row['simc_action'] for row in capabilities['actions']}
    for alias, row in spec['facts'].items():
        source = row['from']
        if source == 'scenario.scene':
            value = scene
        elif source == 'scenario.target_count':
            value = target_count
        elif source == 'capability.available':
            value = spec['actions'][row['action']]['button'] in available
        elif source == 'static.parameter':
            value = snapshot.get('parameters', {}).get(row['key'])
        elif source == 'static.hero_subtree':
            trees = snapshot.get('hero_subtree_ids')
            if trees is not None and (not isinstance(trees, list) or
                    any(type(identity) is not int or identity <= 0 for identity in trees)):
                raise ValueError('原生英雄子树事实无效')
            value = None if trees is None else row['id'] in trees
        elif source in ('static.resource.current', 'static.resource.maximum'):
            value = snapshot.get('resources', {}).get(row['resource'], {}).get(source.rsplit('.', 1)[1])
        elif source in ('estimate.resource.current', 'estimate.resource.deficit'):
            key = row['resource']
            current = (balances or {}).get(key)
            maximum = (capacities or {}).get(key)
            value = (current if source.endswith('.current') else
                     maximum-current if current is not None and maximum is not None else None)
        elif source == 'student.apl_fact':
            value = None  # 02仅有引用契约，01没有同次学生证据。
        else:
            raise ValueError('规则配置未登记事实来源: ' + source)
        if value is not None:
            kind = row['type']
            valid = (type(value) is bool if kind == 'boolean' else
                     isinstance(value, str) if kind == 'string' else type(value) in (int, float) and math.isfinite(value) and
                     (kind != 'integer' or value == int(value)))
            if not valid or kind not in ('boolean', 'string') and value < row.get('minimum', -math.inf):
                raise ValueError('规则配置事实类型或范围不符: ' + alias)
        values[alias] = value
    return values


def bind(capabilities, snapshot, target_count, *, spec_id, rule_snapshot, scene=None):
    """选择唯一有序起手；动态优先级声明保留给02，不在静态绑定时删除。"""
    if not isinstance(snapshot, dict):
        raise ValueError('规则起点缺少真实角色静态快照，请重新构建引擎')
    spec = rule_snapshot['resolved'].get(str(spec_id))
    if spec is None:
        raise ValueError('当前专精尚无已审核的规则起点绑定')
    values = facts_for(spec, capabilities, snapshot, target_count, scene=scene)
    policy = spec['initialization']
    for key in policy.get('required_facts', []):
        if values.get(key) is None:
            raise ValueError('规则起点缺少静态字段: ' + key)
    matched = [row for row in policy['openers'] if evaluate(row['scope'], values) is True]
    if len(matched) != 1:
        raise ValueError('规则起点需要唯一适用起手分支；当前匹配数: ' + str(len(matched)))
    return dict(resource=policy['resource'],
        recovery={key: evaluate(value, values) for key, value in policy['recovery'].items()},
        opener=copy.deepcopy(matched[0]), bindings=[dict(copy.deepcopy(row),
            scope_status=evaluate(row['scope'], values)) for row in spec['bindings']],
        parameter_sources={key: row for key, row in spec['facts'].items()
                           if row['from'].startswith('static.')},
        approximate=policy.get('approximate', []), unknown=policy.get('unknown', []),
        native_buttons={name: row['button'] for row in spec['actions'].values()
                        for name in [row['native_action'], *row.get('variants', [])]},
        spec=spec, facts=values)


_CONTEXT = {
    'interval.attempt_count': {'02', '03'},
    'finding.source_position': {'02', '03'},
    'finding.opportunity_position': {'02', '03'},
}
_BINARY = {'eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'add', 'subtract', 'multiply', 'divide', 'min', 'max'}


def _expression(value, facts, parameters=(), *, depth=0, phase=None):
    import math
    if depth > 24:
        raise ValueError('表达式超过24层')
    if isinstance(value, dict):
        if len(value) != 1:
            raise ValueError('表达式需要恰好一个操作')
        operation, args = next(iter(value.items()))
        if operation == 'fact':
            if args not in facts and args not in _CONTEXT:
                raise ValueError('未声明事实: ' + str(args))
            if phase is not None:
                source = facts.get(args, {}).get('from', '')
                if (args in _CONTEXT and phase not in _CONTEXT[args]
                        or source == 'student.apl_fact' and phase not in ('02', '03')
                        or source.startswith('estimate.') and phase not in ('plan', 'candidate')):
                    raise ValueError('事实不属于当前求值阶段: ' + str(args))
            return
        if operation == 'param':
            if args not in parameters:
                raise ValueError('未声明参数: ' + str(args))
            return
        if operation == 'unknown':
            if not isinstance(args, str) or not args:
                raise ValueError('unknown需要原因')
            return
        if operation == 'not':
            children = [args]
        elif operation == 'select':
            if not isinstance(args, list) or not 1 <= len(args) <= 16:
                raise ValueError('条件取值需要有界分支')
            children = []
            for row in args:
                if not isinstance(row, dict) or set(row) != {'when', 'value'}:
                    raise ValueError('条件取值需要when/value')
                children.extend(row.values())
        elif operation in _BINARY or operation in ('and', 'or'):
            if not isinstance(args, list) or (len(args) != 2 if operation in _BINARY else not 1 <= len(args) <= 32):
                raise ValueError('操作参数数量无效: ' + operation)
            if operation == 'divide' and args[1] == 0:
                raise ValueError('规则配置除零')
            children = args
        else:
            raise ValueError('未知操作: ' + operation)
        for child in children:
            _expression(child, facts, parameters, depth=depth+1, phase=phase)
    elif not (value is None or type(value) in (str, bool, int, float)):
        raise ValueError('不支持表达式值')
    elif type(value) in (int, float) and not math.isfinite(value):
        raise ValueError('非有限数值')


def _typed(value, facts, expected=None, parameters=None):
    """启动时核对有限比较/算术的类型与量纲；不作隐式布尔转数字。"""
    if isinstance(value, dict):
        operation, args = next(iter(value.items()))
        if operation == 'fact':
            row = facts.get(args, {'type': 'number', 'unit': 'count'})
            kind, unit = row['type'], row.get('unit')
            result = ('number' if kind == 'integer' else kind, unit)
        elif operation == 'param':
            kind = parameters[args]
            result = ({'action_ref': 'string', 'predicate': 'boolean', 'integer': 'number'}.get(kind, kind), None)
        elif operation == 'unknown':
            result = ('unknown', None)
        elif operation == 'select':
            results = []
            for row in args:
                _typed(row['when'], facts, 'boolean', parameters)
                results.append(_typed(row['value'], facts, parameters=parameters))
            result = next((item for item in results if item[0] != 'unknown'), ('unknown', None))
            for item in results:
                if item[0] not in ('unknown', result[0]) or item[1] and result[1] and item[1] != result[1]:
                    raise ValueError('条件取值类型或单位冲突')
        elif operation in ('not', 'and', 'or'):
            for child in ([args] if operation == 'not' else args):
                _typed(child, facts, 'boolean', parameters)
            result = ('boolean', None)
        else:
            left, right = [_typed(child, facts, parameters=parameters) for child in args]
            kinds = {item[0] for item in (left, right)} - {'unknown'}
            numeric = operation not in ('eq', 'ne')
            if len(kinds) > 1 or numeric and kinds - {'number'}:
                raise ValueError('表达式类型冲突: ' + operation)
            units = {item[1] for item in (left, right) if item[1]}
            if operation in ('multiply', 'divide'):
                units -= {'count', 'ratio'}
            if len(units) > 1:
                raise ValueError('表达式单位冲突: ' + operation)
            result = ('boolean', None) if operation in ('eq', 'ne', 'lt', 'lte', 'gt', 'gte') else ('number', next(iter(units), None))
    else:
        result = ('unknown' if value is None else 'boolean' if type(value) is bool else
                  'number' if type(value) in (int, float) else 'string', None)
    if expected is not None and result[0] not in ('unknown', expected):
        raise ValueError('表达式结果类型应为' + expected)
    return result


def _check(value, facts, phase, expected=None, unit=None, *, parameters=None):
    _expression(value, facts, parameters or {}, phase=phase)
    kind, actual_unit = _typed(value, facts, expected, parameters)
    if kind != 'unknown' and unit and actual_unit and unit != actual_unit:
        raise ValueError('表达式结果单位应为' + unit)


def _check_stage_contract(contract, facts, actions=None, parameters=None):
    diagnose = contract.get('diagnose', {})
    if 'when' in diagnose:
        _check(diagnose['when'], facts, '02', 'boolean', parameters=parameters)
    if 'action' in diagnose:
        _check(diagnose['action'], facts, '02', 'string', parameters=parameters)
        if actions is not None and diagnose['action'] not in actions:
            raise ValueError('诊断动作引用失效')
    for key, value in diagnose.items():
        if key not in ('when', 'action') and isinstance(value, dict):
            _check(value, facts, '02', parameters=parameters)
    for edit in contract.get('edits', []):
        for key, value in edit.items():
            if key == 'when' or isinstance(value, dict):
                _check(value, facts, '02', 'boolean' if key == 'when' else None, parameters=parameters)
    for feature in contract.get('features', []):
        _check(feature['value'], facts, '03', 'number', parameters=parameters)


def _substitute(value, arguments):
    if isinstance(value, dict):
        if set(value) == {'param'}:
            if value['param'] not in arguments:
                raise ValueError('缺少模板参数: ' + str(value['param']))
            return copy.deepcopy(arguments[value['param']])
        return {key: _substitute(item, arguments) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, arguments) for item in value]
    return value


def _expand_binding(row, templates, actions, facts):
    if {'initialize', 'extra_initializations', 'overrides'} & row.keys():
        raise ValueError('旧初始化执行字段已取消，请使用initialization.openers')
    arguments = row.get('arguments', {})
    result = _substitute(row, arguments)
    contracts, binding_defaults = [], {}
    for identity in row['rules']:
        template = templates[identity]
        for name, kind in template.get('parameters', {}).items():
            if name not in arguments:
                raise ValueError('缺少模板参数: ' + name)
            value = arguments[name]
            if kind == 'action_ref':
                if value not in actions:
                    raise ValueError('模板动作引用失效: ' + str(value))
            elif kind == 'predicate':
                _expression(value, facts)
                _typed(value, facts, 'boolean')
            elif kind in ('integer', 'number', 'string', 'boolean'):
                expected = 'number' if kind == 'integer' else kind
                _typed(value, facts, expected)
                if kind == 'integer' and type(value) is not int:
                    raise ValueError('模板整数参数无效: ' + name)
            else:
                raise ValueError('未支持模板参数类型: ' + str(kind))
        expanded = _substitute(template, arguments)
        for field, value in expanded.get('binding', {}).items():
            if field in binding_defaults and binding_defaults[field] != value and field not in row:
                raise ValueError('共享定义字段冲突: ' + field)
            binding_defaults[field] = value
        contracts.append(dict(template=identity, **{key: expanded[key] for key in
            ('diagnose', 'edits', 'features') if key in expanded}))
    result = dict(binding_defaults, **result)
    result['stage_contracts'] = contracts  # 02/03只保存并校验，不在01执行。
    return result


def _validate_templates(templates, facts, actions=None):
    for key, row in templates.items():
        if not isinstance(key, str) or not key or not isinstance(row, dict):
            raise ValueError('模板身份无效')
        if {'initialize', 'extra_initializations', 'overrides'} & row.keys():
            raise ValueError('旧初始化执行字段已取消，请使用initialization.openers')
        for field in ('intent', 'scope', 'modifications'):
            if not isinstance(row.get(field), str):
                raise ValueError('模板缺少说明: ' + key)
        if row.get('unknown') not in ('error', 'record_not_applied', 'attempt_with_report'):
            raise ValueError('unknown策略无效')
        parameters = row.get('parameters', {})
        if any(kind not in ('action_ref', 'predicate', 'integer', 'number', 'string', 'boolean')
               for kind in parameters.values()):
            raise ValueError('未支持模板参数类型')
        for edit in row.get('edits', []):
            if edit.get('operation') not in ('move', 'insert', 'remove', 'reduce_wait'):
                raise ValueError('非法候选操作')
        _check_stage_contract(row, facts, parameters=parameters)
        shared = row.get('binding', {})
        if not isinstance(shared, dict):
            raise ValueError('共享定义字段必须是对象')
        if {'initialize', 'extra_initializations', 'overrides'} & shared.keys():
            raise ValueError('旧初始化执行字段已取消，请使用initialization.openers')
        if actions is not None and 'action' in shared and shared['action'] not in actions:
            raise ValueError('共享定义动作引用失效: ' + key)
        for field in ('scope', 'condition'):
            if field in shared:
                _check(shared[field], facts, '02', 'boolean', parameters=parameters)


def validate(pack):
    """启动时一次校验两库与引用；失败不能替换有效文件。"""
    if (not isinstance(pack, dict) or type(pack.get('schema_version')) is not int
            or pack['schema_version'] != 1 or not isinstance(pack.get('general'), dict)
            or not isinstance(pack.get('specializations'), dict)):
        raise ValueError('schema_version/general/specializations无效')
    general = pack['general']
    if 'initialization' in general:
        raise ValueError('旧通用初始化骨架已取消，请使用专精initialization.openers')
    templates = general.get('templates')
    if not isinstance(templates, dict) or not 0 <= len(templates) <= 128:
        raise ValueError('通用模板数量无效')
    _validate_templates(templates, {})
    resolved = copy.deepcopy(pack['specializations'])
    for spec_id, spec in resolved.items():
        if not isinstance(spec_id, str) or not spec_id or not isinstance(spec, dict):
            raise ValueError('专精身份无效')
        actions, facts, bindings = spec['actions'], spec['facts'], spec['bindings']
        if not isinstance(bindings, list) or not 0 <= len(bindings) <= 512 or len(facts) > 512:
            raise ValueError('专精条目或事实数量无效')
        for alias, action in actions.items():
            if (not isinstance(alias, str) or not alias or
                    not all(isinstance(action.get(k), str) and action[k] for k in ('button', 'native_action'))):
                raise ValueError('动作映射无效')
            variants = action.get('variants', [])
            if not isinstance(variants, list) or any(not isinstance(item, str) or not item for item in variants):
                raise ValueError('动作替换映射无效')
        native_targets = {}
        for action in actions.values():
            for name in [action['native_action'], *action.get('variants', [])]:
                if native_targets.setdefault(name, action['button']) != action['button']:
                    raise ValueError('同一原生动作映射多个按钮: ' + name)
        policy = spec['initialization']
        if 'funding' in policy:
            raise ValueError('旧初始化供资字段已取消，请使用initialization.openers')
        recovery = policy['recovery']
        if recovery.get('model') not in ('none', 'parallel_discrete'):
            raise ValueError('未支持的恢复模型')
        fields = {'model': ('string', None)}
        if recovery['model'] == 'parallel_discrete':
            fields.update(resource=('string', None), interval_ms=('number', 'ms'), slots=('number', 'count'))
        if set(recovery) != set(fields):
            raise ValueError('恢复模型字段不完整或未支持')
        for key, (kind, unit) in fields.items():
            _check(recovery[key], facts, 'bind', kind, unit)
        if any(name not in facts for name in policy.get('required_facts', [])):
            raise ValueError('必需事实引用失效')
        for alias, fact in facts.items():
            if alias in _CONTEXT:
                raise ValueError('事实身份与保留上下文冲突: ' + alias)
            if fact.get('type') not in ('boolean', 'integer', 'number', 'string'):
                raise ValueError('事实类型无效: ' + alias)
            if fact.get('from') not in ('scenario.scene', 'scenario.target_count', 'capability.available', 'static.parameter', 'static.hero_subtree',
                                       'estimate.resource.current', 'estimate.resource.deficit', 'static.resource.current', 'static.resource.maximum', 'student.apl_fact'):
                raise ValueError('事实来源未登记: ' + alias)
            if fact['from'] == 'static.hero_subtree' and (fact['type'] != 'boolean'
                    or type(fact.get('id')) is not int or fact['id'] <= 0):
                raise ValueError('英雄子树事实类型或ID无效: ' + alias)
            if fact['from'] == 'capability.available' and fact.get('action') not in actions:
                raise ValueError('事实引用不存在动作: ' + alias)
            if fact['from'] == 'student.apl_fact' and fact.get('phase') != '02':
                raise ValueError('学生事实仅02可求值')
        for name in policy.get('required_facts', []):
            _check({'fact': name}, facts, 'bind')
        openers = policy.get('openers')
        if not isinstance(openers, list) or not 1 <= len(openers) <= 32:
            raise ValueError('初始化需要有界有序起手列表')
        opener_ids = set()
        for opener in openers:
            if not isinstance(opener.get('id'), str) or not opener['id'] or opener['id'] in opener_ids:
                raise ValueError('起手身份缺失或重复')
            opener_ids.add(opener['id'])
            if not isinstance(opener.get('source'), str) or not opener['source']:
                raise ValueError('起手缺少来源')
            _check(opener['scope'], facts, 'bind', 'boolean')
            steps = opener.get('steps')
            if not isinstance(steps, list) or not 1 <= len(steps) <= 128:
                raise ValueError('有序起手必须有1至128个步骤')
            for step in steps:
                if step.get('action') not in actions:
                    raise ValueError('起手动作引用失效')
                if type(step.get('source_step')) is not int or step['source_step'] < 1:
                    raise ValueError('起手来源步骤无效')
                if step.get('mapping', 'loop') not in ('loop', 'burst'):
                    raise ValueError('起手映射方式无效')
                if 'commands' in step:
                    commands = step['commands']
                    if (step.get('mapping') != 'burst' or not isinstance(commands, list)
                            or not 1 <= len(commands) <= 16):
                        raise ValueError('独立爆发来源多命令块无效')
                    for command in commands:
                        if not isinstance(command, dict) or command.get('action') not in actions:
                            raise ValueError('开场或来源命令动作引用失效')
                        if command.get('condition') is not None:
                            raise ValueError('来源爆发命令不支持额外条件')
                if 'native_form' in step and step['native_form'] not in [
                        actions[step['action']]['native_action'], *actions[step['action']].get('variants', [])]:
                    raise ValueError('起手替换形态引用失效')
            if 'first_burst_step' in opener and opener['first_burst_step'] not in [row['source_step'] for row in steps]:
                raise ValueError('首次爆发来源步骤无效')
        local_templates = spec.get('templates', {})
        if not isinstance(local_templates, dict) or len(local_templates) > 128 or set(local_templates) & set(templates):
            raise ValueError('专精共享定义无效或与通用模板冲突')
        _validate_templates(local_templates, facts, actions)
        available_templates = dict(templates, **local_templates)
        for row in bindings:
            if any(key not in available_templates for key in row['rules']):
                raise ValueError('模板引用失效: ' + row['id'])
        bindings[:] = [_expand_binding(row, available_templates, actions, facts) for row in bindings]
        ids = [row['id'] for row in bindings]
        if len(set(ids)) != len(ids):
            raise ValueError('绑定ID重复')
        dependencies = {key: set() for key in ids}
        for row in bindings:
            if row.get('action') not in actions:
                raise ValueError('绑定动作引用失效: ' + row['id'])
            if any(key not in available_templates for key in row['rules']):
                raise ValueError('模板引用失效: ' + row['id'])
            for key in ('scope', 'condition'):
                _check(row[key], facts, '02', 'boolean')
            _check(row.get('priority', 0), facts, 'bind', 'number')
            _check(row.get('parent_condition', True), facts, '02', 'boolean')
            coverage = row.get('initialization_coverage', {})
            if 'upstream_applicable' in coverage:
                _check(coverage['upstream_applicable'], facts, 'bind', 'boolean')
            for contract in row['stage_contracts']:
                _check_stage_contract(contract, facts, actions)
            for relation in row.get('yields_to', []):
                if set(relation) != {'source_entries', 'when'} or any(
                        key not in ids and key not in spec.get('external_entries', {}) for key in relation['source_entries']):
                    raise ValueError('前序来源引用失效')
                _check(relation['when'], facts, '02', 'boolean')
            target = row.get('target', {'mode': 'current'})
            if target.get('mode') not in ('current', 'first', 'min', 'max') or (
                    target['mode'] != 'current' and target.get('fact') not in facts):
                raise ValueError('目标事实引用失效')
            if target['mode'] != 'current':
                _check({'fact': target['fact']}, facts, '02',
                       'boolean' if target['mode'] == 'first' else 'number')
            for field in ('before', 'after'):
                for other in row.get(field, []):
                    if other not in dependencies:
                        raise ValueError('顺序引用失效: ' + other)
                    left, right = (other, row['id']) if field == 'before' else (row['id'], other)
                    dependencies[left].add(right)
        remaining = set(ids)
        while remaining:
            ready = {key for key in remaining if not dependencies[key] & remaining}
            if not ready:
                raise ValueError('动作依赖存在环')
            remaining -= ready
    return resolved
