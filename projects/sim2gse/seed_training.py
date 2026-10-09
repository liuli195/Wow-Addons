"""Manually launched seed preparation; all business records use the shared center."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import math
import msvcrt
from pathlib import Path
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


def publish_records(processed, selected, *, condition, character, targets, template_sha, engines, capabilities=None):
    """Rebuild from committed outcomes so a failed final publish is retryable."""
    options = []
    for row in processed:
        if row['condition'] != condition or row['status'] != 'completed':
            continue
        final_family = row['family'] if row['core_retained'] else 'history-search'
        for program, scores, family in (
                (decode(row['program']), row['scores'], final_family),
                (decode(row['initial_program']), row['initial_scores'], row['family'])):
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


def training_condition(template_sha, engines, config, simulation_config, *, burst_context=None):
    """训练与升级核验共用的条件计算；不启动计算、不读取历史。"""
    from engine import ROOT, COMMON
    from task import _rule_hashes
    return digest(dict(version=TRAINING_VERSION, template=template_sha, engines=engines,
                       config=config, simulation=simulation_config, retest=RETEST_SEEDS,
                       effective_options=COMMON, rules=_rule_hashes(relative_to=ROOT),
                       **(dict(task_category='burst_free_training', burst=burst_context)
                          if burst_context else {})))


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


def _run_training(template, targets, workspace, *, cancel_event=None, use_burst=False, materials=None):
    from engine import identity, reference, prepare_loop
    from program import canonicalize_search_program
    _check_cancelled(cancel_event)
    text = template.read_text(encoding='utf-8')
    character = template_character(text)
    if materials is not None and any(row['class_name'] != character.class_name or
                                     row['spec'] != character.spec for row in materials):
        raise ValueError('训练材料与标准角色职业或专精不一致')
    scope = f'{character.class_name}-{character.spec}-{targets}' + ('-burst' if use_burst else '')
    config = config_for({'diagnostic_logging': True, 'diagnostics': 'summary',
                         'no_improvement_rounds': 2})
    simulation_config = {'target_count': targets, 'enable_omnium_talents': True}
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    burst_context = None
    capabilities = None
    if use_burst:
        from burst import select_definition
        definition = select_definition(character)
        config = config_for(dict(config, input_interval_ms=200))
        setup = workspace.resolve() / 'burst-setup' / uuid.uuid4().hex
        setup.mkdir(parents=True)
        setup_profile = setup / 'standard.simc'
        setup_profile.write_text(text, encoding='utf-8')
        setup_runtime = TaskRuntime(600, cancel_event=cancel_event)
        native = reference(setup_profile, setup / 'reference', character, runtime=setup_runtime,
                           iterations=100, simulation_config=simulation_config)
        character = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
        _, capabilities, burst_context = prepare_loop(native, character, setup, setup_runtime,
                                                      definition=definition, interval_ms=config['input_interval_ms'])
    template_sha = hashlib.sha256(text.encode()).hexdigest()
    condition = training_condition(template_sha, engines, config, simulation_config,
                                   burst_context=burst_context)
    processed = result_store.read_records('seed_processed', scope)
    selected = [row for row in result_store.read_records('seed_selected', scope)
                if row['condition'] == condition]
    completed = {row['candidate_id'] for row in processed
                 if row['condition'] == condition and row['status'] in ('completed', 'rejected')}
    candidates = (materials if materials is not None else
                  result_store.read_records('seed_candidates', 'registry') + history_candidates(character))
    _check_cancelled(cancel_event)
    candidates = [row for row in candidates if row.get('semantic') != 'unsupported' and
                  row['class_name'] == character.class_name and
                  row['spec'] == character.spec and row['candidate_id'] not in completed]
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
    batch = workspace.resolve() / str(targets) / condition[:12]
    batch.mkdir(parents=True, exist_ok=True)
    identity_file = batch / 'condition.txt'
    if identity_file.exists() and identity_file.read_text(encoding='ascii') != condition:
        raise ValueError('训练目录短标识碰撞，请选择其他运行目录')
    identity_file.write_text(condition, encoding='ascii')
    profile = batch / 'standard.simc'
    profile.write_text(text, encoding='utf-8')
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
        cancelled = False
        try:
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
                record['comparison'] = summarize_pairs(
                    [{'dps': value} for value in record['scores']],
                    [{'dps': value} for value in record['initial_scores']])
                record['status'] = 'completed'
        except (ValueError, BudgetExceeded, TaskCancelled) as error:
            record['error'] = str(error)
            cancelled = isinstance(error, TaskCancelled)
            if isinstance(error, ValueError) and store is None:
                record['status'] = 'rejected'
        finally:
            if store:
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


def run_training(template, targets, workspace, *, use_burst=False):
    from seed_activity import training_activity
    with training_activity() as cancel_event:
        return _run_training(template, targets, workspace, cancel_event=cancel_event, use_burst=use_burst)


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
            material_options = ({'materials': selected_materials(args.candidate_id)}
                                if args.candidate_id else {})
            ready = check_training(args.template, use_burst=args.use_burst)
            from seed_activity import training_activity
            with writer_lock():
                with training_activity() as cancel_event:
                    output = [_run_training(Path(ready['template']), targets, args.workspace,
                                            cancel_event=cancel_event, use_burst=args.use_burst,
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
