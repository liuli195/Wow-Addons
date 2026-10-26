"""Manually launched seed preparation; all business records use the shared center."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import threading
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from itertools import islice
import json
import math
from pathlib import Path
import sqlite3
import sys
import uuid

import result_store
from search import digest, config_for, TaskStore
from runtime import TaskRuntime, TaskCancelled, diagnostic_summary

CANDIDATE_SCHEMA = dict(candidate_id='VARCHAR', label='VARCHAR', class_name='VARCHAR',
    spec='VARCHAR', source='VARCHAR', source_id='VARCHAR', source_revision='VARCHAR',
    active='BOOLEAN', unavailable_reason='VARCHAR', original='VARCHAR', instructions='VARCHAR',
    semantic='VARCHAR', changes='VARCHAR[]', family='VARCHAR', core='JSON', program='JSON')
PROCESSED_SCHEMA = dict(configuration_key='JSON', candidate_id='VARCHAR', condition='VARCHAR', status='VARCHAR',
    error='VARCHAR', initial_program='JSON', program='JSON', family='VARCHAR', core_retained='BOOLEAN',
    rounds='UBIGINT', stop_reason='VARCHAR', elapsed_seconds='DOUBLE', scores='DOUBLE[]',
    initial_scores='DOUBLE[]', comparison='JSON', task_path='VARCHAR', native_batch_starts='UBIGINT',
    batch_requests='UBIGINT', cache_hits='UBIGINT')
SELECTED_SCHEMA = dict(configuration_key='JSON', candidate_id='VARCHAR', condition='VARCHAR', class_name='VARCHAR',
    spec='VARCHAR', targets='UBIGINT', program='JSON', family='VARCHAR', score='DOUBLE',
    scores='DOUBLE[]', template_sha256='VARCHAR', engines='JSON')
SELECTED_V2_SCHEMA = dict(SELECTED_SCHEMA, contract_version='UBIGINT', evaluation='JSON')
RETEST_SEEDS = (20261008, 20261009, 20261010)
TRAINING_VERSION = 'seed-training-v2'
PREPARATION_VERSION = 'seed-preparation-v1'
PREPARED_SCHEMA = dict(CANDIDATE_SCHEMA, kind='VARCHAR', config_key='VARCHAR',
    version='VARCHAR', program_revision='VARCHAR', status='VARCHAR', reason='VARCHAR',
    initial_program='JSON', behavior_id='VARCHAR', adaptation='JSON', context='JSON',
    checksum='VARCHAR', representative_id='VARCHAR', representative_program='JSON')
LEGACY_SOURCE_COMMIT = 'be350c90af3ff90af3ba59e05ad011b4bd61ab44'
# 仅本票已审阅的三个执行/身份模块；摘要来自固定 Git blob 的 LF / CRLF 字节。
LEGACY_EXECUTION_RULES = {
    'projects/sim2gse/search.py': (
        '485ab5afb5d5c5335524a0996215605fe241839467e9476295e55270855c22b0',
        '48a5995fc3a84cf9a0d3718882bbdcfae52777dfc62bd7501f8ffcedb811debc'),
    'projects/sim2gse/seed_training.py': (
        '54e32ce78bb1973899909da3841108335d180a2e763af871bc34c47487da6510',
        'b816f1e1c6506724f20902b9566a3a25b2b6f8a2fe0143c423b637a868d6b768'),
    'projects/sim2gse/simulation_config.py': (
        '649f3a70293b25ddde2ac66505966a91bc3370999f928b867e713ab4fa220484',
        '4f842e229e2c4c01091fa0e7faaf9fc90b6fd367d4979a99b86d3c17ddb794f5'),
}
# 仅这三个未改模块可由受控导入器证明换行差异；摘要来自固定 be350 Git blob。
LEGACY_LINE_ENDING_RULES = {
    'projects/sim2gse/gse_import.py': '9a01cccda449b49c30d96ae315c9bfec027e8cb7bc29f1ce83f3cf693a41cd31',
    'projects/sim2gse/macro_interpreter.py': '2b31a0812c3658411ccb77b78b892314f822876500f0895dd49bab7ea593bcc5',
    'projects/sim2gse/runtime.py': 'bcc3d3e28f17e04735b4629272ada3bf311db8471ecfe3cc74de4c916270364f',
}
LEGACY_SEMANTIC_VERSIONS = dict(training='seed-training-v2',
    search='multi-start-local-adaptive-v2', statistics='paired-bootstrap-v1',
    behavior='sim2gse-search-behavior-v1')


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


@contextmanager
def writer_lock():
    import msvcrt
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with (result_store.DATA_ROOT / '.seed-writer.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ValueError('另一起点整理正在执行') from error
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def register(path):
    row = json.loads(Path(path).read_text(encoding='utf-8'))
    optional = {'source_id', 'active'}
    required = set(CANDIDATE_SCHEMA) - {'candidate_id', 'source_id', 'source_revision', 'active', 'unavailable_reason'}
    if not isinstance(row, dict) or not required <= set(row) or set(row) - required - optional:
        raise ValueError('清洗件必须包含来源、原件、使用说明、语义、清洗记录、家族、核心及程序')
    for key in ('label', 'class_name', 'spec', 'source', 'original', 'instructions', 'family'):
        if not isinstance(row[key], str) or not row[key].strip():
            raise ValueError('清洗件字段不能为空: ' + key)
    if row['semantic'] not in ('preserved', 'rewritten', 'unsupported'):
        raise ValueError('清洗件语义状态无效')
    if (not isinstance(row['changes'], list) or
            any(not isinstance(item, str) for item in row['changes']) or
            not isinstance(row['program'], list) or
            (row['semantic'] != 'unsupported' and not row['program']) or
            not isinstance(row['core'], list)):
        raise ValueError('清洗记录、核心或程序格式无效')
    if row['semantic'] == 'unsupported' and (row['program'] or not row['changes']):
        raise ValueError('不可表达材料必须保存原因且不得伪造程序')
    if ('source_id' in row and (not isinstance(row['source_id'], str) or not row['source_id'].strip()
                                 or row['source_id'].startswith('history:'))):
        raise ValueError('人工来源身份不能为空或使用历史保留前缀')
    if 'active' in row and type(row['active']) is not bool:
        raise ValueError('来源活动状态必须为布尔值')
    row['candidate_id'] = digest({key: row[key] for key in required | ({'source_id'} if 'source_id' in row else set())})
    row.setdefault('source_id', row['candidate_id'])
    row.setdefault('active', True)
    row['unavailable_reason'] = '' if row['active'] else '来源已明确停用'
    row['source_revision'] = digest(row)
    with writer_lock():
        rows = registry_rows()
        previous = next((item for item in rows if item['source_id'] == row['source_id']), None)
        if previous and previous['program'] == row['program']:
            row['candidate_id'] = previous['candidate_id']
        if previous != row:
            result_store.write('seed_candidates', 'registry',
                               [item for item in rows if item['source_id'] != row['source_id']] + [row],
                               schema=CANDIDATE_SCHEMA)
    return {'status': 'registered', 'candidate_id': row['candidate_id']}


def template_character(text):
    """Project identity fields only; actual simulation always reads the full template."""
    from task import parse_character, _CLASS_KEYS, _ALLOWED_KEYS, _EQUIPMENT_SLOTS
    projected = []
    for line in text.splitlines():
        key, separator, value = line.strip().partition('=')
        key = {'shoulders': 'shoulder', 'wrists': 'wrist'}.get(key, key)
        if not separator or key not in _CLASS_KEYS | _ALLOWED_KEYS:
            continue
        if key in _EQUIPMENT_SLOTS and not value.startswith(','):
            name, separator, options = value.partition(',')
            if not separator:
                raise ValueError('标准模板装备缺少物品编号: ' + key)
            value = ',' + options
        projected.append(key + '=' + value)
    return parse_character('\n'.join(projected))


def search_program(shared):
    """Recover only the structures already expressible at the search entrance."""
    if isinstance(shared, list):
        return shared
    if not isinstance(shared, dict) or shared.get('adapter') != 'search':
        raise ValueError('历史程序未包含可恢复的搜索结构')
    output = []
    for node in shared['nodes']:
        kind = node['kind']
        if kind == 'Action':
            commands = node['commands']
            if commands and all(command.get('condition') == 'nocombat' for command in commands):
                continue
            if len(commands) == 1 and commands[0].get('kind') == 'castsequence':
                command = commands[0]
                output.append(dict(kind='CastSequence', members=command['members'], reset=command.get('reset')))
            elif commands and all(command.get('condition') in (None, '') and
                                  command.get('simc_action') for command in commands):
                output.append([command['simc_action'] for command in commands])
            else:
                raise ValueError('历史动作包含搜索入口不能表达的条件')
        elif kind == 'Loop' and node['step_function'] == 'Sequential':
            body = search_program(dict(adapter='search', nodes=node['body']))
            if any(not isinstance(block, list) for block in body):
                raise ValueError('历史循环包含不能表达的嵌套结构')
            output.append(dict(kind='Loop', count=node['count'], blocks=body))
        elif kind == 'Pause' and node.get('duration_ms') is None:
            output.append(dict(kind='WaitClicks', clicks=node['clicks']))
        else:
            raise ValueError('历史程序包含不能表达的控制块')
    return output


def registry_rows():
    rows = result_store.read_records('seed_candidates', 'registry')
    for row in rows:
        row['program'], row['core'] = decode(row['program']), decode(row['core'])
        row.setdefault('source_id', row['candidate_id'])
        row.setdefault('active', True)
        row.setdefault('unavailable_reason', '')
        row.setdefault('source_revision', digest(row))
    return rows


def sync_history(character, *, sources=None):
    """适配来源后一次原子登记；读取失败不会伪装成来源删除。"""
    rows = registry_rows() if sources is None else sources
    with result_store.query("SELECT table_name FROM information_schema.tables WHERE table_name='runs'",
                            tables=['runs']) as cursor:
        available = bool(cursor.fetchone())
    scanned = set()
    updates = {}
    histories = result_store.iter_rows(
        'SELECT run_id, profile, status, candidate_data_key, candidate_key, search_dps FROM runs '
        "WHERE json_extract_string(profile, '$.identity.class') = ? "
        "AND json_extract_string(profile, '$.identity.spec') = ?",
        [character.class_name, character.spec], tables=['runs']) if available else ()
    candidate_columns = ['candidate_data_key', 'run_id', 'candidate_key', 'program']
    while history_batch := list(islice(histories, 500)):
        keys = list(dict.fromkeys(run['candidate_data_key'] for run in history_batch
                                 if run['status'] == 'completed' and run['candidate_data_key']))
        try:
            candidates = result_store.read_many('candidates', keys, columns=candidate_columns)
        except result_store.DataReadError as error:
            if not isinstance(error.__cause__, result_store._api()['MissingKeyError']):
                raise
            candidates = []
        if (len(candidates) != len(keys)
                or {candidate['candidate_data_key'] for candidate in candidates} != set(keys)):
            # 非空组写入契约下，异常批次沿用逐组唯一性判断；只点读本批已知键。
            candidates = [candidate for key in keys if (candidate := result_store.one(
                'candidates', 'candidate_data_key', key, columns=candidate_columns)) is not None]
        candidates_by_key = {}
        for candidate in candidates:
            candidates_by_key.setdefault(candidate['candidate_data_key'], []).append(candidate)
        for run in history_batch:
            profile = decode(run['profile']) or {}
            identity = profile.get('identity', {})
            if identity.get('class') != character.class_name or identity.get('spec') != character.spec:
                continue
            source_id = 'history:' + run['run_id']
            if source_id in scanned:
                raise ValueError('历史来源身份不唯一: ' + run['run_id'])
            scanned.add(source_id)
            reason, shared, program = '', None, []
            if run['status'] != 'completed':
                reason = '历史尚未完成: ' + str(run['status'])
            elif not run['candidate_data_key']:
                reason = '历史最佳候选引用缺失'
            else:
                matches = candidates_by_key.get(run['candidate_data_key'], [])
                candidate = matches[0] if len(matches) == 1 else None
                if candidate is None:
                    reason = '历史最佳候选记录缺失: ' + run['run_id']
                elif (candidate['run_id'] != run['run_id'] or
                      (run.get('candidate_key') and candidate['candidate_key'] != run['candidate_key'])):
                    reason = '历史最佳候选引用不一致: ' + run['run_id']
                else:
                    shared = decode(candidate['program'])
                    try:
                        program = search_program(shared)
                    except (ValueError, KeyError, TypeError) as error:
                        reason = str(error)
            previous = next((row for row in rows if row['source_id'] == source_id or
                             row['candidate_id'] == digest(dict(history=run['run_id'], program=program))), None)
            row = dict(candidate_id=(digest(dict(history=run['run_id'], program=program)) if not reason
                                     else (previous['candidate_id'] if previous else digest(dict(history=run['run_id'])))),
                       source_id=source_id, label=run['run_id'], class_name=character.class_name, spec=character.spec,
                       source=source_id, original=json.dumps(shared, ensure_ascii=False),
                       instructions='历史最佳程序；原角色成绩仅作来源证据，当前训练独立评价',
                       semantic='unsupported' if reason else 'preserved', changes=[reason] if reason else [],
                       family='history-search', core=[], program=program if not reason else [],
                       active=not bool(reason), unavailable_reason=reason)
            row['source_revision'] = digest(dict(row, candidate_reference=run['candidate_data_key'],
                                                status=run['status'], search_dps=run['search_dps']))
            updates[source_id] = row
    output = []
    for row in rows:
        if row['source_id'] in updates:
            output.append(updates.pop(row['source_id']))
        elif (row['source_id'].startswith('history:') and row['class_name'] == character.class_name
              and row['spec'] == character.spec and row['source_id'] not in scanned):
            row = dict(row, active=False, unavailable_reason='历史来源已明确删除')
            row['source_revision'] = digest({key: value for key, value in row.items() if key != 'source_revision'})
            output.append(row)
        else:
            output.append(row)
    output.extend(updates.values())
    if output != rows:
        result_store.write('seed_candidates', 'registry', output, schema=CANDIDATE_SCHEMA)
    return output





def retains_core(program, core):
    if not core:
        return False
    # Exact grouped fragment; no frequency-based or cyclic-rotation equivalence.
    return any(program[index:index + len(core)] == core for index in range(len(program)))


def filter_search_program(program, excluded, validation_capabilities):
    """只派生程序；裁剪已知动作并保留剩余结构、顺序与原始删除位置。"""
    from program import _search_castsequence_parts
    from macro_interpreter import parse_castsequence
    removed = []

    def keep(block, path):
        remaining = []
        for index, action in enumerate(block):
            if isinstance(action, str) and action in excluded:
                removed.append(dict(path=f'{path}[{index}]', action=action))
            else:
                remaining.append(action)
        return remaining

    if not isinstance(program, list) or not 1 <= len(program) <= 128:
        return program, removed  # 原校验负责不可恢复的历史结构。
    output = []
    for index, segment in enumerate(program):
        path = f'segments[{index}]'
        if isinstance(segment, list):
            if not 1 <= len(segment) <= 16:
                output.append(segment)
                continue
            block = keep(segment, path)
            if block:
                output.append(block)
        elif isinstance(segment, dict) and segment.get('kind') == 'Loop':
            blocks, count = segment.get('blocks'), segment.get('count')
            if (type(count) is not int or not 1 <= count <= 4096 or not isinstance(blocks, list)
                    or not 1 <= len(blocks) <= 128
                    or any(not isinstance(block, list) or not 1 <= len(block) <= 16 for block in blocks)):
                output.append(segment)  # 不因删空而掩盖原控制结构错误。
                continue
            remaining = [keep(block, f'{path}.blocks[{block_index}]')
                         for block_index, block in enumerate(blocks)]
            remaining = [block for block in remaining if block]
            if remaining:
                output.append(dict(segment, blocks=remaining))
        elif isinstance(segment, dict) and segment.get('kind') == 'CastSequence':
            # 先核原结构及语法，再核成员证据；静态不可用技能不需要伪造法术编号。
            members, reset_text = _search_castsequence_parts(segment, path)
            parsed = parse_castsequence('/castsequence' + reset_text + ' ' + ','.join(members),
                                        path, actions=None)
            actions = validation_capabilities['actions']
            known = {action['simc_action'] for action in actions if action.get('kind') == 'spell'}
            known.update(excluded - {action['simc_action'] for action in actions})
            if parsed['members'] != members or any(member not in known for member in members):
                raise ValueError(f'{path}: /castsequence 包含当前角色不支持且非原生确证不可用的技能')
            members = keep(members, path + '.members')
            if members:
                output.append(dict(segment, members=members))
        else:
            output.append(segment)
    return output, removed


def training_program(program, capabilities, all_capabilities, burst_context):
    """仅派生训练输入；原来源、剩余控制结构及施法序列重置不变。"""
    from burst import _excluded
    policy = capabilities['burst_exclusions']
    actions = [*all_capabilities['actions'],
               *(command for block in burst_context['candidate']['blocks'] for command in block)]
    excluded = set(policy['actions']) | {action['simc_action'] for action in actions
                                        if _excluded(action, policy)}
    by_name = {action['simc_action']: action for action in actions}
    return filter_search_program(program, excluded,
        dict(all_capabilities, actions=list(by_name.values())))


def shared_scope(configuration_key):
    """训练和消费共用规则的三元身份，不把角色、引擎或目标数加入主键。"""
    if (not isinstance(configuration_key, dict) or set(configuration_key) != {
            'specialization_id', 'hero_talent', 'target_type'} or
            type(configuration_key['specialization_id']) is not int or
            configuration_key['specialization_id'] <= 0 or
            not isinstance(configuration_key['hero_talent'], str) or not configuration_key['hero_talent'] or
            configuration_key['target_type'] not in ('single_target', 'aoe')):
        raise ValueError('起点共享范围缺少有效专精、英雄天赋或目标类型')
    return 'scope-' + digest(configuration_key)




def _check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise TaskCancelled('任务已取消')


def semantic_versions():
    """共享准备及旧成果的语义版本；GA另有版本化清单。"""
    from search import SEARCH_ALGORITHM, STATS_VERSION
    from program import BEHAVIOR_IDENTITY_VERSION
    return dict(training=TRAINING_VERSION, search=SEARCH_ALGORITHM,
                statistics=STATS_VERSION, behavior=BEHAVIOR_IDENTITY_VERSION)


def training_condition_input(template_sha, engines, config, simulation_config, *, burst_context=None, rule_snapshot=None):
    """完整输入保留源码出处；执行并发不再直接决定成绩身份。"""
    from engine import ROOT, COMMON
    from task import _rule_hashes
    return dict(**(dict(rule_config_digest=rule_snapshot['rule_config_digest']) if rule_snapshot is not None else {}),
                       version=TRAINING_VERSION, template=template_sha, engines=engines,
                       config=config, simulation=simulation_config, retest=RETEST_SEEDS,
                       effective_options=COMMON, rules=_rule_hashes(relative_to=ROOT),
                       **(dict(task_category='burst_free_training', burst=burst_context)
                          if burst_context else {}))


def _identity_config(config):
    # 保留历史训练编号的固定日志字段；本次采集只读实际执行配置。
    legacy = dict(config, diagnostic_logging=True, diagnostics='summary', search_observability='off')
    return {key: value for key, value in legacy.items() if key not in ('max_processes', 'search_timeline')}


def semantic_condition(payload, versions):
    semantic = dict(payload, config=_identity_config(payload['config']), semantic_versions=versions)
    semantic.pop('rules')
    return digest(semantic)


def _checkpoint_states(batch):
    """只读原检查点，不创建 SQLite（轻量数据库）或改写业务记录。"""
    states = {}
    for path in sorted(Path(batch).glob('*/task.sqlite3')):
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as database:
            state = TaskStore.load_state(database)
            progress = database.execute('SELECT elapsed FROM runtime_progress WHERE id=1').fetchone()
            if progress:
                state['elapsed_seconds'] = max(state.get('elapsed_seconds', 0), progress[0])
            states[path.parent.name] = state
    return states


def _validate_identity(batch, manifest, current_input, *, processed=(), selected=()):
    """完整证明后才把旧条件视为同一语义的存储命名空间。"""
    try:
        payload, versions, condition = (manifest['condition_input'], manifest['semantic_versions'],
                                       manifest['condition'])
        from search import PREVIOUS_SEARCH_ALGORITHM
        expected_versions = semantic_versions()
        previous_versions = dict(expected_versions, search=PREVIOUS_SEARCH_ALGORITHM)
        # 仅核验原始完整成果时允许已支持的旧来源；新训练输入含冻结开关，不能借此续跑旧路径。
        compatible = versions == expected_versions or (versions == previous_versions and
            all(key not in current_input['config'] for key in
                ('rule_initialization_enabled', 'adaptive_selector_enabled')))
        if (manifest['format'] != 1 or not compatible or
                payload['version'] != versions['training'] or
                manifest['input_sha256'] != digest(payload) or
                manifest['semantic_condition'] != semantic_condition(payload, versions) or
                manifest['semantic_condition'] != semantic_condition(current_input, versions) or
                (Path(batch) / 'condition.txt').read_text(encoding='ascii') != condition or
                hashlib.sha256((Path(batch) / 'standard.simc').read_text(encoding='utf-8').encode()).hexdigest()
                != payload['template']):
            raise ValueError('训练语义身份、模板或原条件不一致')
        legacy = manifest.get('legacy_source_commit')
        if legacy:
            rules, current_rules = payload['rules'], current_input['rules']
            if (legacy != LEGACY_SOURCE_COMMIT or versions != LEGACY_SEMANTIC_VERSIONS or
                    digest(payload) != condition or set(rules) != set(current_rules)):
                raise ValueError('旧训练条件凭据缺失或不是已审核基线')
            proof = manifest.get('legacy_line_endings', {})
            if not isinstance(proof, dict) or set(proof) - set(LEGACY_LINE_ENDING_RULES):
                raise ValueError('旧训练源码换行凭据键不兼容')
            for key, value in rules.items():
                if key in proof:
                    from engine import ROOT
                    raw = (ROOT / key).read_bytes()
                    normalized = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                    if (proof[key] != dict(raw_sha256=value, normalized_sha256=LEGACY_LINE_ENDING_RULES[key]) or
                            hashlib.sha256(raw).hexdigest() != current_rules[key] or
                            hashlib.sha256(normalized).hexdigest() != LEGACY_LINE_ENDING_RULES[key]):
                        raise ValueError('旧训练源码换行凭据或当前内容不兼容: ' + key)
                elif value not in LEGACY_EXECUTION_RULES.get(key, (current_rules[key],)):
                    raise ValueError('旧训练源码凭据不兼容: ' + key)
        elif condition != manifest['semantic_condition']:
            raise ValueError('训练条件不是当前语义身份')
        states = _checkpoint_states(batch)
        for folder, state in states.items():
            if (state.get('training_condition') != condition or
                    state.get('training_candidate_id', '')[:12] != folder or
                    semantic_condition(dict(payload, config=state['config']), versions) !=
                    manifest['semantic_condition'] or state.get('burst') != payload.get('burst')):
                raise ValueError('训练检查点与完整条件凭据不一致: ' + folder)
        for row in processed:
            if row['condition'] == condition:
                folder = Path(row['task_path']).resolve()
                if folder.parent != Path(batch).resolve() or folder.name != row['candidate_id'][:12]:
                    raise ValueError('旧训练记录与批次目录不一致')
                if row['status'] != 'rejected' and (folder.name not in states or
                        states[folder.name]['training_candidate_id'] != row['candidate_id']):
                    raise ValueError('旧训练记录缺少原检查点')
        completed = {row['candidate_id']: row for row in processed
                     if row['condition'] == condition and row['status'] == 'completed'}
        for row in selected:
            if row['condition'] == condition:
                trained = completed.get(row['candidate_id'])
                if (trained is None or row['template_sha256'] != payload['template'] or
                        decode(row['engines']) != payload['engines'] or not any(
                            decode(row['program']) == decode(trained[program]) and row['scores'] == trained[scores]
                            for program, scores in [('program', 'scores'), ('initial_program', 'initial_scores')])):
                    raise ValueError('旧入选记录与原完成程序、复测成绩或条件凭据不一致')
        return manifest
    except (KeyError, TypeError, OSError, sqlite3.Error) as error:
        raise ValueError('训练条件凭据不完整: ' + str(error)) from error


def validate_training_identity(batch, template_sha, engines, config, simulation_config, *,
                               burst_context=None, processed=(), selected=(), rule_snapshot=None):
    """旧完整训练成果的只读核验，不放宽原评分批次验真。"""
    manifest = _read_identity(Path(batch) / 'identity.json')
    current_input = training_condition_input(template_sha, engines, config, simulation_config,
                                             burst_context=burst_context, rule_snapshot=rule_snapshot)
    return _validate_identity(batch, manifest, current_input, processed=processed, selected=selected)


def _read_identity(path):
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
        payload, versions = manifest['condition_input'], manifest['semantic_versions']
        if (manifest['format'] != 1 or not isinstance(manifest['executions'], list) or
                payload['version'] != versions['training'] or
                manifest['input_sha256'] != digest(payload) or
                manifest['semantic_condition'] != semantic_condition(payload, versions)):
            raise ValueError('训练身份清单损坏: ' + str(path))
        return manifest
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError('训练身份清单不完整: ' + str(path)) from error








def selected_materials(candidate_ids, *, sources=None):
    """只读取明确登记的材料，错误编号在启动计算前拒绝。"""
    sources = registry_rows() if sources is None else sources
    rows = []
    for candidate_id in dict.fromkeys(candidate_ids):
        matches = [row for row in sources if row['candidate_id'] == candidate_id]
        if len(matches) != 1:
            raise ValueError('训练材料不存在或不唯一: ' + candidate_id)
        if matches[0].get('semantic') == 'unsupported' or matches[0].get('active') is False:
            raise ValueError('不可表达材料不能用于训练: ' + candidate_id)
        rows.append(matches[0])
    if not rows:
        raise ValueError('至少指定一个训练材料')
    return rows


def _check_pretraining_observations(options):
    if (options.get('diagnostics') not in (None, 'off', 'summary')
            or options.get('search_observability') not in (None, 'off')):
        raise ValueError('预训练仅支持基础性能日志和时间DPS曲线，不支持完整事件或过程观测')


def _training_inputs(template, targets, *, cancel_event=None, use_burst=False, max_processes=None,
                     burst_identity=None, verified_engines=None, rule_snapshot=None, diagnostic_logging=False, search_config=None):
    from engine import identity
    _check_cancelled(cancel_event)
    if rule_snapshot is None:
        _check_pretraining_observations(search_config or {})
    if max_processes is None:
        from simulation_config import load_training_config
        max_processes = load_training_config()['max_processes']
    text = Path(template).read_text(encoding='utf-8')
    character = template_character(text)
    scope = f'{character.class_name}-{character.spec}-{targets}' + ('-burst' if use_burst else '')
    from simulation_config import load_search_config
    values = dict(search_config or {}, diagnostic_logging=diagnostic_logging,
        diagnostics='summary', max_processes=max_processes)
    if rule_snapshot is not None:
        values.setdefault('no_improvement_rounds', 2)  # Historical v1 identity only.
    # 仅旧完整成果重建原凭据时接受其内嵌配置，不读current职业规则。
    config = config_for(values if rule_snapshot is not None else load_search_config(**values),
                        training=True, legacy=rule_snapshot is not None)
    from dual_task import SCENES
    simulation_config = {'target_count': targets, 'enable_omnium_talents': True,
                         'scene': next((scene for scene, count in SCENES if count == targets), None)}
    engines = (verified_engines if verified_engines is not None else
               {mode: identity(mode)[1] for mode in ('baseline', 'controlled')})
    template_sha = hashlib.sha256(text.encode()).hexdigest()
    definition = None
    if use_burst:
        from burst import load, select_definition
        if burst_identity is None:
            definition = select_definition(character)
        else:
            definition = load(burst_identity['spec_id'])
            if definition['definition_id'] != burst_identity['definition_id']:
                raise ValueError('本次训练的爆发定义已变化，请重新准备')
            if (definition['class_key'] != character.class_name or definition['spec_key'] != character.spec):
                raise ValueError('当前标准角色职业或专精不适用冻结爆发定义')
        config = config_for(dict(config, input_interval_ms=200), training=True, legacy=rule_snapshot is not None)
    return dict(text=text, character=character, scope=scope, config=config, simulation_config=simulation_config,
                engines=engines, template_sha=template_sha, definition=definition, rule_snapshot=rule_snapshot)




def ensure_prepared(template, targets, workspace, *, cancel_event=None, use_burst=False,
                    materials=None, max_processes=None, inputs=None, sources=None, diagnostic_logging=False, search_config=None,
                    burst_identity=None):
    """run/prepare共用入口：完整快照原子保存成功后才返回可派发队列。"""
    from engine import reference, prepare_loop, configuration_key
    from program import canonicalize_search_program, _search_expanded_nodes, compile_program
    from codec import load_targeting, prepare_block, prepare_castsequence
    inputs = inputs or _training_inputs(template, targets, cancel_event=cancel_event, use_burst=use_burst,
                                       max_processes=max_processes, diagnostic_logging=diagnostic_logging, search_config=search_config,
                                       burst_identity=burst_identity)
    text, character, scope, config, simulation_config, engines, template_sha, definition = (
        inputs[name] for name in ('text', 'character', 'scope', 'config', 'simulation_config',
                                 'engines', 'template_sha', 'definition'))
    if materials is not None and any(row['class_name'] != character.class_name or
                                     row['spec'] != character.spec for row in materials):
        raise ValueError('训练材料与标准角色职业或专精不一致')
    preparation_input = dict(version=PREPARATION_VERSION, template=template_sha, engines=engines,
        simulation=simulation_config, definition=definition, semantics=semantic_versions(),
        config=_identity_config(config))
    config_key = digest(preparation_input)
    try:
        cached = result_store.read_records('seed_prepared', config_key)
    except result_store.InvalidRecordError:
        cached = []  # 明确损坏可重建；权限、存储及临时读失败仍直接报错。
    json_fields = ('program', 'core', 'initial_program', 'adaptation', 'context', 'representative_program')
    try:
        for row in cached:
            for name in json_fields:
                row[name] = decode(row.get(name))
    except (ValueError, TypeError):
        cached = []
    header = next((row for row in cached if row.get('kind') == 'context'), None)
    if (header is None or any(set(row) != set(PREPARED_SCHEMA) for row in cached)
            or header.get('version') != PREPARATION_VERSION
            or header.get('config_key') != config_key
            or header.get('checksum') != digest([{key: value for key, value in row.items()
                                                if key != 'checksum'} for row in cached])):
        cached, header = [], None
    sources = registry_rows() if sources is None else sources
    sources = [row for row in sources if row['class_name'] == character.class_name and row['spec'] == character.spec]
    active = [row for row in sources if row.get('active', True) and row['semantic'] != 'unsupported']
    context = header['context'] if header else None
    context_rebuilt = bool(active and context is None)
    runtime = TaskRuntime(600, cancel_event=cancel_event, diagnostic_logging=config['diagnostic_logging'])
    if context_rebuilt:
        setup = Path(workspace).resolve() / 'preparation' / config_key[:12] / uuid.uuid4().hex
        setup.mkdir(parents=True)
        profile = setup / 'standard.simc'
        profile.write_text(text, encoding='utf-8')
        native = reference(profile, setup / 'reference', character, runtime=runtime,
                           iterations=100, simulation_config=simulation_config)
        actual_character = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
        all_capabilities, capabilities, burst_context = prepare_loop(native, actual_character, setup, runtime,
                                                     definition=definition, interval_ms=config['input_interval_ms'])
        from engine import configuration_key
        scope_key = configuration_key(native, simulation_config.get('scene'))
        current_input = training_condition_input(template_sha, engines, config, simulation_config,
                                                 burst_context=burst_context, rule_snapshot=inputs['rule_snapshot'])
        reference_key = digest(dict(condition=semantic_condition(current_input, semantic_versions()),
                                    purpose='seed_reference'))
        result_store.write_batch(reference_key, dict(batch_key=reference_key, run_id=config_key,
            purpose='seed_reference', dps=native['dps'], samples=native['samples'],
            report=json.loads((setup / 'reference/native.json').read_text(encoding='utf-8'))),
            diagnostic_logging=config['diagnostic_logging'], runtime=runtime)
        (setup / 'reference/native.json').unlink()
        context = dict(native=native, all_capabilities=all_capabilities, capabilities=capabilities,
                       burst=burst_context, configuration_key=scope_key, representations={})
    if context:
        from engine import ROOT
        from task import _rule_hashes
        context = dict(context, preparation_input=preparation_input, rules=_rule_hashes(relative_to=ROOT),
                       configuration_key=configuration_key(context['native'], simulation_config.get('scene')))
    # 受检工具/目标资料加载失败是环境错误，不缓存为某条材料非法。
    target_masks = load_targeting(runtime=runtime)['target_masks'] if context else {}
    previous = {row['source_id']: row for row in cached if row.get('kind') == 'source'}
    entries, rebuilt = [], 0
    for source in sources:
        runtime.check()
        source = dict(source, program=decode(source['program']), core=decode(source['core']))
        program_revision = digest({key: source[key] for key in ('program', 'semantic', 'instructions', 'changes')})
        old = previous.get(source.get('source_id', source['candidate_id']))
        entry = dict.fromkeys(PREPARED_SCHEMA)
        entry.update(source, source_id=source.get('source_id', source['candidate_id']), kind='source',
                     config_key=config_key, version=PREPARATION_VERSION, program_revision=program_revision,
                     status='inactive', reason=source.get('unavailable_reason', ''), adaptation={},
                     initial_program=source['program'])
        if old and old['program_revision'] == program_revision:
            for key in ('initial_program', 'behavior_id', 'adaptation', 'reason'):
                entry[key] = old[key]
        if not source.get('active', True) or source['semantic'] == 'unsupported':
            entry['reason'] = source.get('unavailable_reason') or entry['reason'] or '; '.join(source['changes'])
        elif old and old['program_revision'] == program_revision:
            for key in ('initial_program', 'behavior_id', 'adaptation', 'reason'):
                entry[key] = old[key]
            entry['status'] = 'ready' if entry['behavior_id'] else 'rejected'
            if entry['status'] == 'ready':
                entry['reason'] = ''
        else:
            rebuilt += 1
            try:
                program, removed = (training_program(source['program'], context['capabilities'],
                                                    context['all_capabilities'], context['burst'])
                                    if context['burst'] else (source['program'], []))
                if removed:
                    entry['adaptation'] = dict(original_program=source['program'], removed=removed,
                        initial_core_retained=retains_core(program, source['core']))
                entry['initial_program'] = program
                if context['burst']:
                    for index, segment in enumerate(program if isinstance(program, list) else []):
                        if (removed and isinstance(segment, dict) and segment.get('kind') == 'CastSequence'
                                and len(segment['members']) == 1):
                            raise ValueError(f'segments[{index}]: 去除爆发动作后 /castsequence 仅剩一个成员，不能保持现有表达')
                    if not program or all(isinstance(segment, dict) and segment.get('kind') == 'WaitClicks'
                            and type(segment.get('clicks')) is int and 2 <= segment['clicks'] <= 4096
                            for segment in program):
                        raise ValueError('去除爆发动作后没有可训练的普通循环')
                prepared = canonicalize_search_program(program, context['capabilities'])
                for node in _search_expanded_nodes(prepared['program']):
                    if node['kind'] == 'Action':
                        commands = node['commands']
                        if len(commands) == 1 and commands[0].get('kind') == 'castsequence':
                            prepare_castsequence(commands[0])
                        else:
                            prepare_block(commands, target_masks)
            except ValueError as error:
                entry.update(status='rejected', reason=str(error))
            else:
                # 原编译工具及存储/环境错误直接终止准备，不将其缓存为非法材料。
                folder = Path(workspace).resolve() / 'preparation' / config_key[:12] / 'inputs' / source['candidate_id']
                compile_program(prepared['program'], folder,
                                identity=context['native']['identity'], runtime=runtime,
                                capabilities=context['capabilities'])
                entry.update(status='ready', behavior_id=prepared['identity'], reason='')
        if entry['adaptation']:
            entry['adaptation'] = dict(entry['adaptation'],
                initial_core_retained=retains_core(entry['initial_program'], source['core']))
        entries.append(entry)
    representations = dict(context['representations']) if context else {}
    groups = {}
    for entry in entries:
        if entry['status'] != 'ready':
            continue
        groups.setdefault(entry['behavior_id'], []).append(entry)
    queue = []
    for behavior_id, group in groups.items():
        representative = representations.get(behavior_id)
        if representative is None:
            first = min(group, key=lambda row: row['source_id'])
            representative = dict(candidate_id=first['candidate_id'], program=first['initial_program'])
            representations[behavior_id] = representative
        for entry in group:
            entry.update(representative_id=representative['candidate_id'],
                         representative_program=representative['program'])
        first = next((row for row in group if row['candidate_id'] == representative['candidate_id']), group[0])
        queue.append(dict(first, candidate_id=representative['candidate_id'], program=representative['program'],
                          sources=group))
    snapshot_entries = entries
    if materials is not None:
        wanted = {row['candidate_id'] for row in materials}
        entries = [dict(row) for row in entries if row['candidate_id'] in wanted]
        scoped_queue = []
        for row in queue:
            scoped_sources = [source for source in row['sources'] if source['candidate_id'] in wanted]
            if scoped_sources:
                first = min(scoped_sources, key=lambda source: source['source_id'])
                scoped_queue.append(dict(first, candidate_id=first['candidate_id'], program=first['initial_program'],
                                         sources=scoped_sources))
                for entry in entries:
                    if entry['behavior_id'] == row['behavior_id']:
                        entry.update(representative_id=first['candidate_id'],
                                     representative_program=first['initial_program'])
        queue = scoped_queue
    if context:
        context = dict(context, representations=representations,
            frozen_queue=[dict(candidate_id=row['candidate_id'], program=row['program'],
                               source_ids=sorted(source['source_id'] for source in row['sources'])) for row in queue])
    header = dict.fromkeys(PREPARED_SCHEMA)
    header.update(kind='context', config_key=config_key, version=PREPARATION_VERSION, context=context)
    snapshot = [header, *snapshot_entries]
    header['checksum'] = digest([{key: value for key, value in row.items() if key != 'checksum'}
                                for row in snapshot])
    _check_cancelled(cancel_event)
    if snapshot != cached:
        result_store.write('seed_prepared', config_key, snapshot, schema=PREPARED_SCHEMA)
    stats = dict(registry_sources=len(sources), active_sources=len(active),
                 original_unique=len({digest(row['program']) for row in active}), unique_inputs=len(queue),
                 rejected=sum(row['status'] == 'rejected' for row in entries),
                 sources_rebuilt=rebuilt, context_rebuilt=context_rebuilt)
    if runtime.diagnostic_logging:
        diagnostic_path = Path(workspace).resolve() / 'preparation' / config_key[:12] / 'diagnostics.json'
        try:
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostic_path.write_text(json.dumps(dict(performance=diagnostic_summary(runtime)),
                                                   ensure_ascii=False), encoding='utf-8')
        except (OSError, ValueError, TypeError):
            pass
    return dict(text=text, character=character, scope=scope, config=config, simulation_config=simulation_config,
                engines=engines, template_sha=template_sha, definition=definition, config_key=config_key,
                context=context, entries=entries, queue=queue, preparation=stats)




def _run_training(template, targets, workspace, *, cancel_event=None, use_burst=False, materials=None,
                  max_processes=None, max_trainings=None, prepare_only=False, sources=None, burst_identity=None,
                  diagnostic_logging=False, search_config=None, _timeline_origin=None, training_config=None,
                  expected_key=None):
    from population_training import run_group
    from simulation_config import load_training_config
    config = training_config or load_training_config(max_processes=max_processes, max_trainings=max_trainings)
    return run_group(template, targets, workspace, cancel_event=cancel_event or threading.Event(),
        use_burst=use_burst, sources=sources if sources is not None else registry_rows(), config=config,
        prepare_only=prepare_only, materials=materials, diagnostic_logging=diagnostic_logging,
        search_config=search_config, expected_key=expected_key, timeline_origin=_timeline_origin,
        burst_identity=burst_identity)


def run_training(template, targets, workspace, *, use_burst=False, max_processes=None, max_trainings=None,
                 diagnostic_logging=False, search_config=None):
    from seed_activity import training_activity
    from simulation_config import load_search_config
    search_config = load_search_config(**(search_config or {}))
    _check_pretraining_observations(search_config)
    timeline_origin = None
    if search_config['search_timeline']:
        from time import monotonic
        timeline_origin = monotonic()
    with writer_lock(), training_activity() as cancel_event:
        sources = sync_history(template_character(Path(template).read_text(encoding='utf-8')))
        return _run_training(template, targets, workspace, cancel_event=cancel_event, use_burst=use_burst,
                             max_processes=max_processes, max_trainings=max_trainings, sources=sources,
                             diagnostic_logging=diagnostic_logging, search_config=search_config, _timeline_origin=timeline_origin)


def check_training(template=None, *, use_burst=True, training_config=None):
    """只读冻结受检双英雄模板与四组三元范围，不启动原生计算。"""
    from engine import identity, training_templates
    from burst import select_definition, talent_hash
    from simulation_config import load_training_config
    paths = (Path(template).resolve(),) if template is not None else training_templates()
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    templates, groups = [], []
    for path in paths:
        if not path.is_file():
            raise ValueError('标准训练角色文件不存在: ' + str(path))
        text = path.read_text(encoding='utf-8')
        character = template_character(text)
        definition = select_definition(character) if use_burst else None
        row = dict(template=str(path), template_source='explicit' if template else 'current_build',
            template_sha256=hashlib.sha256(text.encode()).hexdigest(), talent_sha256=talent_hash(character),
            burst_definition_id=definition['definition_id'] if definition else None,
            burst_identity=dict(spec_id=definition['spec_id'], definition_id=definition['definition_id'])
                           if definition else None)
        templates.append(row)
        if template is None:
            hero = 'sanlayn' if "San'layn" in path.name else 'rider_of_the_apocalypse'
            for target in ('single_target', 'aoe'):
                groups.append(dict(template=str(path), configuration_key=dict(
                    specialization_id=252, hero_talent=hero, target_type=target)))
    config = load_training_config() if training_config is None else training_config
    return dict(status='ready', **templates[0], templates=templates, groups=groups,
        engines=engines, use_burst=use_burst, training_config=config,
        final_requested_iterations_per_group=config['top_k'] * 5 * config['retest_batches'] * config['retest_iterations'])


def selected_contract_version(rows):
    """缺版本是旧成果，不从TRAINING_VERSION或程序来源猜新契约。"""
    versions = {row.get('contract_version') if row.get('contract_version') is not None else 1 for row in rows}
    if any(type(version) is not int or version not in (1, 2) for version in versions) or len(versions) > 1:
        raise ValueError('不支持的训练成果契约版本')
    version = next(iter(versions), 1)
    if version == 2 and len(rows) != 4:
        raise ValueError('v2训练成果必须是完整四条')
    return version


def training_champion(class_name, spec, simulation_config, *, engines, input_interval_ms,
                      use_burst=False, burst_identity=None, rule_snapshot=None, configuration_key=None):
    """只读全部已完成最终成果及三份原复测，不训练、不补算、不改库。"""
    from program import canonicalize_search_program
    from search import _validate_saved_batch, STATS_VERSION
    from engine import player_report
    snapshot = dict(source_kind='training_champion', status='absent', excluded=[])
    if configuration_key is None:
        snapshot['reason'] = '训练冠军需要已验证三元共享范围'
        return snapshot
    scope = shared_scope(configuration_key)
    try:
        rows = result_store.read_records('seed_processed', scope)
    except result_store.InvalidRecordError as error:
        snapshot['excluded'].append(dict(status='invalid', reason=str(error)))
        return snapshot
    rows = [row for row in rows if row.get('status') == 'completed'
            and decode(row.get('configuration_key')) == configuration_key]
    batches, eligible = {}, []
    for row in rows:
        try:
            scores = row['scores']
            if (not isinstance(scores, list) or len(scores) != 3 or any(
                    type(score) not in (int, float) or not math.isfinite(score) or score <= 0 for score in scores)):
                raise ValueError('最终程序缺少三项有限有效复测成绩')
            folder = Path(row['task_path']).resolve()
            if folder.name != row['candidate_id'][:12]:
                raise ValueError('最终训练记录与原任务目录身份不符')
            batch = folder.parent
            if batch not in batches:
                manifest = _read_identity(batch / 'identity.json')
                payload = manifest['condition_input']
                source_rules = manifest.get('rule_snapshot')
                if source_rules is None:
                    raise ValueError('训练冠军缺少原规则身份快照')
                from legacy_training_rules import validate
                if (digest(source_rules['pack']) != source_rules['rule_config_digest'] or
                        validate(source_rules['pack']) != source_rules['resolved']):
                    raise ValueError('训练冠军原规则快照与摘要或解析结果不符')
                if rule_snapshot is not None and source_rules['rule_config_digest'] != rule_snapshot['rule_config_digest']:
                    raise ValueError('训练冠军原规则身份与当前配置不兼容')
                context = payload.get('burst')
                if bool(context) != use_burst:
                    raise ValueError('训练爆发模式不适用')
                inputs = _training_inputs(batch / 'standard.simc', payload['simulation']['target_count'],
                    use_burst=use_burst, verified_engines=payload['engines'], rule_snapshot=source_rules,
                    search_config=payload['config'])
                if (inputs['character'].class_name != class_name or inputs['character'].spec != spec or
                        payload['simulation'].get('scene') != configuration_key['target_type']):
                    raise ValueError('原训练角色或场景与共享范围不符')
                if context:
                    definition = inputs['definition']
                    if (context['definition_id'] != definition['definition_id'] or
                            dict(context['plan'], start_ms=definition['plan']['start_ms']) != definition['plan'] or
                            context['interval_ms'] != payload['config']['input_interval_ms']):
                        raise ValueError('原训练爆发内容或按法不适用')
                    if context['plan']['start_ms'] != definition['plan']['start_ms']:
                        alignment = context.get('initialization_alignment') or {}
                        if (alignment.get('rule_config_digest') != source_rules['rule_config_digest'] or
                                alignment.get('first_burst_ms') != context['plan']['start_ms'] or
                                alignment.get('plan_digest') != digest(context['plan']) or
                                alignment.get('opener_id') != digest(configuration_key)):
                            raise ValueError('原训练爆发首次时点缺少相符的冻结起手凭据')
                manifest = validate_training_identity(batch, inputs['template_sha'], payload['engines'],
                    payload['config'], payload['simulation'], burst_context=context,
                    rule_snapshot=source_rules)
                batches[batch] = manifest, inputs
            manifest, inputs = batches[batch]
            source_simulation = manifest['condition_input']['simulation']
            source_interval = manifest['condition_input']['config']['input_interval_ms']
            source_engines = manifest['condition_input']['engines']
            if row['condition'] != manifest['condition']:
                raise ValueError('最终训练记录与完整条件凭据不符')
            checkpoint = folder / 'task.sqlite3'
            checkpoint.stat()  # 缺失和权限/磁盘故障不能混为一类。
            with sqlite3.connect(checkpoint.as_uri() + '?mode=ro', uri=True) as database:
                state = TaskStore.load_state(database)
                if (state.get('training_candidate_id') != row['candidate_id'] or
                        state.get('training_condition') != row['condition']):
                    raise ValueError('最终训练记录缺少相符的原检查点')
                from legacy_training_rules import bind
                initialization = state.get('rule_context') or state.get('rule_initialization') or {}
                source_key = bind(state['capabilities'], initialization.get('static_snapshot'),
                    source_simulation['target_count'], spec_id=configuration_key['specialization_id'],
                    rule_snapshot=manifest['rule_snapshot'], scene=source_simulation.get('scene'))['configuration_key']
                if source_key != configuration_key or initialization.get('configuration_key') != source_key:
                    raise ValueError('原训练英雄身份与共享范围不符')
                program = decode(row['program'])
                form = canonicalize_search_program(program, state['capabilities'])['form']
                character = inputs['character']
                context = manifest['condition_input'].get('burst')
                times = list(range(0, 180000, source_interval))
                if context:
                    from burst import combined_inputs
                    times, _ = combined_inputs(times, context, source_interval)
                evidence = []
                for index, (seed, score) in enumerate(zip(RETEST_SEEDS, scores)):
                    key = digest(dict(folder=str(folder / 'retest-final'), seed=seed))
                    receipt = database.execute('SELECT value FROM batches WHERE key=?', (key,)).fetchone()
                    if receipt is None:
                        raise FileNotFoundError('最终复测请求凭据缺失: ' + key)
                    cached = json.loads(receipt[0])
                    request = dict(condition=row['condition'], program=form, behavior_identity=digest(form),
                        purpose='seed_retest', seed=seed, input_seed=seed, iterations=128, times=times,
                        stats=STATS_VERSION, trace=False, reset_events=[])
                    if (not isinstance(cached, dict) or cached.get('status') != 'success' or cached.get('request') != request or
                            cached.get('data_key') != key or cached.get('requested_iterations') != 128 or
                            cached.get('dps') != score or cached.get('samples', 0) < 2):
                        raise ValueError('最终复测请求、程序、条件、种子或128次样本规则不符')
                    group = cached.get('storage_group_key')
                    if group is not None and not isinstance(group, str):
                        raise ValueError('最终复测报告位置凭据无效')
                    group = group or key
                    saved = result_store.one('batches', 'batch_key', key, group_key=group)
                    if saved is None:
                        raise FileNotFoundError('最终复测报告缺失: ' + key)
                    if decode(saved.get('engines')) != source_engines or saved.get('requested_iterations') != 128:
                        raise ValueError('最终复测引擎或128次样本规则不符')
                    player = player_report(saved['report'], inputs['character'])
                    report_key = bind(state['capabilities'], player.get('sim2gse_static_snapshot'),
                        source_simulation['target_count'], spec_id=player.get('sim2gse_spec_id'),
                        rule_snapshot=manifest['rule_snapshot'], scene=source_simulation.get('scene'))['configuration_key']
                    if report_key != source_key:
                        raise ValueError('原复测英雄身份与训练共享范围不符')
                    if (player.get('sim2gse_spec') != spec or player.get('race') != inputs['character'].race or
                            type(player.get('sim2gse_spec_id')) is not int or player['sim2gse_spec_id'] <= 0 or
                            character.spec_id not in (None, player['sim2gse_spec_id']) or
                            player['sim2gse_spec_id'] != configuration_key['specialization_id']):
                        raise ValueError('最终复测标准角色身份不符')
                    if character.spec_id is None:
                        character = replace(character, spec_id=player['sim2gse_spec_id'])
                    _validate_saved_batch(saved, key, cached, character, index, 'nominal', source_simulation)
                    evidence.append(dict(batch_key=key, storage_group_key=group, seed=seed,
                                         requested_iterations=128, samples=cached['samples']))
            eligible.append(dict(configuration_key=configuration_key, source_kind='training_champion', status='selected',
                candidate_id=row['candidate_id'], phase='final', program=program, program_identity=form,
                scores=scores, score=sum(scores) / 3, condition=row['condition'],
                semantic_condition=manifest['semantic_condition'], condition_input=manifest['condition_input'],
                semantic_versions=manifest['semantic_versions'], template_sha256=inputs['template_sha'],
                engines=source_engines, class_name=class_name, spec=spec, targets=source_simulation['target_count'],
                task_path=str(folder), identity_path=str(batch / 'identity.json'), evidence=evidence))
        except (ValueError, KeyError, TypeError, FileNotFoundError, result_store.InvalidRecordError,
                sqlite3.Error) as error:
            cause = error
            while cause.__cause__ is not None:
                cause = cause.__cause__
            corrupt_sqlite = isinstance(cause, sqlite3.DatabaseError) and any(
                text in str(cause).lower() for text in ('malformed', 'not a database'))
            if ((isinstance(cause, OSError) and not isinstance(cause, FileNotFoundError)) or
                    (isinstance(cause, sqlite3.Error) and not corrupt_sqlite)):
                raise result_store.DataReadError('训练冠军原凭据暂时不可读: ' + str(cause)) from error
            snapshot['excluded'].append(dict(candidate_id=row.get('candidate_id'),
                status='missing' if isinstance(cause, FileNotFoundError) else 'invalid', reason=str(error)))
        except OSError as error:
            raise result_store.DataReadError('训练冠军原凭据暂时不可读: ' + str(error)) from error
    if eligible:
        # 历史DPS仅用于选择起点来源；当前角色和引擎仍须适配并重新评分。
        winner = min(eligible, key=lambda item: (-item['score'], digest(item['program']), item['candidate_id']))
        snapshot.update(winner)
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description='人工清洗件登记与起点预训练')
    parser.add_argument('--project', type=Path, required=True, help='已接入的共享数据中心所属项目')
    commands = parser.add_subparsers(dest='command', required=True)
    registration = commands.add_parser('register', help='登记人工清洗件')
    registration.add_argument('input', type=Path)
    listing = commands.add_parser('list', help='读取中心中的起点记录')
    listing.add_argument('--state', choices=('pending', 'selected', 'processed', 'unsupported', 'prepared'), default='pending')
    listing.add_argument('--config-key', help='prepared快照标识，由prepare/run返回')
    listing.add_argument('--targets', type=int, choices=(1, 5), default=1)
    listing.add_argument('--class-name', default='deathknight')
    listing.add_argument('--spec', default='unholy')
    listing.add_argument('--specialization-id', type=int)
    listing.add_argument('--hero-talent')
    listing.add_argument('--target-type', choices=('single_target', 'aoe'))
    training = commands.add_parser('run', help='种群预训练至连续两代无改善、五场景复测与更新')
    preparing = commands.add_parser('prepare', help='统一增量整理并冻结唯一输入，不启动优化或复测')
    for command_parser in (training, preparing):
        from simulation_config import add_search_arguments
        add_search_arguments(command_parser)
        command_parser.add_argument('--diagnostic-logging', action='store_true',
                                    help='本次开启基础性能日志；恢复预训练可按本次设置切换')
        command_parser.add_argument('--template', type=Path, help='明确角色文件；默认使用当前受检构建的标准角色')
        command_parser.add_argument('--targets', type=int, nargs='+', choices=(1, 5), default=[1, 5])
        command_parser.add_argument('--candidate-id', action='append', help='只训练指定登记材料；可重复传入，默认全部')
        command_parser.add_argument('--max-processes', type=int, choices=range(1, 17),
                          help='覆盖每组原生评分并发（缺省5）；与组并发乘积≤20')
        command_parser.add_argument('--max-trainings', type=int, choices=range(1, 11),
                          help='覆盖分组并发（缺省4）；与原生评分并发乘积≤20')
        command_parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[2] /
                          '.local/sim2gse/seed-training')
    checking = commands.add_parser('check', help='只读核对训练模板、引擎与审核适用性，不启动计算')
    checking.add_argument('--template', type=Path)
    for command_parser in (training, preparing, checking, listing):
        mode = command_parser.add_mutually_exclusive_group()
        mode.add_argument('--use-burst', dest='use_burst', action='store_true', help='独立爆发模式（默认）')
        mode.add_argument('--legacy', dest='use_burst', action='store_false', help='显式无独立爆发；run仍仅执行GA')
        command_parser.set_defaults(use_burst=True)
    args = parser.parse_args(argv)
    try:
        result_store.bind_project(args.project)
        result_store.ensure_available()
        if args.command == 'register':
            output = register(args.input)
        elif args.command == 'check':
            output = check_training(args.template, use_burst=args.use_burst)
        elif args.command in ('run', 'prepare'):
            from simulation_config import load_search_config
            search_config = load_search_config(search_timeline=args.search_timeline)
            timeline_origin = None
            if args.command == 'run' and search_config['search_timeline']:
                from time import monotonic
                timeline_origin = monotonic()
            from simulation_config import load_training_config
            parallelism = load_training_config(max_processes=args.max_processes, max_trainings=args.max_trainings)
            max_processes = parallelism['max_processes']
            from seed_activity import training_activity
            with writer_lock():
                sources = registry_rows()
                if args.candidate_id:
                    selected_materials(args.candidate_id, sources=sources)  # 明显非法编号不依赖模板或引擎。
                ready = check_training(args.template, use_burst=args.use_burst, training_config=parallelism)
                with training_activity() as cancel_event:
                    sources = sync_history(template_character(Path(ready['template']).read_text(encoding='utf-8')),
                                           sources=sources)
                    material_options = ({'materials': selected_materials(args.candidate_id, sources=sources)}
                                        if args.candidate_id else {})
                    jobs = [(row, targets) for row in ready['templates'] for targets in dict.fromkeys(args.targets)]
                    output, errors = [], []
                    from population_training import group_configs, group_workers
                    configs = group_configs(args.workspace, ready['templates'], parallelism, args.targets)
                    workers = group_workers(args.workspace, ready['templates'], parallelism, args.targets,
                                            effective_configs=configs)
                    if args.command == 'run':
                        for row, targets in jobs:
                            config = configs[(str(Path(row['template']).resolve()), targets)]
                            batches = config['top_k'] * 5 * config['retest_batches']
                            print(f"{Path(row['template']).name}/{targets}：五场景复测最多"
                                  f"{config['top_k']}候选、{batches}请求批、"
                                  f"{batches * config['retest_iterations']}请求迭代（非实际有效样本）；"
                                  f"本次分组并发上限{workers}", file=sys.stderr, flush=True)
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = []
                        for row, targets in jobs:
                            expected = next((group['configuration_key'] for group in ready['groups']
                                if group['template'] == row['template'] and group['configuration_key']['target_type'] ==
                                ('single_target' if targets == 1 else 'aoe')), None)
                            futures.append(pool.submit(_run_training, Path(row['template']), targets, args.workspace,
                                cancel_event=cancel_event, use_burst=args.use_burst,
                                prepare_only=args.command == 'prepare', sources=sources,
                                training_config=parallelism, expected_key=expected, burst_identity=row['burst_identity'],
                                diagnostic_logging=args.diagnostic_logging, search_config=search_config,
                                _timeline_origin=timeline_origin, **material_options))
                        # Deterministic result order; one group's failure never cancels another group.
                        try:
                            for (row, targets), future in zip(jobs, futures):
                                try:
                                    output.append(future.result())
                                except (ValueError, OSError, RuntimeError) as error:
                                    output.append(dict(status='paused', template=row['template'], targets=targets, error=str(error)))
                                    errors.append(Path(row['template']).name + '/' + str(targets) + ': ' + str(error))
                        except KeyboardInterrupt as error:
                            cancel_event.set()
                            raise TaskCancelled('任务已取消；等待所属评价刷尾并保存暂停') from error
                    if errors:
                        print(json.dumps(output, ensure_ascii=False))
                        raise ValueError('; '.join(errors))
        elif args.state == 'prepared':
            if not args.config_key:
                raise ValueError('读取准备快照必须指定--config-key')
            output = result_store.read_records('seed_prepared', args.config_key)
        elif args.state in ('pending', 'unsupported'):
            output = [row for row in result_store.read_records('seed_candidates', 'registry')
                      if (row['semantic'] == 'unsupported' or row.get('active') is False) == (args.state == 'unsupported')]
        else:
            key = (shared_scope(dict(specialization_id=args.specialization_id,
                   hero_talent=args.hero_talent, target_type=args.target_type))
                   if any(value is not None for value in (args.specialization_id, args.hero_talent, args.target_type))
                   else f'{args.class_name}-{args.spec}-{args.targets}' + ('-burst' if args.use_burst else ''))
            output = result_store.read_records('seed_' + args.state, key)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
