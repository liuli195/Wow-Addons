"""仅核验旧v1完整训练成果内嵌规则快照；不加载或编辑current规则。"""
import copy
import math
from search import digest


def _nonempty(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError('规则配置字符串无效: ' + label)
    return value


_OBJECT_KINDS = {'action', 'effect', 'state', 'resource', 'target_scope', 'source', 'plan', 'range', 'policy'}
_DECLARED_OPERATIONS = {
    'map', 'join', 'merge', 'record', 'any3', 'lookup_unique', 'and', 'not', 'select', 'eq',
    'compare', 'or', 'unknown', 'lte', 'gt', 'all3', 'entries', 'gte', 'lookup', 'is_number',
    'contains', 'filter', 'object_field', 'resolve_edit_gaps', 'block', 'adjacent', 'empty',
    'lt', 'last_true', 'is_true', 'interval_select', 'pair_intervals', 'join_interval',
    'first_true', 'matches_native_object', 'count', 'subtract', 'is_integer',
}


def _fields(value, required, optional=(), *, label):
    if not isinstance(value, dict) or set(required) - set(value) or set(value) - set(required) - set(optional):
        raise ValueError('规则声明字段缺失或未支持: ' + label)


def _template_declaration(value, parameters, depth=0):
    """仅检查有限语法和形参引用，绝不求值02表达式。"""
    if depth > 24:
        raise ValueError('模板表达式超过深度边界')
    if isinstance(value, dict):
        if 'arg' in value and (set(value) != {'arg'} or value['arg'] not in parameters):
            raise ValueError('模板形参引用失效')
        if 'var' in value:
            if set(value) != {'var'}:
                raise ValueError('模板变量声明无效')
            _nonempty(value['var'], 'var')
        if 'op' in value:
            if value['op'] not in _DECLARED_OPERATIONS or ('args' in value and not isinstance(value['args'], list)):
                raise ValueError('模板操作未登记或参数结构无效')
            depth += 1
        for child in value.values():
            _template_declaration(child, parameters, depth)
    elif isinstance(value, list):
        if len(value) > 4096:
            raise ValueError('模板声明数组超过边界')
        for child in value:
            _template_declaration(child, parameters, depth)
    elif type(value) is float and not math.isfinite(value):
        raise ValueError('模板声明必须使用有限数值')


def _argument(value, declaration, objects, prior_rules, label):
    kind = declaration['type']
    if value is None and declaration.get('nullable') is True:
        return
    if kind.endswith('_ref_array'):
        if (not isinstance(value, list) or len(value) > 512
                or any(not isinstance(item, str) for item in value) or len(set(value)) != len(value)):
            raise ValueError('模板数组参数无效: ' + label)
        for item in value:
            _argument(item, dict(type=kind.removesuffix('_array')), objects, prior_rules, label)
    elif kind.endswith('_ref'):
        if kind == 'rule_ref':
            valid = isinstance(value, str) and value in prior_rules
        else:
            target = objects.get(value) if isinstance(value, str) else None
            valid = isinstance(target, dict) and target.get('kind') == kind.removesuffix('_ref')
        if not valid:
            raise ValueError('模板对象参数引用失效或类型不符: ' + label)
    elif kind == 'enum':
        if not isinstance(value, str) or not value or value not in declaration['values']:
            raise ValueError('模板枚举参数无效: ' + label)
    elif kind in ('number', 'integer', 'number_or_boolean'):
        valid = (type(value) is bool and kind == 'number_or_boolean') or (
            type(value) in (int, float) and math.isfinite(value) and (kind != 'integer' or type(value) is int))
        if not valid or not declaration.get('minimum', -math.inf) <= value <= declaration.get('maximum', math.inf):
            raise ValueError('模板数值参数类型或范围无效: ' + label)
    elif kind == 'boolean':
        if type(value) is not bool:
            raise ValueError('模板布尔参数无效: ' + label)
    else:
        raise ValueError('未支持的模板参数类型: ' + str(kind))


def _object_declaration(row, entries, alias):
    """检查既有对象数据及同集合引用，不解释诊断或业务含义。"""
    if not isinstance(row, dict) or row.get('kind') not in _OBJECT_KINDS:
        raise ValueError('对象类型未登记: ' + alias)
    kind = row['kind']
    if kind == 'action':
        _fields(row, ('kind', 'native_action', 'base_button'), ('native_forms', 'label'), label=alias)
        _nonempty(row['native_action'], alias + '.native_action')
        _nonempty(row['base_button'], alias + '.base_button')
        if 'label' in row:
            _nonempty(row['label'], alias + '.label')
        forms = row.get('native_forms', [row['native_action']])
        if not isinstance(forms, list) or any(not isinstance(value, str) or not value for value in forms):
            raise ValueError('动作原生形态无效: ' + alias)
    elif kind == 'effect':
        _fields(row, ('kind',), ('native_identity', 'components', 'selector', 'from_action', 'qualification'), label=alias)
        if ('native_identity' in row) == ('components' in row):
            raise ValueError('效果必须唯一声明原生身份或组件: ' + alias)
        if 'native_identity' in row:
            _nonempty(row['native_identity'], alias + '.native_identity')
        else:
            components = row['components']
            if not isinstance(components, list) or not 1 <= len(components) <= 512:
                raise ValueError('效果组件列表无效: ' + alias)
            for component in components:
                _fields(component, ('native_identity', 'target_scope'), label=alias + '.component')
                _nonempty(component['native_identity'], alias + '.component.native_identity')
                _argument(component['target_scope'], dict(type='target_scope_ref'), entries, (), alias + '.target_scope')
        for field, target_kind in (('from_action', 'action_ref'), ('qualification', 'state_ref')):
            if field in row:
                _argument(row[field], dict(type=target_kind), entries, (), alias + '.' + field)
        if 'selector' in row:
            selector = row['selector']
            _fields(selector, ('slots', 'active_only'), label=alias + '.selector')
            if (not isinstance(selector['slots'], list) or len(selector['slots']) > 512
                    or any(type(value) is not int or value <= 0 for value in selector['slots'])
                    or type(selector['active_only']) is not bool):
                raise ValueError('效果选择对象字段类型无效: ' + alias)
    elif kind in ('state', 'resource'):
        _fields(row, ('kind', 'native_identity'), ('representation',) if kind == 'state' else (), label=alias)
        _nonempty(row['native_identity'], alias + '.native_identity')
        if 'representation' in row and (not isinstance(row['representation'], str)
                or row['representation'] not in ('boolean', 'positive_stack_presence')):
            raise ValueError('资格状态表示未登记: ' + alias)
    elif kind == 'range':
        _fields(row, ('kind', 'segments', 'allow_units', 'preserve_block_contents', 'respect_approved_protection'), label=alias)
        _nonempty(row['segments'], alias + '.segments')
        if (not isinstance(row['allow_units'], list) or not row['allow_units']
                or any(not isinstance(value, str) or not value for value in row['allow_units'])
                or type(row['preserve_block_contents']) is not bool or type(row['respect_approved_protection']) is not bool):
            raise ValueError('编辑范围字段类型无效: ' + alias)
    else:
        _fields(row, ('kind', 'value'), label=alias)
        _nonempty(row['value'], alias + '.value')


def validate(pack):
    """只校验新配置并解析引用；01不执行模板诊断或编辑。"""
    if not isinstance(pack, dict) or type(pack.get('schema_version')) is not int or pack['schema_version'] != 2:
        raise ValueError('schema_version必须为2；旧任务结果仅保留只读')
    _fields(pack, ('schema_version', 'identity_mappings', 'general', 'object_sets', 'configurations',
                   'execution_evidence'), label='runtime')
    _fields(pack['general'], ('templates',), label='general')
    _fields(pack['identity_mappings'], ('hero_talents',), label='identity_mappings')
    templates = pack['general']['templates']
    objects = pack['object_sets']
    heroes = pack['identity_mappings']['hero_talents']
    configurations = pack['configurations']
    executions = pack.get('execution_evidence', {})
    if (not isinstance(templates, dict) or len(templates) > 128 or not isinstance(objects, dict)
            or not isinstance(heroes, dict) or not isinstance(executions, dict)
            or not isinstance(configurations, list) or not 1 <= len(configurations) <= 512):
        raise ValueError('模板/对象/身份映射/配置列表无效')
    for name, native_id in heroes.items():
        _nonempty(name, 'hero_talent')
        if type(native_id) is not int or native_id <= 0:
            raise ValueError('英雄原生子树身份无效: ' + name)
    for name, template in templates.items():
        _nonempty(name, 'template')
        _fields(template, ('application_phase', 'parameters', 'reads', 'diagnose', 'edits'), label=name)
        if (not isinstance(template, dict) or not isinstance(template.get('parameters'), dict)
                or not isinstance(template.get('reads'), list) or not isinstance(template.get('diagnose'), dict)
                or not isinstance(template.get('edits'), list)
                or template.get('application_phase') != 'post_simulation_diagnosis_and_next_candidate'):
            raise ValueError('通用模板完整声明无效: ' + name)
        for parameter, declaration in template['parameters'].items():
            _nonempty(parameter, 'parameter')
            _fields(declaration, ('type',), ('nullable', 'minimum', 'maximum', 'values', 'unit'), label=parameter)
            kind = _nonempty(declaration['type'], parameter + '.type')
            base = kind.removesuffix('_array').removesuffix('_ref')
            if (kind not in ('enum', 'number', 'integer', 'number_or_boolean', 'boolean')
                    and (not kind.removesuffix('_array').endswith('_ref') or base not in _OBJECT_KINDS | {'rule'})):
                raise ValueError('模板参数类型未登记: ' + kind)
            if 'nullable' in declaration and type(declaration['nullable']) is not bool:
                raise ValueError('模板参数nullable必须为布尔值')
            if kind == 'enum' and (not isinstance(declaration.get('values'), list)
                    or not declaration['values']
                    or any(not isinstance(value, str) or not value for value in declaration['values'])):
                raise ValueError('模板枚举参数仅支持非空字符串取值')
            if 'unit' in declaration and declaration['unit'] not in ('ms', 'count', 'percent', 'ratio'):
                raise ValueError('模板参数单位未登记')
            for bound in ('minimum', 'maximum'):
                if bound in declaration and (type(declaration[bound]) not in (int, float)
                        or not math.isfinite(declaration[bound])):
                    raise ValueError('模板参数范围必须是有限数值')
            if declaration.get('minimum', -math.inf) > declaration.get('maximum', math.inf):
                raise ValueError('模板参数范围倒置')
        for section in ('reads', 'diagnose', 'edits'):
            _template_declaration(template[section], template['parameters'])
    for name, entries in objects.items():
        _nonempty(name, 'objects_ref')
        if not isinstance(entries, dict) or len(entries) > 512:
            raise ValueError('对象集合无效')
        for alias, row in entries.items():
            _nonempty(alias, 'object')
            _object_declaration(row, entries, alias)
    seen, resolved = set(), []
    for configuration in configurations:
        _fields(configuration, ('key', 'objects_ref', 'opener', 'states', 'execution_ref'),
                ('edit_range_ref',), label='configuration')
        key = configuration['key']
        if not isinstance(key, dict) or set(key) != {'specialization_id', 'hero_talent', 'target_type'}:
            raise ValueError('配置必须声明三个且仅三个身份键')
        if type(key['specialization_id']) is not int or key['specialization_id'] <= 0:
            raise ValueError('专精身份无效')
        for field in ('hero_talent', 'target_type'):
            _nonempty(key[field], field)
        if key['target_type'] not in ('single_target', 'aoe'):
            raise ValueError('目标类型必须为single_target或aoe')
        if key['hero_talent'] not in heroes:
            raise ValueError('英雄身份映射引用失效')
        identity = (key['specialization_id'], key['hero_talent'], key['target_type'])
        if identity in seen:
            raise ValueError('三键配置重复')
        seen.add(identity)
        if configuration['objects_ref'] not in objects:
            raise ValueError('对象集合引用失效')
        entries = objects[configuration['objects_ref']]
        if configuration.get('edit_range_ref') is not None:
            _argument(configuration['edit_range_ref'], dict(type='range_ref'), entries, (), 'edit_range_ref')
        execution = configuration.get('execution_ref')
        if execution is not None and execution not in executions:
            raise ValueError('已有爆发计划引用失效')
        states = configuration['states']
        if not isinstance(states, dict) or not 1 <= len(states) <= 32:
            raise ValueError('配置需要1到N个有界状态列表')
        for name, state in states.items():
            _nonempty(name, 'state')
            _fields(state, ('effect', 'expected', 'priority'), label='state')
            _argument(state['effect'], dict(type='effect_ref', nullable=True), entries, (), 'state.effect')
            if type(state.get('expected')) is not bool or not isinstance(state.get('priority'), list):
                raise ValueError('状态条件/有序规则列表无效')
            prior_rules = set()
            for rule in state['priority']:
                _fields(rule, ('name', 'template', 'arguments'), label='binding')
                _nonempty(rule.get('name'), 'rule.name')
                if rule['name'] in prior_rules:
                    raise ValueError('同状态规则名称重复')
                if rule['template'] not in templates:
                    raise ValueError('模板引用失效: ' + str(rule['template']))
                parameters = templates[rule['template']]['parameters']
                arguments = rule['arguments']
                if not isinstance(arguments, dict) or set(arguments) != set(parameters):
                    raise ValueError('模板参数缺失或含未声明字段: ' + rule['name'])
                for parameter, declaration in parameters.items():
                    _argument(arguments[parameter], declaration, entries, prior_rules, parameter)
                prior_rules.add(rule['name'])
        opener = configuration['opener']
        _fields(opener, ('source_basis', 'source_steps', 'ordinary_steps', 'precombat',
                         'burst_anchor', 'independent_burst_source_steps'), ('manual_differences',), label='opener')
        _nonempty(opener['source_basis'], 'opener.source_basis')
        source_steps = opener['source_steps']
        if (not isinstance(source_steps, list) or not 1 <= len(source_steps) <= 128
                or any(not isinstance(label, str) or not label for label in source_steps)):
            raise ValueError('完整起手来源列表无效')
        steps = opener['ordinary_steps']
        if not isinstance(steps, list) or not 1 <= len(steps) <= 128:
            raise ValueError('普通有序起手必须有1至128个步骤')
        for step in steps:
            _fields(step, ('action', 'source_step', 'source_form', 'attribute_query'), label='ordinary_step')
            _nonempty(step['action'], 'ordinary_step.action')
            action = entries.get(step['action'])
            if not action or action['kind'] != 'action':
                raise ValueError('起手动作引用失效')
            if type(step['source_step']) is not int or not 1 <= step['source_step'] <= len(source_steps):
                raise ValueError('起手来源步骤无效')
            if step['source_form'] not in [action['native_action'], *action.get('native_forms', [])]:
                raise ValueError('起手源形态引用失效')
            query = step['attribute_query']
            _fields(query, ('native_form', 'base_button', 'missing'), label='attribute_query')
            if query['missing'] != 'unknown_no_base_cost_fallback':
                raise ValueError('源形态缺失属性必须保留unknown')
            if query.get('native_form') != step['source_form'] or query.get('base_button') != action['base_button']:
                raise ValueError('起手源形态属性查询不一致')
        independent = opener['independent_burst_source_steps']
        if not isinstance(independent, list) or len(independent) > 128:
            raise ValueError('独立爆发来源列表无效')
        for step in independent:
            _fields(step, ('action', 'source_step', 'mapping'), ('commands',), label='independent_burst_source_step')
            _nonempty(step['action'], 'independent.action')
            if (not isinstance(step, dict) or step.get('mapping') != 'burst'
                    or entries.get(step.get('action'), {}).get('kind') != 'action'):
                raise ValueError('独立爆发来源动作引用失效')
            commands = step.get('commands', [dict(action=step['action'])])
            if (not isinstance(commands, list) or not 1 <= len(commands) <= 16
                    or any(not isinstance(row, dict) or not isinstance(row.get('action'), str)
                           or set(row) != {'action'} or entries.get(row['action'], {}).get('kind') != 'action'
                           for row in commands)):
                raise ValueError('独立爆发来源命令引用失效')
        indices = [step['source_step'] for step in [*steps, *independent]]
        if (any(type(index) is not int for index in indices)
                or sorted(indices) != list(range(1, len(source_steps) + 1))):
            raise ValueError('完整源步骤必须由普通和独立爆发映射唯一覆盖')
        anchor = opener.get('burst_anchor')
        if anchor is not None:
            _fields(anchor, ('source_step', 'freeze_per_task'), ('estimation',), label='burst_anchor')
            if type(anchor['source_step']) is not int or anchor['freeze_per_task'] is not True:
                raise ValueError('首次爆发来源锚点必须逐任务冻结')
        if anchor is not None and (not isinstance(anchor, dict) or anchor.get('source_step') not in indices):
            raise ValueError('首次爆发来源锚点无效')
        precombat = opener['precombat']
        if isinstance(precombat, list):
            for row in precombat:
                _fields(row, ('action', 'command_count', 'condition', 'path'), label='precombat')
                _nonempty(row['action'], 'precombat.action')
        if (not isinstance(precombat, list) or len(precombat) > 128 or any(
                entries.get(row.get('action'), {}).get('kind') != 'action'
                or row.get('command_count') != 1 or row.get('condition') != 'out_of_combat'
                or row.get('path') != 'existing_supported_path' for row in precombat)):
            raise ValueError('战前声明仅支持现有单命令路径')
        resolved.append(dict(copy.deepcopy(configuration), objects=copy.deepcopy(entries)))
    return resolved


def bind(capabilities, snapshot, target_count, *, spec_id, rule_snapshot, scene=None):
    """仅核验旧成果冻结的英雄/场景与战前声明，不求值或生成规则。"""
    if not isinstance(snapshot, dict):
        raise ValueError('规则起点缺少真实角色静态快照，请重新构建引擎')
    trees = snapshot.get('hero_subtree_ids')
    if (not isinstance(trees, list) or any(type(identity) is not int or identity <= 0 for identity in trees)):
        raise ValueError('规则起点缺少有效原生英雄子树身份')
    if scene is None:
        raise ValueError('三键配置需要明确目标类型，不猜测目标数阈值')
    heroes = rule_snapshot['pack']['identity_mappings']['hero_talents']
    matched = [row for row in rule_snapshot['resolved']
               if row['key']['specialization_id'] == spec_id
               and heroes[row['key']['hero_talent']] in trees and row['key']['target_type'] == scene]
    if len(matched) != 1:
        raise ValueError('三键配置需要唯一精确匹配；当前匹配数: ' + str(len(matched)))
    configuration = copy.deepcopy(matched[0])
    actions = {key: dict(row, button=row['base_button'], variants=row.get('native_forms', []))
               for key, row in configuration['objects'].items() if row['kind'] == 'action'}
    opener = configuration['opener']
    expected_precombat = [actions[row['action']]['native_action'] for row in opener['precombat']]
    if expected_precombat != [row['simc_action'] for row in capabilities.get('precombat_actions', [])]:
        raise ValueError('配置战前声明与现有实际执行/导出路径不一致')
    return dict(configuration_key=configuration['key'])
