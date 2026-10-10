"""Manually launched seed preparation; all business records use the shared center."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
import msvcrt
from pathlib import Path
import sqlite3
import sys
import uuid

import result_store
from search import digest, config_for, TaskStore, optimize, summarize_pairs
from runtime import TaskRuntime, BudgetExceeded, TaskCancelled

CANDIDATE_SCHEMA = dict(candidate_id='VARCHAR', label='VARCHAR', class_name='VARCHAR',
    spec='VARCHAR', source='VARCHAR', original='VARCHAR', instructions='VARCHAR',
    semantic='VARCHAR', changes='VARCHAR[]', family='VARCHAR', core='JSON', program='JSON')
PROCESSED_SCHEMA = dict(candidate_id='VARCHAR', condition='VARCHAR', status='VARCHAR',
    error='VARCHAR', initial_program='JSON', program='JSON', family='VARCHAR', core_retained='BOOLEAN',
    rounds='UBIGINT', stop_reason='VARCHAR', elapsed_seconds='DOUBLE', scores='DOUBLE[]',
    initial_scores='DOUBLE[]', comparison='JSON', task_path='VARCHAR', native_batch_starts='UBIGINT',
    batch_requests='UBIGINT', cache_hits='UBIGINT')
SELECTED_SCHEMA = dict(candidate_id='VARCHAR', condition='VARCHAR', class_name='VARCHAR',
    spec='VARCHAR', targets='UBIGINT', program='JSON', family='VARCHAR', score='DOUBLE',
    scores='DOUBLE[]', template_sha256='VARCHAR', engines='JSON')
RETEST_SEEDS = (20261008, 20261009, 20261010)
TRAINING_VERSION = 'seed-training-v2'
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
    required = set(CANDIDATE_SCHEMA) - {'candidate_id'}
    if not isinstance(row, dict) or set(row) != required:
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
    row['candidate_id'] = digest(row)
    with writer_lock():
        rows = result_store.read_records('seed_candidates', 'registry')
        if not any(item['candidate_id'] == row['candidate_id'] for item in rows):
            for item in rows:
                item['program'], item['core'] = decode(item['program']), decode(item['core'])
            result_store.write('seed_candidates', 'registry', rows + [row], schema=CANDIDATE_SCHEMA)
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


def history_candidates(character):
    # Query only the existing logical table; absence is distinct from a failed read.
    with result_store.query("SELECT table_name FROM information_schema.tables WHERE table_name='runs'") as cursor:
        if not cursor.fetchone():
            return []
    rows = []
    for run in result_store.iter_rows("SELECT run_id, profile, candidate_data_key, search_dps FROM runs "
                                     "WHERE candidate_data_key IS NOT NULL AND search_dps > 0"):
        profile = decode(run['profile'])
        identity = profile.get('identity', {})
        if identity.get('class') != character.class_name or identity.get('spec') != character.spec:
            continue
        candidate = result_store.one('candidates', 'candidate_data_key', run['candidate_data_key'])
        if candidate is None:
            raise ValueError('历史最佳候选记录缺失: ' + run['run_id'])
        shared = decode(candidate['program'])
        try:
            program = search_program(shared)
        except ValueError:
            # Retain original history; never convert unsupported semantics silently.
            program = shared
        rows.append(dict(candidate_id=digest(dict(history=run['run_id'], program=program)),
                         label=run['run_id'], class_name=character.class_name, spec=character.spec,
                         source='history:' + run['run_id'], program=program, family='history-search', core=[]))
    return rows


def retest(profile, program, character, capabilities, native, folder, simulation_config, *,
           engines, condition, runtime=None, burst_context=None):
    from program import from_search_program, compile_program
    from sequence import evaluate, compiled_identity
    runtime = runtime or TaskRuntime(600)
    runtime.check()
    compiled = compile_program(from_search_program(program, capabilities), folder / 'export',
                               identity=native['identity'], runtime=runtime, capabilities=capabilities)
    scores = []
    interval_ms = burst_context['interval_ms'] if burst_context else 300
    times = list(range(0, 180000, interval_ms))
    burst_options = {}
    if burst_context is not None:
        from burst import combined_inputs
        times, sources = combined_inputs(times, burst_context, interval_ms)
        burst_options = dict(input_sources=sources, burst_candidate=burst_context['candidate'])
    for seed in RETEST_SEEDS:
        runtime.check()
        result = evaluate(profile, compiled, folder / str(seed), character=character, iterations=128,
                          seed=seed, trace=False, input_times=times,
                          simulation_config=simulation_config, runtime=runtime, **burst_options)
        runtime.check()
        summary = result['summary']
        if summary['samples'] < 2 or not math.isfinite(summary['dps']) or summary['dps'] <= 0:
            raise ValueError('复测没有完整有效成绩')
        scores.append(summary['dps'])
        result_store.write_batch(digest(dict(folder=str(folder), seed=seed)), dict(
            batch_key=digest(dict(folder=str(folder), seed=seed)), run_id=folder.parent.name,
            purpose='seed_retest', seed=seed, samples=summary['samples'], dps=summary['dps'],
            requested_iterations=128, engines=engines, condition_key=condition,
            program_identity=compiled_identity(compiled),
            report=result['report']))
        (folder / str(seed) / 'native.json').unlink(missing_ok=True)
    return scores


def retains_core(program, core):
    if not core:
        return False
    # Exact grouped fragment; no frequency-based or cyclic-rotation equivalence.
    return any(program[index:index + len(core)] == core for index in range(len(program)))


def training_program(program, capabilities, all_capabilities, burst_context):
    """仅派生训练输入；原来源、剩余控制结构及施法序列重置不变。"""
    from burst import _excluded
    from program import from_search_program
    policy = capabilities['burst_exclusions']
    actions = [*all_capabilities['actions'],
               *(command for block in burst_context['candidate']['blocks'] for command in block)]
    excluded = set(policy['actions']) | {action['simc_action'] for action in actions
                                        if _excluded(action, policy)}
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
            # 删除前用既有解析核对成员和reset，不能删除后掩盖无效定义。
            by_name = {action['simc_action']: action for action in actions}
            from_search_program([segment], dict(all_capabilities, actions=list(by_name.values())))
            members = keep(segment['members'], path + '.members')
            if members:
                output.append(dict(segment, members=members))
        else:
            output.append(segment)
    return output, removed


def publish_records(processed, selected, *, condition, character, targets, template_sha, engines, capabilities=None):
    """Rebuild from committed outcomes so a failed final publish is retryable."""
    options = []
    for row in processed:
        if row['condition'] != condition or row['status'] != 'completed':
            continue
        final_family = row['family'] if row['core_retained'] else 'history-search'
        adaptation = decode(row['comparison']).get('adaptation', {})
        initial_family = ('history-search' if adaptation.get('initial_core_retained') is False
                          else row['family'])
        for program, scores, family in (
                (decode(row['program']), row['scores'], final_family),
                (decode(row['initial_program']), row['initial_scores'], initial_family)):
            if capabilities is not None:
                from program import canonicalize_search_program
                canonicalize_search_program(program, capabilities)
            options.append(dict(candidate_id=row['candidate_id'], condition=condition,
                                class_name=character.class_name, spec=character.spec, targets=targets,
                                program=program, family=family, score=sum(scores) / len(scores),
                                scores=scores, template_sha256=template_sha, engines=engines))
    for option in sorted(options, key=lambda item: (-item['score'], digest(item['program']))):
        incumbent = next((item for item in selected if item['family'] == option['family']), None)
        if incumbent is None or summarize_pairs(
                [{'dps': value} for value in option['scores']],
                [{'dps': value} for value in incumbent['scores']])['status'] == 'improvement_confirmed':
            selected = [item for item in selected if item['family'] != option['family']] + [option]
    unique = {}
    for item in sorted(selected, key=lambda item: (-item['score'], item['candidate_id'])):
        item['program'], item['engines'] = decode(item['program']), decode(item['engines'])
        if capabilities is not None:
            from program import canonicalize_search_program
            canonicalize_search_program(item['program'], capabilities)
        unique.setdefault(digest(item['program']), item)
    return list(unique.values())[:4]


def _check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise TaskCancelled('任务已取消')


def semantic_versions():
    """改变训练、搜索、统计或行为语义时，须递增其既有版本。"""
    from search import SEARCH_ALGORITHM, STATS_VERSION
    from program import BEHAVIOR_IDENTITY_VERSION
    return dict(training=TRAINING_VERSION, search=SEARCH_ALGORITHM,
                statistics=STATS_VERSION, behavior=BEHAVIOR_IDENTITY_VERSION)


def training_condition_input(template_sha, engines, config, simulation_config, *, burst_context=None):
    """完整输入保留源码出处；执行并发不再直接决定成绩身份。"""
    from engine import ROOT, COMMON
    from task import _rule_hashes
    return dict(version=TRAINING_VERSION, template=template_sha, engines=engines,
                       config=config, simulation=simulation_config, retest=RETEST_SEEDS,
                       effective_options=COMMON, rules=_rule_hashes(relative_to=ROOT),
                       **(dict(task_category='burst_free_training', burst=burst_context)
                          if burst_context else {}))


def semantic_condition(payload, versions):
    semantic = dict(payload, config={key: value for key, value in payload['config'].items()
                                    if key != 'max_processes'}, semantic_versions=versions)
    semantic.pop('rules')
    return digest(semantic)


def training_condition(template_sha, engines, config, simulation_config, *, burst_context=None):
    """训练与升级核验共用的语义条件计算；不启动计算、不读取历史。"""
    return semantic_condition(training_condition_input(template_sha, engines, config, simulation_config,
                              burst_context=burst_context), semantic_versions())


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


def _validate_identity(batch, manifest, current_input, *, processed=(), selected=(), adopting=False):
    """完整证明后才把旧条件视为同一语义的存储命名空间。"""
    try:
        payload, versions, condition = (manifest['condition_input'], manifest['semantic_versions'],
                                       manifest['condition'])
        if (manifest['format'] != 1 or versions != semantic_versions() or
                payload['version'] != versions['training'] or
                manifest['input_sha256'] != digest(payload) or
                manifest['semantic_condition'] != semantic_condition(payload, versions) or
                manifest['semantic_condition'] != semantic_condition(current_input, semantic_versions()) or
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
                    manifest['semantic_condition'] or state.get('burst') != payload.get('burst') or
                    (adopting and digest(state['config']) != digest(payload['config']))):
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
                               burst_context=None, processed=(), selected=()):
    """升级后核查与训练入口共用的只读核验，不放宽原评分批次验真。"""
    manifest = _read_identity(Path(batch) / 'identity.json')
    current_input = training_condition_input(template_sha, engines, config, simulation_config,
                                             burst_context=burst_context)
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


@writer_lock()
def adopt_legacy_condition(batch, evidence, *, processed, selected, source_root=None):
    """仅为已核对的 be350 批次补出处清单；不改旧检查点、成绩或请求键。"""
    from engine import identity
    from task import _write_json
    batch = Path(batch)
    if (batch / 'identity.json').exists():
        raise ValueError('该训练批次已有身份清单，不能覆盖')
    required = {'version', 'template', 'engines', 'config', 'simulation', 'retest', 'effective_options', 'rules'}
    if (not isinstance(evidence, dict) or not isinstance(evidence.get('condition_input'), dict) or
            set(evidence['condition_input']) not in (required, required | {'task_category', 'burst'}) or
            evidence.get('source_commit') != LEGACY_SOURCE_COMMIT or
            evidence.get('semantic_versions') != LEGACY_SEMANTIC_VERSIONS):
        raise ValueError('旧训练完整输入、来源或语义版本凭据缺失')
    payload, versions = evidence['condition_input'], evidence['semantic_versions']
    manifest = dict(format=1, condition=digest(payload), condition_input=payload, input_sha256=digest(payload),
        semantic_versions=versions, semantic_condition=semantic_condition(payload, versions),
        legacy_source_commit=evidence['source_commit'], executions=[])
    if source_root is not None:
        proof = {}
        try:
            for key, expected in LEGACY_LINE_ENDING_RULES.items():
                raw = (Path(source_root) / key).read_bytes()
                raw_sha = hashlib.sha256(raw).hexdigest()
                normalized_sha = hashlib.sha256(raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')).hexdigest()
                if raw_sha != payload['rules'].get(key) or normalized_sha != expected:
                    raise ValueError('原训练源码不匹配旧凭据或固定基线: ' + key)
                proof[key] = dict(raw_sha256=raw_sha, normalized_sha256=normalized_sha)
        except OSError as error:
            raise ValueError('原训练源码缺失或不可读: ' + str(error)) from error
        manifest['legacy_line_endings'] = proof
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    current_input = training_condition_input(payload['template'], engines, payload['config'],
        payload['simulation'], burst_context=payload.get('burst'))
    _validate_identity(batch, manifest, current_input, processed=processed, selected=selected, adopting=True)
    if not any(row['condition'] == manifest['condition'] for row in processed):
        raise ValueError('旧批次没有相符的原处理记录')
    manifest['executions'].append(dict(origin='legacy_checkpoint', config=payload['config'],
        rules=payload['rules'], candidates={key: _execution_state(state)
                                           for key, state in _checkpoint_states(batch).items()}))
    _write_json(batch / 'identity.json', manifest, atomic=True)
    return manifest


def _execution_state(state):
    return {key: state.get(key) for key in ('phase', 'rounds', 'elapsed_seconds',
            'native_batch_starts', 'batch_requests', 'batch_cache_hits')}


def _write_execution(batch, manifest, candidate_id, config, state):
    from engine import ROOT
    from task import _rule_hashes, _write_json
    segment = dict(candidate_id=candidate_id, started_at=datetime.now(timezone.utc).isoformat(),
                   config=dict(config), rules=_rule_hashes(relative_to=ROOT),
                   before=_execution_state(state))
    manifest['executions'].append(segment)
    _write_json(batch / 'identity.json', manifest, atomic=True)
    return segment


def selected_materials(candidate_ids):
    """只读取明确登记的材料，错误编号在启动计算前拒绝。"""
    rows = []
    for candidate_id in dict.fromkeys(candidate_ids):
        matches = result_store.read_records('seed_candidates', 'registry',
                                            filters={'candidate_id': candidate_id})
        if len(matches) != 1:
            raise ValueError('训练材料不存在或不唯一: ' + candidate_id)
        if matches[0].get('semantic') == 'unsupported':
            raise ValueError('不可表达材料不能用于训练: ' + candidate_id)
        rows.append(matches[0])
    if not rows:
        raise ValueError('至少指定一个训练材料')
    return rows


def _run_training(template, targets, workspace, *, cancel_event=None, use_burst=False, materials=None,
                  max_processes=None):
    from engine import identity, reference, prepare_loop
    from program import canonicalize_search_program
    _check_cancelled(cancel_event)
    if max_processes is None:
        from simulation_config import load_training_config
        max_processes = load_training_config()['max_processes']
    text = template.read_text(encoding='utf-8')
    character = template_character(text)
    if materials is not None and any(row['class_name'] != character.class_name or
                                     row['spec'] != character.spec for row in materials):
        raise ValueError('训练材料与标准角色职业或专精不一致')
    scope = f'{character.class_name}-{character.spec}-{targets}' + ('-burst' if use_burst else '')
    config = config_for({'diagnostic_logging': True, 'diagnostics': 'summary',
                         'no_improvement_rounds': 2, 'max_processes': max_processes}, training=True)
    simulation_config = {'target_count': targets, 'enable_omnium_talents': True}
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    burst_context = None
    capabilities = None
    definition = None
    processed = result_store.read_records('seed_processed', scope)
    all_selected = result_store.read_records('seed_selected', scope)
    template_sha = hashlib.sha256(text.encode()).hexdigest()
    if use_burst:
        from burst import select_definition
        definition = select_definition(character)
        config = config_for(dict(config, input_interval_ms=200), training=True)
    matches = []
    for path in (workspace.resolve() / str(targets)).glob('*/condition.txt'):
        if not path.with_name('identity.json').exists() and any(
                row['condition'] == path.read_text(encoding='ascii') for row in processed):
            old_profile = path.with_name('standard.simc')
            if (not old_profile.is_file() or hashlib.sha256(
                    old_profile.read_text(encoding='utf-8').encode()).hexdigest() == template_sha):
                raise ValueError('同模板旧训练批次缺少完整身份凭据，请先核验原条件: ' + str(path.parent))
    for path in sorted((workspace.resolve() / str(targets)).glob('*/identity.json')):
        manifest = _read_identity(path)
        stored_burst = manifest['condition_input'].get('burst')
        if bool(stored_burst) != use_burst or (use_burst and
                stored_burst['definition_id'] != definition['definition_id']):
            continue
        current_input = training_condition_input(template_sha, engines, config, simulation_config,
                                                 burst_context=stored_burst)
        if semantic_condition(current_input, semantic_versions()) == manifest['semantic_condition']:
            _validate_identity(path.parent, manifest, current_input,
                               processed=processed, selected=all_selected)
            matches.append((path.parent, manifest))
    if len(matches) > 1:
        raise ValueError('同一训练语义存在多个批次，必须明确保留一个运行目录')
    batch, manifest = matches[0] if matches else (None, None)
    if manifest:
        burst_context = manifest['condition_input'].get('burst')
        states = _checkpoint_states(batch)
        capabilities = next((state['capabilities'] for state in states.values() if 'capabilities' in state), None)
    # 完整成绩复用先核验身份，再决定是否需要启动参考计算。
    condition = manifest['condition'] if manifest else None
    completed = {row['candidate_id'] for row in processed
                 if row['condition'] == condition and row['status'] in ('completed', 'rejected')}
    candidates = (materials if materials is not None else
                  result_store.read_records('seed_candidates', 'registry') + history_candidates(character))
    _check_cancelled(cancel_event)
    candidates = [row for row in candidates if row.get('semantic') != 'unsupported' and
                  row['class_name'] == character.class_name and
                  row['spec'] == character.spec and row['candidate_id'] not in completed]
    if use_burst and candidates:
        setup = workspace.resolve() / 'burst-setup' / uuid.uuid4().hex
        setup.mkdir(parents=True)
        setup_profile = setup / 'standard.simc'
        setup_profile.write_text(text, encoding='utf-8')
        setup_runtime = TaskRuntime(600, cancel_event=cancel_event)
        native = reference(setup_profile, setup / 'reference', character, runtime=setup_runtime,
                           iterations=100, simulation_config=simulation_config)
        character = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
        all_capabilities, capabilities, burst_context = prepare_loop(native, character, setup, setup_runtime,
                                                      definition=definition, interval_ms=config['input_interval_ms'])
    current_input = training_condition_input(template_sha, engines, config, simulation_config,
                                             burst_context=burst_context)
    if manifest:
        _validate_identity(batch, manifest, current_input, processed=processed, selected=all_selected)
    else:
        condition = semantic_condition(current_input, semantic_versions())
        batch = workspace.resolve() / str(targets) / condition[:12]
        manifest = dict(format=1, condition=condition, condition_input=current_input, input_sha256=digest(current_input),
                        semantic_versions=semantic_versions(), semantic_condition=condition, executions=[])
    selected = [row for row in all_selected if row['condition'] == condition]
    if not candidates:
        status = 'unchanged'
        _check_cancelled(cancel_event)
        if not any(row['condition'] == condition and row['status'] == 'failed' for row in processed):
            restored = publish_records(processed, selected, condition=condition, character=character,
                                       targets=targets, template_sha=template_sha, engines=engines, capabilities=capabilities)
            _check_cancelled(cancel_event)
            if restored and digest(restored) != digest(selected):
                result_store.write('seed_selected', scope, restored, schema=SELECTED_SCHEMA)
                status = 'restored'
        return dict(status=status, processed=0, targets=targets)
    batch.mkdir(parents=True, exist_ok=True)
    identity_file = batch / 'condition.txt'
    if identity_file.exists() and identity_file.read_text(encoding='ascii') != condition:
        raise ValueError('训练目录短标识碰撞，请选择其他运行目录')
    identity_file.write_text(condition, encoding='ascii')
    profile = batch / 'standard.simc'
    profile.write_text(text, encoding='utf-8')
    from task import _write_json
    _write_json(batch / 'identity.json', manifest, atomic=True)
    setup_runtime = TaskRuntime(600, cancel_event=cancel_event)
    setup_runtime.check()
    if not use_burst:
        native = reference(profile, batch / 'reference', character, runtime=setup_runtime, iterations=100,
                           simulation_config=simulation_config)
        character = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
        _, capabilities, _ = prepare_loop(native, character, batch, setup_runtime)
    else:
        (batch / 'reference').mkdir(exist_ok=True)
        (batch / 'reference/native.json').write_bytes((setup / 'reference/native.json').read_bytes())
    setup_runtime.check()
    _check_cancelled(cancel_event)
    reference_path = batch / 'reference/native.json'
    reference_key = digest(dict(condition=condition, purpose='seed_reference'))
    result_store.write_batch(reference_key, dict(batch_key=reference_key, run_id=condition,
        purpose='seed_reference', dps=native['dps'], samples=native['samples'],
        report=json.loads(reference_path.read_text(encoding='utf-8'))))
    reference_path.unlink()
    known = {row['candidate_id'] for row in candidates}
    processed = [row for row in processed if not (row['candidate_id'] in known and row['condition'] == condition)]
    seen = {}
    for row in processed:
        if row['condition'] == condition and row['status'] == 'completed':
            for field in ('initial_program', 'program'):
                identity = canonicalize_search_program(decode(row[field]), capabilities)['identity']
                seen.setdefault(identity, row['candidate_id'])
    for row in candidates:
        _check_cancelled(cancel_event)
        row['program'], row['core'] = decode(row['program']), decode(row['core'])
        folder = batch / row['candidate_id'][:12]
        folder.mkdir(exist_ok=True)
        record = dict(candidate_id=row['candidate_id'], condition=condition, status='failed',
                      error='', initial_program=row['program'], program=row['program'], family=row['family'],
                      core_retained=False, rounds=0, stop_reason='', elapsed_seconds=0., scores=[],
                      initial_scores=[], comparison={}, task_path=str(folder), native_batch_starts=0,
                      batch_requests=0, cache_hits=0)
        store = None
        execution = None
        cancelled = False
        try:
            if burst_context is not None:
                program, removed = training_program(row['program'], capabilities, all_capabilities, burst_context)
                if removed:
                    record['comparison']['adaptation'] = dict(original_program=row['program'], removed=removed,
                        initial_core_retained=retains_core(program, row['core']))
                row = dict(row, program=program)
                record.update(initial_program=program, program=program)
                for index, segment in enumerate(program if isinstance(program, list) else []):
                    if (removed and isinstance(segment, dict) and segment.get('kind') == 'CastSequence'
                            and len(segment['members']) == 1):
                        raise ValueError(f'segments[{index}]: 去除爆发动作后 /castsequence 仅剩一个成员，不能保持现有表达')
                if not program:
                    raise ValueError('去除爆发动作后没有可训练的普通循环')
                if all(isinstance(segment, dict) and segment.get('kind') == 'WaitClicks'
                       and type(segment.get('clicks')) is int and 2 <= segment['clicks'] <= 4096
                       for segment in program):
                    raise ValueError('去除爆发动作后没有可训练的普通循环，仅剩空点击')
            prepared = canonicalize_search_program(row['program'], capabilities)
            key = prepared['identity']
            if key in seen:
                record.update(status='rejected', error='相同行为候选: ' + seen[key])
            else:
                seen[key] = row['candidate_id']
                store = TaskStore(folder)
                saved_condition = store.state.get('training_condition')
                if saved_condition and saved_condition != condition:
                    raise ValueError('训练恢复条件不一致')
                if store.state.get('training_candidate_id', row['candidate_id']) != row['candidate_id']:
                    raise ValueError('训练候选目录短标识碰撞')
                execution = _write_execution(batch, manifest, row['candidate_id'], config, store.state)
                store.state.update(training_condition=condition, config=config, capabilities=capabilities,
                                   training_candidate_id=row['candidate_id'],
                                   run_id=store.state.get('run_id', uuid.uuid4().hex),
                                   starts=store.state.get('starts', [row['program']]),
                                   **(dict(burst=burst_context) if burst_context else {}))
                used = store.state.get('elapsed_seconds', 0)
                runtime = TaskRuntime(600, used_seconds=min(600, used),
                                      cancel_event=cancel_event)
                with store.active(runtime):
                    result = optimize(profile=profile, character=character, capabilities=capabilities,
                                      reference=native, destination=folder, runtime=runtime, config=config,
                                      condition_key=condition, store=store, simulation_config=simulation_config,
                                      training=True)
                best = next(item for item in result['search']['records']
                            if item['key'] == result['selected_candidate_key'])
                program = best['program']
                record.update(program=program, rounds=result['search']['rounds'],
                              stop_reason=result['search']['stop_reason'], elapsed_seconds=result['elapsed_seconds'],
                              core_retained=retains_core(program, row['core']),
                              native_batch_starts=store.state.get('native_batch_starts', 0),
                              cache_hits=store.state.get('batch_cache_hits', 0),
                              batch_requests=store.state.get('batch_requests', 0))
                if record['stop_reason'] not in ('no_improvement', 'space_stalled'):
                    raise ValueError('预算或其他上限使训练未收敛，保留进度待检查')
                record['initial_scores'] = retest(profile, row['program'], character, capabilities,
                                                 native, folder / 'retest-initial', simulation_config,
                                                 engines=engines, condition=condition,
                                                 runtime=TaskRuntime(600, cancel_event=cancel_event), burst_context=burst_context)
                record['scores'] = retest(profile, program, character, capabilities, native,
                                         folder / 'retest-final', simulation_config,
                                         engines=engines, condition=condition,
                                         runtime=TaskRuntime(600, cancel_event=cancel_event), burst_context=burst_context)
                record['comparison'].update(summarize_pairs(
                    [{'dps': value} for value in record['scores']],
                    [{'dps': value} for value in record['initial_scores']]))
                record['status'] = 'completed'
        except (ValueError, BudgetExceeded, TaskCancelled) as error:
            record['error'] = str(error)
            cancelled = isinstance(error, TaskCancelled)
            if isinstance(error, ValueError) and store is None:
                record['status'] = 'rejected'
        finally:
            if store:
                if execution is not None:
                    execution.update(finished_at=datetime.now(timezone.utc).isoformat(),
                                     after=_execution_state(store.state), status=record['status'],
                                     error=record['error'])
                    _write_json(batch / 'identity.json', manifest, atomic=True)
                store.close()
        if record['status'] == 'completed':
            identity = canonicalize_search_program(decode(record['program']), capabilities)['identity']
            seen.setdefault(identity, row['candidate_id'])
        processed.append(record)
        for item in processed:
            for name in ('initial_program', 'program', 'comparison'):
                item[name] = decode(item[name])
        result_store.write('seed_processed', scope, processed, schema=PROCESSED_SCHEMA)
        if cancelled:
            break
        _check_cancelled(cancel_event)
    if cancel_event is not None and cancel_event.is_set():
        raise TaskCancelled('任务已取消；进度已保存，旧入选库保持不变')
    if any(item['status'] == 'failed' for item in processed if item['condition'] == condition):
        raise ValueError('存在未完成候选，旧入选库保持不变；使用list --state processed检查')
    selected = publish_records(processed, selected, condition=condition, character=character,
                               targets=targets, template_sha=template_sha, engines=engines, capabilities=capabilities)
    _check_cancelled(cancel_event)
    if selected:
        _check_cancelled(cancel_event)
        result_store.write('seed_selected', scope, selected, schema=SELECTED_SCHEMA)
    return dict(status='completed', processed=len(candidates), selected=len(selected), targets=targets)


def run_training(template, targets, workspace, *, use_burst=False, max_processes=None):
    from seed_activity import training_activity
    with training_activity() as cancel_event:
        return _run_training(template, targets, workspace, cancel_event=cancel_event, use_burst=use_burst,
                             max_processes=max_processes)


def check_training(template=None, *, use_burst=True):
    """只读确认实际模板、受检引擎及审核定义，不创建模拟或训练目录。"""
    from engine import identity, training_template
    from burst import select_definition, talent_hash
    path = Path(template).resolve() if template is not None else training_template()
    if not path.is_file():
        raise ValueError('标准训练角色文件不存在: ' + str(path))
    text = path.read_text(encoding='utf-8')
    character = template_character(text)
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    definition = select_definition(character) if use_burst else None
    return dict(status='ready', template=str(path), template_source='explicit' if template else 'current_build',
                template_sha256=hashlib.sha256(text.encode()).hexdigest(),
                talent_sha256=talent_hash(character), engines=engines, use_burst=use_burst,
                burst_definition_id=definition['definition_id'] if definition else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description='人工清洗件登记与起点预训练')
    parser.add_argument('--project', type=Path, required=True, help='已接入的共享数据中心所属项目')
    commands = parser.add_subparsers(dest='command', required=True)
    registration = commands.add_parser('register', help='登记人工清洗件')
    registration.add_argument('input', type=Path)
    listing = commands.add_parser('list', help='读取中心中的起点记录')
    listing.add_argument('--state', choices=('pending', 'selected', 'processed', 'unsupported'), default='pending')
    listing.add_argument('--targets', type=int, choices=(1, 5), default=1)
    listing.add_argument('--class-name', default='deathknight')
    listing.add_argument('--spec', default='unholy')
    training = commands.add_parser('run', help='独立训练至连续两轮无改善、复测与更新')
    training.add_argument('--template', type=Path, help='明确角色文件；默认使用当前受检构建的标准角色')
    training.add_argument('--targets', type=int, nargs='+', choices=(1, 5), default=[1, 5])
    training.add_argument('--candidate-id', action='append', help='只训练指定登记材料；可重复传入，默认全部')
    training.add_argument('--max-processes', type=int, choices=range(1, 17),
                          help='覆盖内部训练并发（缺省2，最多16）；不并行处理材料或目标场景')
    training.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[2] /
                          '.local/sim2gse/seed-training')
    checking = commands.add_parser('check', help='只读核对训练模板、引擎与审核适用性，不启动计算')
    checking.add_argument('--template', type=Path)
    for command_parser in (training, checking, listing):
        mode = command_parser.add_mutually_exclusive_group()
        mode.add_argument('--use-burst', dest='use_burst', action='store_true', help='独立爆发模式（默认）')
        mode.add_argument('--legacy', dest='use_burst', action='store_false', help='显式查看或运行历史无爆发模式')
        command_parser.set_defaults(use_burst=True)
    args = parser.parse_args(argv)
    try:
        result_store.bind_project(args.project)
        result_store.ensure_available()
        if args.command == 'register':
            output = register(args.input)
        elif args.command == 'check':
            output = check_training(args.template, use_burst=args.use_burst)
        elif args.command == 'run':
            from simulation_config import load_training_config
            max_processes = (args.max_processes if args.max_processes is not None else
                             load_training_config()['max_processes'])
            material_options = ({'materials': selected_materials(args.candidate_id)}
                                if args.candidate_id else {})
            ready = check_training(args.template, use_burst=args.use_burst)
            from seed_activity import training_activity
            with writer_lock():
                with training_activity() as cancel_event:
                    output = [_run_training(Path(ready['template']), targets, args.workspace,
                                            cancel_event=cancel_event, use_burst=args.use_burst,
                                            max_processes=max_processes,
                                            **material_options)
                              for targets in dict.fromkeys(args.targets)]
        elif args.state in ('pending', 'unsupported'):
            output = [row for row in result_store.read_records('seed_candidates', 'registry')
                      if (row['semantic'] == 'unsupported') == (args.state == 'unsupported')]
        else:
            output = result_store.read_records('seed_' + args.state,
                                              f'{args.class_name}-{args.spec}-{args.targets}' +
                                              ('-burst' if args.use_burst else ''))
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
