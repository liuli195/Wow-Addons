"""固定通用特征与真实 Coba LinUCB 的小型共享状态适配。"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math

import result_store
from runtime import diagnostic_start, diagnostic_finish

FEATURE_VERSION = 'c50-a21-v1'
REWARD_VERSION = 'relative-common-batches-v1'
STATE_VERSION = 3
MATRIX_FORMAT = 'f64-le-v1'
MATRIX_FIELDS = ('theta', 'a_inv', 'theta_bytes', 'a_inv_bytes', 'matrix_format')
MODEL_KEY = 'linucb_c50_a21_feature_v1_reward_v1'
CONTEXT_DIMENSION, ACTION_DIMENSION, MODEL_DIMENSION = 50, 21, 1072
COBA_VERSION, NUMPY_VERSION = '8.1.0', '2.4.4'
FEATURES = [1, 'a', 'ax']
_CACHED_LEARNER = None
_SEEN_VERSION = None
FINDING_KINDS = (
    'unknown', 'blocked_by_plan', 'yielded', 'covered', 'attempt_failed',
    'missed_opportunity', 'missed_window', 'no_opportunity', 'missed_preparation',
    'not_triggered', 'utilized_off_selected_position', 'missed_short_window',
    'expired_unused', 'right_censored', 'actual_coverage_gap', 'effect_absence',
    'requirement_interval_unknown', 'maintenance_opportunity',
    'reservation_crowding_hypothesis', 'actual_overflow', 'near_full_opportunity', 'avoidable_idle',
)
TEMPLATES = ('条件触发与CD使用', 'Buff窗口与充能使用', '爆发前准备', '短期增益利用',
             '持续效果维护', '资源预留', '资源近满与溢出处理', '可避免空闲')
OPERATION_KINDS = ('move', 'insert', 'reduce_wait', 'remove_wait')
CONTEXT_SCHEMA = (
    *[f'finding.{kind}' for kind in (*FINDING_KINDS, 'other')], 'finding.valid',
    'certainty.observed_fact', 'certainty.hypothesis', 'certainty.unknown', 'certainty.valid',
    'unknown_rules.value', 'unknown_rules.valid',
    *[f'{group}.{stat}.{part}' for group in ('window_position', 'resource_fraction')
      for stat in ('valid_fraction', 'mean', 'min', 'max') for part in ('value', 'valid')],
    'opportunity_fraction.value', 'opportunity_fraction.valid', 'failure_fraction.value', 'failure_fraction.valid',
)
ACTION_SCHEMA = (
    *[f'operation.{kind}' for kind in OPERATION_KINDS],
    *[f'template.{kind}' for kind in (*TEMPLATES, 'other')],
    *[f'{name}.{part}' for name in ('source_position', 'target_position', 'signed_move', 'signed_click_change')
      for part in ('value', 'valid')],
)


def _ratio(numerator, denominator):
    return [numerator / denominator, 1.0] if denominator > 0 else [0.0, 0.0]


def _stat_features(samples):
    valid = [value for value in samples if _finite(value)]
    return [*_ratio(len(valid), len(samples)),
            *([sum(valid)/len(valid), 1.0, min(valid), 1.0, max(valid), 1.0]
              if valid else [0.0, 0.0] * 3)]


def context_features(diagnostic, payload, objects=None):
    """Encode the complete same-report diagnosis once, without fetching another report."""
    rules = diagnostic.get('rules', [])
    findings = [finding for rule in rules for finding in rule.get('findings', [])]
    count = len(findings)
    result = [sum(row.get('kind') == kind for row in findings) / count if count else 0.0
              for kind in FINDING_KINDS]
    result += [sum(row.get('kind') not in FINDING_KINDS for row in findings) / count if count else 0.0,
               float(bool(count))]
    result += [sum(row.get('certainty') == certainty for row in findings) / count if count else 0.0
               for certainty in ('observed_fact', 'hypothesis', 'unknown')]
    unknown_rules = sum(bool(row.get('status') == 'unknown' or row.get('unknown_conditions')
                             or row.get('unknown_evidence') or row.get('state_unknown_inputs')) for row in rules)
    result += [float(bool(count)), *_ratio(unknown_rules, len(rules))]
    payload = payload if isinstance(payload, dict) else {}
    scope = payload.get('scope') or {}
    inputs = {(row.get('sample_id'), row.get('input_index')): row for row in payload.get('inputs', [])
              if type(row.get('sample_id')) is int and type(row.get('input_index')) is int}
    windows, window_associations_complete = {}, True
    for finding in findings:
        window = finding.get('window')
        if not isinstance(window, dict):
            continue
        sample = window.get('sample_id', scope.get('sample_id'))
        index = finding.get('input_index', window.get('input_index'))
        start, end = window.get('start'), window.get('end')
        bounded = _finite(start) and _finite(end) and end > start
        window_id = _digest({key: window.get(key) for key in (
            'object', 'effect_id', 'instance_id', 'target_id', 'source_id',
            'start_event_index', 'end_event_index', 'start', 'end')})
        if type(index) is int:
            members = [((sample, index), inputs.get((sample, index)))]
        elif bounded:
            members = [(key, row) for key, row in inputs.items() if key[0] == sample
                       and _finite(row.get('time')) and start <= row['time'] <= end]
        else:
            # No sample/input association can be proven from this declaration.
            window_associations_complete = False
            members = []
        for identity, row in members:
            at = row.get('time') if row else None
            value = (at-start)/(end-start) if bounded and _finite(at) and start <= at <= end else None
            windows[(*identity, window_id)] = value
    window_features = _stat_features(list(windows.values()))
    if not window_associations_complete:
        window_features[:2] = [0.0, 0.0]
    result += window_features

    objects = objects or {}
    aliases = {name: declaration.get('native_identity', name) for name, declaration in objects.items()
               if declaration.get('kind') == 'resource'}
    resource_rows = payload.get('resource_events', [])
    if not aliases:
        aliases = {row['object']: row['object'] for row in resource_rows if isinstance(row.get('object'), str)}
    observed_resources = {}
    for row in resource_rows:
        identity = row.get('sample_id'), row.get('input_index')
        name = row.get('object')
        native = aliases.get(name, name if name in aliases.values() else None)
        if identity in inputs and native is not None:
            observed_resources.setdefault((*identity, native), []).append((row.get('current'), row.get('maximum')))
    resources = {}
    for identity, values in observed_resources.items():
        # Multiple contradictory readings are unknown; never borrow initialization capacity.
        value = None
        if all(pair == values[0] for pair in values):
            current, maximum = values[0]
            if _finite(current) and _finite(maximum) and maximum > 0:
                value = current / maximum
        resources[identity] = value
    result += _stat_features(list(resources.values()))

    opportunities = set()
    for row in findings:
        if row.get('certainty') != 'hypothesis' or type(row.get('input_index')) is not int:
            continue
        sample = row.get('sample_id', scope.get('sample_id'))
        identity = (sample, row['input_index'])
        if identity in inputs:
            opportunities.add(identity)
    result += _ratio(len(opportunities), len(inputs))
    from rule_diagnostics import _observed_rows
    actions = _observed_rows(dict(payload, inputs=list(inputs.values())), [], objects, None)['action_observations']
    actual = {}
    complete = scope.get('complete') is True
    for row in actions:
        identity = (row.get('sample_id'), row.get('input_index'), row.get('object'))
        outcome = row.get('attempt'), row.get('success')
        if ((identity[0], identity[1]) not in inputs or type(outcome[0]) is not bool
                or outcome[0] and type(outcome[1]) is not bool
                or identity in actual and actual[identity] != outcome):
            complete = False
        actual[identity] = outcome
    attempted = [success for attempt, success in actual.values() if attempt is True]
    result += _ratio(sum(success is False for success in attempted), len(attempted)) if complete else [0.0, 0.0]
    return _dense(result, CONTEXT_DIMENSION)


def action_features(diagnostic, program, operations):
    """Encode every concrete operation separately using the existing expansion mapping."""
    from rule_diagnostics import _structure
    _, expanded = _structure(program)
    length = len(expanded)
    positions = {}
    for ordinal, path in enumerate(expanded):
        if path is not None:
            positions.setdefault(tuple(path), []).append(ordinal)
    offsets = [0]
    for segment in program:
        width = (1 if isinstance(segment, list) else segment['count'] * len(segment['blocks'])
                 if segment['kind'] == 'Loop' else segment['clicks'] if segment['kind'] == 'WaitClicks' else 1)
        offsets.append(offsets[-1]+width)

    def gaps(path):
        if not isinstance(path, list) or not path or any(type(part) is not int for part in path):
            return []
        if len(path) == 1 and 0 <= path[0] <= len(program):
            return [offsets[path[0]]]
        if len(path) == 2 and 0 <= path[0] < len(program):
            segment = program[path[0]]
            if (isinstance(segment, dict) and segment.get('kind') == 'Loop'
                    and 0 <= path[1] <= len(segment['blocks'])):
                return [offsets[path[0]] + repeat*len(segment['blocks']) + path[1]
                        for repeat in range(segment['count'])]
        return []

    templates = {(row.get('name'), row.get('state')): row.get('template') for row in diagnostic.get('rules', [])}
    result = []
    for operation in operations:
        kind = operation.get('operation')
        if kind not in OPERATION_KINDS:
            raise ValueError('具体操作类别不支持固定特征版本')
        contributing = {templates.get((row.get('rule'), row.get('state'))) for row in operation.get('contributors', [])}
        values = [float(kind == name) for name in OPERATION_KINDS]
        values += [float(name in contributing) for name in TEMPLATES]
        values += [float(any(name not in TEMPLATES for name in contributing))]
        source, destination = operation.get('source_path'), operation.get('destination_path')
        origin = positions.get(tuple(source), []) if isinstance(source, list) else []
        targets = gaps(destination)
        if kind in ('reduce_wait', 'remove_wait'):
            targets = list(origin)
        elif kind == 'move' and origin and targets and source[:-1] == destination[:-1]:
            width = len(origin) if len(source) == 1 else 1
            targets = [at - (width if source[-1] < destination[-1] else 0) + (width-1)/2 for at in targets]
        source_mean = sum(origin)/len(origin)/length if origin and length else None
        target_mean = sum(targets)/len(targets)/length if targets and length else None
        movement = target_mean-source_mean if source_mean is not None and target_mean is not None else None
        change = None
        if length:
            if kind == 'move': change = 0.0
            elif kind == 'insert' and targets: change = len(targets)/length
            elif kind in ('reduce_wait', 'remove_wait') and origin and type(operation.get('count')) is int:
                change = -operation['count']/length
        for value in (source_mean, target_mean, movement, change):
            values += [value, 1.0] if _finite(value) else [0.0, 0.0]
        result.append(_dense(values, ACTION_DIMENSION))
    return result


class AlreadySettled(ValueError):
    """A removed receipt cannot be predicted again after its settlement watermark."""
    def __init__(self, task_run_id, decision_id, watermark):
        self.task_run_id, self.decision_id, self.watermark = task_run_id, decision_id, watermark
        super().__init__('选择决策已结算，不能重新预测；请恢复原任务的冻结反馈')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _dense(values, size):
    if not isinstance(values, list) or len(values) != size or not all(map(_finite, values)):
        raise ValueError('选择器特征维度或有限数值无效')
    return [float(value) for value in values]


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _learner():
    import coba
    import numpy
    from coba.learners import LinUCBLearner
    if coba.__version__ != COBA_VERSION or numpy.__version__ != NUMPY_VERSION:
        raise ValueError('共享选择器依赖版本不兼容，保留原状态')
    return LinUCBLearner(alpha=1, features=list(FEATURES), seed=1)


def _rng_state(learner):
    from coba.random import CobaRandom
    rng = learner._pred._pmfrng
    generator = rng._randu
    state = inspect.getgeneratorstate(generator)
    if (state not in ('GEN_CREATED', 'GEN_SUSPENDED')
            or generator.gi_code is not CobaRandom._next_uniform.__code__
            or generator.gi_frame is None):
        raise ValueError('Coba原生随机进度帧不受支持')
    frame = generator.gi_frame.f_locals
    if (not isinstance(frame.get('self'), CobaRandom)
            or any(type(frame.get(key)) is not int or frame[key] != value
                   for key, value in dict(a=116646453, c=9, m=2**30).items())
            or type(frame.get('s')) is not int or not 0 <= frame['s'] < 2**30
            or state == 'GEN_SUSPENDED' and frame.get('m_1') != 2**30-1
            or rng.seed != 1):
        raise ValueError('Coba原生随机进度参数不兼容')
    return frame['s']


def _snapshot(learner, *, version=0, reservations=None, settled=None, model=True, runtime=None):
    logging = runtime is not None and runtime.diagnostic_logging
    started = diagnostic_start() if logging else None
    try:
        record = dict(model_key=MODEL_KEY, version=version, state_version=STATE_VERSION,
            feature_version=FEATURE_VERSION, reward_version=REWARD_VERSION,
            coba_version=COBA_VERSION, numpy_version=NUMPY_VERSION,
            dimension=MODEL_DIMENSION, alpha=learner._alpha, features=list(learner._X),
            seed=learner.params['seed'], rng_state=_rng_state(learner),
            reservations=reservations if reservations is not None else [],
            settled=settled if settled is not None else {})
        if model:
            import numpy as np
            theta, inverse = learner._theta, learner._A_inv
            if theta is None or inverse is None:
                if (theta is not None or inverse is not None or version != 0
                        or record['rng_state'] != 1 or record['reservations'] or record['settled']):
                    raise ValueError('共享选择器仅严格空初始版本允许没有矩阵')
            elif (not isinstance(theta, np.ndarray) or not isinstance(inverse, np.ndarray)
                    or theta.shape != (MODEL_DIMENSION,)
                    or inverse.shape != (MODEL_DIMENSION, MODEL_DIMENSION)
                    or theta.dtype != np.dtype('float64') or inverse.dtype != np.dtype('float64')
                    or not np.isfinite(theta).all() or not np.isfinite(inverse).all()):
                raise ValueError('共享选择器矩阵必须具有固定形状、float64类型和全部有限值')
            record.update(theta=None, a_inv=None, matrix_format=MATRIX_FORMAT,
                theta_bytes=theta.astype('<f8', copy=False).tobytes() if theta is not None else None,
                a_inv_bytes=inverse.astype('<f8', copy=False).tobytes() if inverse is not None else None)
        return record
    finally:
        if logging:
            try:
                diagnostic_finish(runtime, 'model.snapshot', started, dimension=MODEL_DIMENSION, matrix_values=(MODEL_DIMENSION * (MODEL_DIMENSION + 1) if model and learner._theta is not None else 0))
            except Exception:
                pass


def _validate_parameters(record, *, state_version=None):
    expected = dict(model_key=MODEL_KEY, state_version=STATE_VERSION if state_version is None else state_version,
        feature_version=FEATURE_VERSION, reward_version=REWARD_VERSION,
        coba_version=COBA_VERSION, numpy_version=NUMPY_VERSION,
        dimension=MODEL_DIMENSION, alpha=1, features=FEATURES, seed=1)
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError('共享选择器状态版本、参数或特征不兼容，保留原状态')


def _validate_state(record):
    if (type(record.get('version')) is not int or record['version'] < 0
            or type(record.get('rng_state')) is not int or not 0 <= record['rng_state'] < 2**30
            or not isinstance(record.get('reservations'), list)
            or not isinstance(record.get('settled'), dict)
            or any(not isinstance(task, str) or not task or type(decision) is not int or decision < 0
                   for task, decision in record['settled'].items())):
        raise ValueError('共享选择器状态元数据无效，保留原状态')
    identities = set()
    for receipt in record['reservations']:
        _validate_receipt(receipt)
        identity = receipt['task_run_id'], receipt['decision_id']
        if (identity in identities or identity[1] <= record['settled'].get(identity[0], 0)
                or receipt['model_version'] > record['version']):
            raise ValueError('共享选择器决策身份或结算水位冲突')
        identities.add(identity)


def _restore(record, *, state_version=None):
    import numpy as np
    from coba.random import CobaRandom
    learner = _learner()
    _validate_parameters(record, state_version=state_version)
    _validate_state(record)
    theta, inverse = record.get('theta'), record.get('a_inv')
    if record['state_version'] in (1, 2) and any(
            record.get(name) is not None for name in ('theta_bytes', 'a_inv_bytes', 'matrix_format')):
        raise ValueError('旧格式必须使用原生数组列，不能包含新矩阵格式')
    if record['state_version'] == STATE_VERSION:
        if (not set(MATRIX_FIELDS) <= record.keys() or theta is not None or inverse is not None
                or record['matrix_format'] != MATRIX_FORMAT):
            raise ValueError('共享选择器矩阵格式无效，保留原状态')
        theta, inverse = record['theta_bytes'], record['a_inv_bytes']
        if theta is not None or inverse is not None:
            if (not isinstance(theta, bytes) or not isinstance(inverse, bytes)
                    or len(theta) != MODEL_DIMENSION * 8
                    or len(inverse) != MODEL_DIMENSION * MODEL_DIMENSION * 8):
                raise ValueError('共享选择器矩阵字节长度或类型无效，保留原状态')
            theta = np.frombuffer(theta, dtype='<f8').copy()
            inverse = np.frombuffer(inverse, dtype='<f8').reshape(MODEL_DIMENSION, MODEL_DIMENSION).copy()
    if not {'theta', 'a_inv'} <= record.keys() or (theta is None) != (inverse is None):
        raise ValueError('共享选择器矩阵不完整，保留原状态')
    if theta is None and (record['version'] != 0 or record['rng_state'] != 1
                          or record['reservations'] or record['settled']):
        raise ValueError('共享选择器只有严格空初始版本可以没有矩阵，保留原经验')
    if theta is not None:
        try:
            theta, inverse = np.asarray(theta), np.asarray(inverse)
            if (theta.shape != (MODEL_DIMENSION,) or inverse.shape != (MODEL_DIMENSION, MODEL_DIMENSION)
                    or theta.dtype.kind != 'f' or inverse.dtype.kind != 'f'
                    or not np.isfinite(theta).all() or not np.isfinite(inverse).all()):
                raise ValueError('选择器矩阵类型、形状或有限值无效')
            learner._theta, learner._A_inv, learner._np = theta, inverse, np
        except (ValueError, TypeError) as error:
            raise ValueError('共享选择器矩阵无效，保留原状态') from error
    learner._pred._pmfrng._randu = CobaRandom(record['rng_state'])._randu
    _rng_state(learner)
    return learner


def _validate_intent(intent):
    if not isinstance(intent, dict) or set(intent) != {
            'task_run_id', 'decision_id', 'parent_identity', 'pool_digest', 'context', 'actions'}:
        raise ValueError('选择器意图字段或身份无效')
    if (any(not isinstance(intent[key], str) or not intent[key]
            for key in ('task_run_id', 'parent_identity', 'pool_digest'))
            or type(intent['decision_id']) is not int or intent['decision_id'] < 1
            or not isinstance(intent['actions'], list) or not intent['actions']):
        raise ValueError('选择器意图身份或操作池无效')
    _dense(intent['context'], CONTEXT_DIMENSION)
    identities = set()
    for action in intent['actions']:
        if (not isinstance(action, dict) or set(action) != {'operation_id', 'features'}
                or not isinstance(action['operation_id'], str) or not action['operation_id']
                or action['operation_id'] in identities):
            raise ValueError('选择器具体操作身份无效或重复')
        _dense(action['features'], ACTION_DIMENSION)
        identities.add(action['operation_id'])


def _validate_receipt(receipt):
    if not isinstance(receipt, dict) or any(not isinstance(receipt.get(key), str) or not receipt[key]
            for key in ('task_run_id', 'parent_identity', 'pool_digest', 'intent_digest', 'operation_id')):
        raise ValueError('选择器回执身份无效')
    if (receipt.get('model_key') != MODEL_KEY or type(receipt.get('decision_id')) is not int
            or receipt['decision_id'] < 1 or type(receipt.get('model_version')) is not int
            or receipt['model_version'] < 1 or not _finite(receipt.get('probability'))
            or not 0 < receipt['probability'] <= 1):
        raise ValueError('选择器回执版本或概率无效')
    _dense(receipt.get('context'), CONTEXT_DIMENSION)
    _dense(receipt.get('action_features'), ACTION_DIMENSION)


def _control(record, base_version, phase='active'):
    return dict({key: value for key, value in record.items() if key not in MATRIX_FIELDS},
                base_version=base_version, phase=phase)


def _validate_control(record, *, state_version=None):
    _validate_parameters(record, state_version=state_version)
    _validate_state(record)
    if any(name in record for name in MATRIX_FIELDS):
        raise result_store.DataReadError('共享选择器控制记录不得包含矩阵字段')
    if (record.get('phase') not in ('bootstrap', 'migrating', 'active')
            or type(record.get('base_version')) is not int
            or not 0 <= record['base_version'] <= record['version']):
        raise result_store.DataReadError('共享选择器控制阶段或基础版本无效')


def _binary_available():
    if "binary-write-v1" not in result_store._api().get("DATA_STORE_CAPABILITIES", ()):
        raise result_store.DataReadError('data-store 缺少 binary-write-v1 能力，请更新技能并重启当前进程')


def _related(record, control):
    if (control['phase'] != 'active' and
            (control['version'] < record['version'] or control['base_version'] != record['version'])):
        raise result_store.DataReadError('共享选择器准备阶段与完整模型版本冲突')
    if (record.get('theta') is None and record.get('theta_bytes') is None
            and (control['version'] != 0 or control['rng_state'] != 1
                 or control['reservations'] or control['settled'])):
        raise result_store.DataReadError('共享选择器空模型不能叠加已有控制进度')
    if control['version'] >= record['version']:
        if control['base_version'] != record['version']:
            raise result_store.DataReadError('共享选择器控制记录与模型基础版本冲突')
        if control['version'] == record['version'] and any(
                control[key] != record[key] for key in ('rng_state', 'reservations', 'settled')):
            raise result_store.DataReadError('共享选择器同版本控制内容冲突')


def _activate(runtime=None):
    """Complete this key's bootstrap or physical migration under the existing shared lock."""
    _binary_available()
    for attempt in range(2):
        try:
            record = result_store.read_search_learner(MODEL_KEY)
            control = result_store.read_search_learner_control(MODEL_KEY)
            if record is None:
                empty = _snapshot(_learner(), runtime=runtime)
                prepared = _control(empty, 0, 'bootstrap')
                if control is None:
                    result_store.write_search_learner_control(prepared, runtime=runtime)
                    control = prepared
                elif control.get('state_version') == 2:
                    _validate_control(control, state_version=2)
                    if control != dict(prepared, state_version=2):
                        raise result_store.DataReadError('共享选择器旧初始化控制记录冲突')
                    result_store.write_search_learner_control(prepared, runtime=runtime)
                    control = prepared
                if control != prepared:
                    raise result_store.DataReadError('共享选择器完整记录缺失，不能重建已有经验')
                result_store.write_search_learner(empty, runtime=runtime)
                record = empty
            elif record.get('state_version') in (1, 2):
                old_version = record['state_version']
                learner = _restore(record, state_version=old_version)
                upgraded = _snapshot(learner, version=record['version'],
                    reservations=record['reservations'], settled=record['settled'], runtime=runtime)
                if control is None:
                    if old_version != 1:
                        raise result_store.DataReadError('共享选择器控制记录缺失')
                    prepared = _control(upgraded, record['version'], 'migrating')
                elif (old_version == 1 and control.get('state_version') == 2
                      and control.get('phase') == 'migrating'):
                    _validate_control(control, state_version=2)
                    prepared = _control(upgraded, record['version'], 'migrating')
                    if control != dict(prepared, state_version=2):
                        raise result_store.DataReadError('共享选择器迁移控制记录冲突')
                elif control.get('state_version') == STATE_VERSION:
                    _validate_control(control)
                    if control['phase'] != 'migrating':
                        raise result_store.DataReadError('共享选择器旧格式与迁移控制记录冲突')
                    if (control['base_version'] != record['version']
                            or control['version'] < record['version']):
                        raise result_store.DataReadError('共享选择器迁移控制记录冲突，旧写入者已改变模型')
                    _related(record, control)
                    prepared = control
                    if old_version == 1 and control != _control(upgraded, record['version'], 'migrating'):
                        raise result_store.DataReadError('共享选择器迁移控制记录冲突')
                else:
                    _validate_control(control, state_version=old_version)
                    if control['phase'] == 'bootstrap' and control == dict(
                            _control(upgraded, 0, 'bootstrap'), state_version=old_version):
                        if upgraded != _snapshot(_learner(), runtime=runtime):
                            raise result_store.DataReadError('共享选择器旧初始化已有非空经验')
                    elif control['phase'] != 'active':
                        raise result_store.DataReadError('共享选择器旧控制阶段无效')
                    _related(record, control)
                    prepared = (_control(upgraded, record['version'], 'migrating')
                                if control['version'] < record['version'] else
                                dict(control, state_version=STATE_VERSION, phase='migrating'))
                if control != prepared:
                    result_store.write_search_learner_control(prepared, runtime=runtime)
                control = prepared
                result_store.write_search_learner(upgraded, runtime=runtime)
                record = upgraded
            _restore(record)
            if control is None:
                raise result_store.DataReadError('共享选择器控制记录缺失')
            _validate_control(control)
            _related(record, control)
            if control['phase'] != 'active':
                if control['phase'] == 'bootstrap' and record != _snapshot(_learner(), runtime=runtime):
                    raise result_store.DataReadError('共享选择器初始化阶段已有非空经验，不能覆盖')
                control = dict(control, phase='active')
                result_store.write_search_learner_control(control, runtime=runtime)
            return record, control
        except Exception:
            if attempt:
                raise
    raise AssertionError('unreachable')


def _remember(record, learner, *, full_version=None):
    global _CACHED_LEARNER, _SEEN_VERSION
    # Keep one native model and small metadata, never a second matrix snapshot.
    state = {key: record[key] for key in ('version', 'rng_state', 'reservations', 'settled')}
    state['full_version'] = (record.get('base_version', record['version'])
                             if full_version is None else full_version)
    source = result_store.DATA_ROOT.resolve(), MODEL_KEY
    _CACHED_LEARNER = source, state, learner
    _SEEN_VERSION = source, record['version']
    return state, learner


def _load(runtime=None, *, initialize=True):
    logging = runtime is not None and runtime.diagnostic_logging
    started = diagnostic_start() if logging else None
    try:
        from coba.random import CobaRandom
        _binary_available()
        global _CACHED_LEARNER, _SEEN_VERSION
        cached, _CACHED_LEARNER = _CACHED_LEARNER, None
        source = result_store.DATA_ROOT.resolve(), MODEL_KEY
        if _SEEN_VERSION is not None and _SEEN_VERSION[0] != source:
            _SEEN_VERSION = None
        cached = cached if cached is not None and cached[0] == source else None
        record = (result_store.read_search_learner_metadata(MODEL_KEY) if cached
                  else result_store.read_search_learner(MODEL_KEY))
        control = result_store.read_search_learner_control(MODEL_KEY)
        if record is None and control is None and not initialize:
            learner = _learner()
            return _snapshot(learner, runtime=runtime), learner
        if record is None or record.get('state_version') in (1, 2):
            if _SEEN_VERSION is not None:
                raise result_store.DataReadError('共享选择器权威记录丢失或格式回退，保留已知经验版本')
            record, control = _activate(runtime)
            cached = None
        _validate_parameters(record)
        if record.get('matrix_format') != MATRIX_FORMAT:
            raise result_store.DataReadError('共享选择器矩阵格式标记无效')
        if control is None:
            raise result_store.DataReadError('共享选择器控制记录丢失，保留已有经验')
        _validate_control(control)
        if (_SEEN_VERSION is not None
                and max(record['version'], control['version']) < _SEEN_VERSION[1]):
            raise result_store.DataReadError('共享选择器权威版本回退，保留已知经验版本')
        if control['phase'] != 'active':
            record, control = _activate(runtime)
            cached = None
        full_version = record['version']
        if cached and full_version == cached[1]['full_version']:
            state, learner = cached[1], cached[2]
        else:
            if cached:
                record = result_store.read_search_learner(MODEL_KEY)
            state, learner = record, _restore(record)
        if control['version'] >= full_version:
            if control['base_version'] != full_version:
                raise result_store.DataReadError('共享选择器控制记录与完整模型基础版本冲突')
            if control['version'] == full_version and any(
                    control[key] != state[key] for key in ('rng_state', 'reservations', 'settled')):
                raise result_store.DataReadError('共享选择器同版本控制内容冲突')
            state = control
        if learner._A_inv is None and (state['version'] != 0 or state['rng_state'] != 1
                                       or state['reservations'] or state['settled']):
            raise result_store.DataReadError('共享选择器空模型不能叠加已有控制进度')
        if _SEEN_VERSION is not None and state['version'] < _SEEN_VERSION[1]:
            raise result_store.DataReadError('共享选择器权威版本回退，保留已知经验版本')
        learner._pred._pmfrng._randu = CobaRandom(state['rng_state'])._randu
        return _remember(state, learner, full_version=full_version)
    finally:
        if logging:
            diagnostic_finish(runtime, 'model.load', started, dimension=MODEL_DIMENSION)


def _receipt(record, task, decision):
    return next((row for row in record['reservations']
                 if row['task_run_id'] == task and row['decision_id'] == decision), None)


def _predict(learner, intent, runtime, version):
    task, decision = intent['task_run_id'], intent['decision_id']
    intent_digest = _digest(intent)
    context = _dense(intent['context'], CONTEXT_DIMENSION)
    actions = [_dense(row['features'], ACTION_DIMENSION) for row in intent['actions']]
    logging = runtime is not None and runtime.diagnostic_logging
    started = diagnostic_start() if logging else None
    try:
        selected, probability = learner.predict(context, actions)
    finally:
        if logging:
            diagnostic_finish(runtime, 'model.predict', started, actions=len(actions), context_dimension=CONTEXT_DIMENSION, action_dimension=ACTION_DIMENSION)
    index = next((i for i, action in enumerate(actions) if action is selected), None)
    if index is None:
        raise ValueError('Coba返回的动作不是原具体操作对象')
    receipt = dict(task_run_id=task, decision_id=decision,
        parent_identity=intent['parent_identity'], pool_digest=intent['pool_digest'],
        intent_digest=intent_digest, operation_id=intent['actions'][index]['operation_id'],
        context=context, action_features=selected, probability=float(probability),
        model_key=MODEL_KEY, model_version=version)
    _validate_receipt(receipt)
    return receipt


def reserve(intent, runtime=None):
    """Predict once and atomically reserve the native RNG progress with its receipt."""
    global _CACHED_LEARNER
    _validate_intent(intent)
    intent_digest = _digest(intent)
    task, decision = intent['task_run_id'], intent['decision_id']
    with result_store.search_learner_lock(runtime):
        for attempt in range(2):
            record, learner = _load(runtime)
            watermark = record['settled'].get(task, 0)
            if decision <= watermark:
                raise AlreadySettled(task, decision, watermark)
            existing = _receipt(record, task, decision)
            if existing:
                if existing['intent_digest'] != intent_digest:
                    raise ValueError('选择器已有决策意图身份不符')
                return copy.deepcopy(existing)
            last = max([watermark, *[row['decision_id'] for row in record['reservations']
                                     if row['task_run_id'] == task]])
            if decision != last + 1:
                raise ValueError('选择器决策序号须连续递增')
            if runtime is not None:
                runtime.check()
            initialized = learner._A_inv is None
            _CACHED_LEARNER = None
            receipt = _predict(learner, intent, runtime, record['version'] + 1)
            updated = _snapshot(learner, version=record['version']+1,
                reservations=[*record['reservations'], receipt], settled=record['settled'], model=initialized, runtime=runtime)
            if not initialized:
                updated = _control(updated, record['full_version'])
            try:
                if initialized:
                    result_store.write_search_learner(updated, runtime=runtime)
                else:
                    result_store.write_search_learner_control(updated, runtime=runtime)
                _remember(updated, learner)
                return copy.deepcopy(receipt)
            except Exception:
                current, _ = _load(runtime)  # A read failure stops; never reset or blindly repeat predict.
                committed = _receipt(current, task, decision)
                if committed and committed == receipt:
                    return copy.deepcopy(committed)
                if (current['version'] != record['version']
                        or current['settled'].get(task, 0) != watermark or attempt):
                    _CACHED_LEARNER = None
                    raise
        raise AssertionError('unreachable')


def settle(receipt, reward, common_batches, reason=None, runtime=None):
    """Learn on the latest shared model once; settle absent evidence without a fake zero."""
    global _CACHED_LEARNER
    _validate_receipt(receipt)
    if type(common_batches) is not int or common_batches < 0:
        raise ValueError('共同批次数无效')
    valid_reward = _finite(reward) and common_batches > 0
    reward = float(reward) if valid_reward else None
    feedback = dict(status='learned' if valid_reward else 'no_learn', reward=reward,
                    common_batches=common_batches, reason=reason,
                    task_run_id=receipt['task_run_id'], decision_id=receipt['decision_id'])
    task, decision = receipt['task_run_id'], receipt['decision_id']
    with result_store.search_learner_lock(runtime):
        for attempt in range(2):
            record, learner = _load(runtime)
            watermark = record['settled'].get(task, 0)
            if decision <= watermark:
                return dict(feedback, status='already_settled', already_committed=True,
                            model_version=record['version'])
            original = _receipt(record, task, decision)
            if original != receipt:
                raise ValueError('共享选择器反馈回执身份不符或不存在')
            if decision != watermark + 1:
                raise ValueError('共享选择器必须按原任务head顺序结算')
            if runtime is not None:
                runtime.check()
            _CACHED_LEARNER = None  # A failed or uncertain write must reload before learning again.
            if valid_reward:
                logging = runtime is not None and runtime.diagnostic_logging
                started = diagnostic_start() if logging else None
                try:
                    learner.learn(receipt['context'], receipt['action_features'], reward, receipt['probability'])
                finally:
                    if logging:
                        diagnostic_finish(runtime, 'model.learn', started, common_batches=common_batches, dimension=MODEL_DIMENSION)
            updated = _snapshot(learner, version=record['version']+1,
                reservations=[row for row in record['reservations'] if row is not original],
                settled=dict(record['settled'], **{task: decision}), model=valid_reward, runtime=runtime)
            if not valid_reward:
                updated = _control(updated, record['full_version'])
            try:
                if valid_reward:
                    result_store.write_search_learner(updated, runtime=runtime)
                else:
                    result_store.write_search_learner_control(updated, runtime=runtime)
                _remember(updated, learner)
                return dict(feedback, model_version=updated['version'], already_committed=False)
            except Exception:
                current, _ = _load(runtime)  # Replacement may have succeeded before the writer raised.
                if current['settled'].get(task, 0) >= decision:
                    return dict(feedback, model_version=current['version'], already_committed=True)
                if (current['version'] != record['version']
                        or _receipt(current, task, decision) != receipt or attempt):
                    _CACHED_LEARNER = None
                    raise
        raise AssertionError('unreachable')


class MemorySelection:
    """One task's live model and independent native random stream, never a shared writer."""

    def __init__(self, state, runtime=None):
        global _CACHED_LEARNER
        from coba.random import CobaRandom
        with result_store.search_learner_lock(runtime):
            record, self.learner = _load(runtime, initialize=False)
            _CACHED_LEARNER = None  # The task owns this matrix until its next checkpoint.
        self.state = state
        self.version = record['version']
        self.watermark = record['settled'].get(state['run_id'], 0)
        state['selection_sequence'] = max(state.get('selection_sequence', 0), self.watermark)
        rng = state.get('selection_rng_state', state['config']['random_seed'])
        self.learner._pred._pmfrng._randu = CobaRandom(rng)._randu
        self.feedback = {}

    def reserve(self, intent, runtime=None):
        _validate_intent(intent)
        if runtime is not None:
            runtime.check()
        receipt = _predict(self.learner, intent, runtime, self.version + 1)
        self.state['selection_rng_state'] = _rng_state(self.learner)
        return receipt

    def settle(self, receipt, reward, common_batches, reason=None, runtime=None):
        _validate_receipt(receipt)
        decision = receipt['decision_id']
        if decision not in self.feedback:
            valid = _finite(reward) and common_batches > 0
            if valid:
                self.learner.learn(receipt['context'], receipt['action_features'],
                                   float(reward), receipt['probability'])
            self.feedback[decision] = dict(status='learned' if valid else 'no_learn',
                reward=float(reward) if valid else None, common_batches=common_batches,
                reason=reason, task_run_id=receipt['task_run_id'], decision_id=decision)
        return dict(self.feedback[decision])

    def refresh(self, record, learner):
        from coba.random import CobaRandom
        rng = _rng_state(self.learner)
        self.learner = learner
        self.learner._pred._pmfrng._randu = CobaRandom(rng)._randu
        self.version = record['version']
        self.feedback.clear()


def commit_feedback(intents, runtime=None, session=None):
    """Merge actual task feedback once into the latest model under the existing lock."""
    global _CACHED_LEARNER
    with result_store.search_learner_lock(runtime):
        record, learner = _load(runtime)
        settled = dict(record['settled'])
        feedbacks = {}
        changed = False
        _CACHED_LEARNER = None
        for key in sorted(intents, key=int):
            intent = intents[key]
            receipt = intent['receipt']
            _validate_receipt(receipt)
            task, decision = receipt['task_run_id'], receipt['decision_id']
            valid = _finite(intent['reward']) and intent['common_batches'] > 0
            feedbacks[key] = dict(status='learned' if valid else 'no_learn',
                reward=float(intent['reward']) if valid else None,
                common_batches=intent['common_batches'], reason=intent['reason'],
                task_run_id=task, decision_id=decision)
            if decision <= settled.get(task, 0):
                continue
            if runtime is not None:
                runtime.check()
            if learner._A_inv is None:
                learner._initialize(receipt['context'], receipt['action_features'])
            if valid:
                learner.learn(receipt['context'], receipt['action_features'],
                              float(intent['reward']), receipt['probability'])
            settled[task] = decision
            changed = True
        if changed:
            # No task's older matrix or RNG replaces another task's experience.
            updated = _snapshot(learner, version=record['version'] + 1,
                reservations=[row for row in record['reservations']
                              if row['decision_id'] > settled.get(row['task_run_id'], 0)],
                settled=settled, runtime=runtime)
            result_store.write_search_learner(updated, runtime=runtime)
            record = updated
        if session is not None:
            session.refresh(record, learner)
        return feedbacks
