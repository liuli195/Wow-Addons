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
import time
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
TRAINING_VERSION = 'seed-training-v1'


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
    if row['semantic'] not in ('preserved', 'rewritten'):
        raise ValueError('仅可登记语义保留或明确改写的可模拟清洗件')
    if (not isinstance(row['changes'], list) or
            any(not isinstance(item, str) for item in row['changes']) or
            not isinstance(row['program'], list) or not row['program'] or
            not isinstance(row['core'], list)):
        raise ValueError('清洗记录、核心或程序格式无效')
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


def retest(profile, program, character, capabilities, native, folder, simulation_config):
    from program import from_search_program, compile_program
    from sequence import evaluate
    compiled = compile_program(from_search_program(program, capabilities), folder / 'export',
                               identity=native['identity'], capabilities=capabilities)
    scores = []
    for seed in RETEST_SEEDS:
        result = evaluate(profile, compiled, folder / str(seed), character=character, iterations=128,
                          seed=seed, trace=False, input_times=list(range(0, 180000, 300)),
                          simulation_config=simulation_config)
        summary = result['summary']
        if summary['samples'] < 2 or not math.isfinite(summary['dps']) or summary['dps'] <= 0:
            raise ValueError('复测没有完整有效成绩')
        scores.append(summary['dps'])
        result_store.write_batch(digest(dict(folder=str(folder), seed=seed)), dict(
            batch_key=digest(dict(folder=str(folder), seed=seed)), run_id=folder.parent.name,
            purpose='seed_retest', seed=seed, samples=summary['samples'], dps=summary['dps'],
            report=result['report']))
        (folder / str(seed) / 'native.json').unlink(missing_ok=True)
    return scores


def retains_core(program, core):
    if not core:
        return False
    # Exact grouped fragment; no frequency-based or cyclic-rotation equivalence.
    return any(program[index:index + len(core)] == core for index in range(len(program)))


def publish_records(processed, selected, *, condition, character, targets, template_sha, engines):
    """Rebuild from committed outcomes so a failed final publish is retryable."""
    options = []
    for row in processed:
        if row['condition'] != condition or row['status'] != 'completed':
            continue
        final_family = row['family'] if row['core_retained'] else 'history-search'
        for program, scores, family in (
                (decode(row['program']), row['scores'], final_family),
                (decode(row['initial_program']), row['initial_scores'], row['family'])):
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
        unique.setdefault(digest(item['program']), item)
    return list(unique.values())[:4]


def run_training(template, targets, workspace):
    from engine import identity, reference, inspect, ROOT, COMMON
    from program import from_search_program, compile_program, canonicalize_search_program
    initialization_started = time.monotonic()
    text = template.read_text(encoding='utf-8')
    character = template_character(text)
    scope = f'{character.class_name}-{character.spec}-{targets}'
    config = config_for({'diagnostic_logging': True, 'diagnostics': 'summary'})
    simulation_config = {'target_count': targets, 'enable_omnium_talents': True}
    engines = {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}
    template_sha = hashlib.sha256(text.encode()).hexdigest()
    rules = {name: hashlib.sha256((ROOT / 'projects/sim2gse' / name).read_bytes()).hexdigest()
             for name in ('program.py', 'search.py', 'sequence.py', 'seed_training.py')}
    condition = digest(dict(version=TRAINING_VERSION, template=template_sha, engines=engines,
                            config=config, simulation=simulation_config, retest=RETEST_SEEDS,
                            effective_options=COMMON, rules=rules))
    processed = result_store.read_records('seed_processed', scope)
    selected = [row for row in result_store.read_records('seed_selected', scope)
                if row['condition'] == condition]
    completed = {row['candidate_id'] for row in processed
                 if row['condition'] == condition and row['status'] in ('completed', 'rejected')}
    candidates = result_store.read_records('seed_candidates', 'registry') + history_candidates(character)
    candidates = [row for row in candidates if row['class_name'] == character.class_name and
                  row['spec'] == character.spec and row['candidate_id'] not in completed]
    if not candidates:
        status = 'unchanged'
        if not any(row['condition'] == condition and row['status'] == 'failed' for row in processed):
            restored = publish_records(processed, selected, condition=condition, character=character,
                                       targets=targets, template_sha=template_sha, engines=engines)
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
    native = reference(profile, batch / 'reference', character, iterations=100,
                       simulation_config=simulation_config)
    character = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
    capabilities = inspect(native, batch / 'capabilities')
    reference_path = batch / 'reference/native.json'
    reference_key = digest(dict(condition=condition, purpose='seed_reference'))
    result_store.write_batch(reference_key, dict(batch_key=reference_key, run_id=condition,
        purpose='seed_reference', dps=native['dps'], samples=native['samples'],
        report=json.loads(reference_path.read_text(encoding='utf-8'))))
    reference_path.unlink()
    initialization_seconds = time.monotonic() - initialization_started
    known = {row['candidate_id'] for row in candidates}
    processed = [row for row in processed if not (row['candidate_id'] in known and row['condition'] == condition)]
    seen = {}
    for row in processed:
        if row['condition'] == condition and row['status'] == 'completed':
            seen[canonicalize_search_program(decode(row['initial_program']), capabilities)['identity']] = row['candidate_id']
    for row in candidates:
        row['program'], row['core'] = decode(row['program']), decode(row['core'])
        folder = batch / row['candidate_id'][:12]
        folder.mkdir(exist_ok=True)
        record = dict(candidate_id=row['candidate_id'], condition=condition, status='failed',
                      error='', initial_program=row['program'], program=row['program'], family=row['family'],
                      core_retained=False, rounds=0, stop_reason='', elapsed_seconds=0., scores=[],
                      initial_scores=[], comparison={}, task_path=str(folder), native_batch_starts=0,
                      batch_requests=0, cache_hits=0)
        store = None
        try:
            prepared = canonicalize_search_program(row['program'], capabilities)
            key = prepared['identity']
            if key in seen:
                record.update(status='rejected', error='相同行为候选: ' + seen[key])
            else:
                seen[key] = row['candidate_id']
                compile_program(from_search_program(row['program'], capabilities), folder / 'initial-export',
                                identity=native['identity'], capabilities=capabilities)
                store = TaskStore(folder)
                saved_condition = store.state.get('training_condition')
                if saved_condition and saved_condition != condition:
                    raise ValueError('训练恢复条件不一致')
                if store.state.get('training_candidate_id', row['candidate_id']) != row['candidate_id']:
                    raise ValueError('训练候选目录短标识碰撞')
                store.state.update(training_condition=condition, config=config,
                                   training_candidate_id=row['candidate_id'],
                                   run_id=store.state.get('run_id', uuid.uuid4().hex),
                                   starts=store.state.get('starts', [row['program']]))
                used = store.state.get('elapsed_seconds', 0)
                runtime = TaskRuntime(600, used_seconds=min(600, used + initialization_seconds))
                with store.active(runtime):
                    result = optimize(profile=profile, character=character, capabilities=capabilities,
                                      reference=native, destination=folder, runtime=runtime, config=config,
                                      condition_key=condition, store=store, simulation_config=simulation_config,
                                      training_round_limit=5)
                best = next(item for item in result['search']['records']
                            if item['key'] == result['selected_candidate_key'])
                program = best['program']
                record.update(program=program, rounds=result['search']['rounds'],
                              stop_reason=result['search']['stop_reason'], elapsed_seconds=result['elapsed_seconds'],
                              core_retained=retains_core(program, row['core']),
                              native_batch_starts=store.state.get('native_batch_starts', 0),
                              cache_hits=store.state.get('batch_cache_hits', 0),
                              batch_requests=store.state.get('batch_requests', 0))
                if store.state.get('training_complete_rounds', 0) != 5:
                    raise ValueError('预算或其他停止条件使五轮未完成，保留进度待检查')
                record['initial_scores'] = retest(profile, row['program'], character, capabilities,
                                                 native, folder / 'retest-initial', simulation_config)
                record['scores'] = retest(profile, program, character, capabilities, native,
                                         folder / 'retest-final', simulation_config)
                record['comparison'] = summarize_pairs(
                    [{'dps': value} for value in record['scores']],
                    [{'dps': value} for value in record['initial_scores']])
                record['status'] = 'completed'
        except (ValueError, BudgetExceeded, TaskCancelled) as error:
            record['error'] = str(error)
            if isinstance(error, ValueError) and store is None:
                record['status'] = 'rejected'
        finally:
            if store:
                store.close()
        processed.append(record)
        for item in processed:
            for name in ('initial_program', 'program', 'comparison'):
                item[name] = decode(item[name])
        result_store.write('seed_processed', scope, processed, schema=PROCESSED_SCHEMA)
    if any(item['status'] == 'failed' for item in processed if item['condition'] == condition):
        raise ValueError('存在未完成候选，旧入选库保持不变；使用list --state processed检查')
    selected = publish_records(processed, selected, condition=condition, character=character,
                               targets=targets, template_sha=template_sha, engines=engines)
    if selected:
        result_store.write('seed_selected', scope, selected, schema=SELECTED_SCHEMA)
    return dict(status='completed', processed=len(candidates), selected=len(selected), targets=targets)


def main(argv=None):
    parser = argparse.ArgumentParser(description='人工清洗件登记与起点预训练')
    parser.add_argument('--project', type=Path, help='已接入的共享数据中心所属项目')
    commands = parser.add_subparsers(dest='command', required=True)
    registration = commands.add_parser('register', help='登记人工清洗件')
    registration.add_argument('input', type=Path)
    listing = commands.add_parser('list', help='读取中心中的起点记录')
    listing.add_argument('--state', choices=('pending', 'selected', 'processed'), default='pending')
    listing.add_argument('--targets', type=int, choices=(1, 5), default=1)
    listing.add_argument('--class-name', default='deathknight')
    listing.add_argument('--spec', default='unholy')
    training = commands.add_parser('run', help='独立五轮训练、复测与更新')
    training.add_argument('--template', type=Path, default=Path(__file__).resolve().parents[2] /
                          '.tools/sim2gse/product/baseline/profiles/MID2/MID2_Death_Knight_Unholy.simc')
    training.add_argument('--targets', type=int, nargs='+', choices=(1, 5), default=[1, 5])
    training.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[2] /
                          '.local/sim2gse/seed-training')
    args = parser.parse_args(argv)
    try:
        if args.project:
            result_store.bind_project(args.project)
        result_store.ensure_available()
        if args.command == 'register':
            output = register(args.input)
        elif args.command == 'run':
            with writer_lock():
                output = [run_training(args.template, targets, args.workspace) for targets in dict.fromkeys(args.targets)]
        elif args.state == 'pending':
            output = result_store.read_records('seed_candidates', 'registry')
        else:
            output = result_store.read_records('seed_' + args.state,
                                              f'{args.class_name}-{args.spec}-{args.targets}')
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
