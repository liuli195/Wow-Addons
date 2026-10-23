"""A代际预训练。复用现有评价/报告/TaskStore，不创建第二套模拟后端。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import random
import types
import uuid

from runtime import TaskRuntime, TaskCancelled
from search import TaskStore, digest, optimize, mutate, _tuple, _validate_saved_batch

SCENARIOS = ('nominal', 'jitter', 'pause', 'slow', 'phase')
ALGORITHM = 'ga-easimple-v1'


def _cross(left, right, rng):
    def blocks(member):
        return member[0]['blocks'] if (len(member) == 1 and isinstance(member[0], dict)
                                       and member[0].get('kind') == 'Loop') else member
    a, b = blocks(left), blocks(right)
    if min(len(a), len(b)) < 2:
        return False
    cut = rng.randint(1, min(len(a), len(b)) - 1)
    if a[cut:] == b[cut:]:
        return False
    a[cut:], b[cut:] = deepcopy(b[cut:]), deepcopy(a[cut:])
    return True


def _stage_plan(config, seed):
    # Independent deterministic streams, frozen before the first request.
    rng = random.Random(seed)
    seeds, used = [], set()
    while len(seeds) < 2 + 5 * config['retest_batches']:
        value = rng.randrange(1, 1000000000)
        if not {value, value - 500000, value + 500000} & used:
            seeds.append(value)
            used.add(value)
    plan = dict(search=dict(iterations=config['coarse_iterations'], seeds=seeds[:1]),
                feedback=dict(iterations=2, seeds=seeds[1:2]))
    offset = 2
    for name in SCENARIOS:
        plan[name] = dict(iterations=config['retest_iterations'],
                          seeds=seeds[offset:offset + config['retest_batches']])
        offset += config['retest_batches']
    return plan


def _evolution(store, capabilities, runtime, config):
    """The eaSimple replacement step and varAnd are group-local, including RNG."""
    from deap import algorithms, base
    from program import canonicalize_search_program, _search_expanded_nodes
    from codec import load_targeting, prepare_block, prepare_castsequence
    target_masks = load_targeting(runtime=runtime)['target_masks']
    class Fitness(base.Fitness):
        weights = (1.0,)
    class Individual(list):
        pass
    ga = store.state['ga']
    if ga['phase'] == 'qualified':
        ga['phase'] = 'retest'  # Re-verify all frozen receipts after a failed publication; refill only missing evidence.
    rng = random.Random()
    rng.setstate(_tuple(ga['rng']))
    toolbox = base.Toolbox()
    def individual(row):
        member = Individual(deepcopy(row['program']))
        member.fitness = Fitness((row['score'],))
        return member
    def clone(parent):
        child = deepcopy(parent)
        child.parent_program, child.crossed = deepcopy(list(parent)), False
        return child
    def select(population, count):
        return [max((rng.choice(population) for _ in range(config['tournament_size'])),
                    key=lambda member: member.fitness) for _ in range(count)]
    def mate(left, right):
        if _cross(left, right, rng):
            left.crossed = right.crossed = True
        return left, right
    feedback_for = None
    def mutation(member):
        feedback_getter = None if member.crossed else lambda: feedback_for(member.parent_program)
        member[:] = mutate(member, capabilities, rng, feedback_getter=feedback_getter)
        return member,
    toolbox.register('clone', clone)
    toolbox.register('mate', mate)
    toolbox.register('mutate', mutation)
    # Rebind only this function's globals, never DEAP's shared module.random.
    variation = types.FunctionType(algorithms.varAnd.__code__,
        dict(algorithms.varAnd.__globals__, random=rng), 'group_varAnd')

    def execute(*, evaluate, feedback):
        nonlocal feedback_for
        def bounded_feedback(program):
            row = feedback(program)
            if len(store.report_buffer) >= 12:
                store.checkpoint()
            return row
        feedback_for = bounded_feedback
        timeline = getattr(runtime, 'search_timeline', None)
        def key(program):
            canonical = canonicalize_search_program(program, capabilities)
            for node in _search_expanded_nodes(canonical['program']):
                if node['kind'] == 'Action':
                    commands = node['commands']
                    if len(commands) == 1 and commands[0].get('kind') == 'castsequence':
                        prepare_castsequence(commands[0])
                    else:
                        prepare_block(commands, target_masks)
            return canonical['identity']
        def scores(programs, stage='search', index=0, *, record_timeline=True):
            unique = {}
            for program in programs:
                unique.setdefault(key(program), program)
            results = {}
            items = list(unique.items())
            # Bounded scheduling windows also bound nondurable report memory to 12.
            at = 0
            while at < len(items):
                runtime.check()
                capacity = max(1, 12 - len(store.report_buffer))
                window = items[at:at + capacity]
                at += len(window)
                with ThreadPoolExecutor(max_workers=config['max_processes']) as pool:
                    futures = [(identity, pool.submit(evaluate, program, stage, index))
                               for identity, program in window]
                    error = None
                    for identity, future in futures:
                        try:
                            results[identity] = future.result()
                            if timeline is not None and record_timeline:
                                row = results[identity]
                                timeline.score(dict(key=identity, score=row['dps'], batches=[row]),
                                               stage, 'training')
                        except BaseException as failure:
                            error = error or failure
                    if len(store.report_buffer) >= 12:
                        store.checkpoint()
                    if error is not None:
                        raise error
            return [results[key(program)] for program in programs]
        def ranking():
            return sorted(store.state['archive'], key=lambda row: (-row['batches'][0]['dps'], row['key']))[:config['top_k']]
        def baseline():
            return [row['batches'][0]['dps'] for row in ranking()]
        # Once per invocation, before any old fitness is used. The existing evaluator
        # reconstructs the full frozen request, verifies its receipt, and repairs only
        # missing/corrupt evidence. Temporary storage failures still pause the group.
        historical = list(store.state['archive'])
        verified = scores([row['program'] for row in historical], record_timeline=False)
        for old, row in zip(historical, verified):
            batches = old.get('batches', [])
            if (old['key'] != row['candidate_key'] or len(batches) != 1
                    or batches[0].get('data_key') != row['batch_key']
                    or digest(batches[0].get('request')) != row['batch_key']
                    or any(batches[0].get(field) != row[field] for field in ('dps', 'samples'))):
                raise ValueError('恢复粗评档案与冻结条件的成功凭据不符；已暂停，旧四条保持不变')
        fitness = {row['candidate_key']: row['dps'] for row in verified}
        if any(fitness.get(row['key']) != row['score'] for row in ga['population']):
            raise ValueError('恢复种群粗分与成功凭据不符；已暂停，旧四条保持不变')
        if ga['phase'] == 'initial':
            rows = scores(store.state['starts'])
            ga['population'] = [dict(program=deepcopy(program), key=row['candidate_key'], score=row['dps'])
                                for program, row in zip(store.state['starts'], rows)]
            ga.update(phase='breed', baseline=baseline())
            store.checkpoint()
        while ga['phase'] == 'breed':
            runtime.check()
            population = [individual(row) for row in ga['population']]
            pending = ga.get('pending')
            if pending is None:
                children = variation(select(population, len(population)), toolbox,
                    config['crossover_probability'], config['mutation_probability'])
                pending = dict(programs=[deepcopy(list(child)) for child in children],
                               regenerations=[0] * len(children), rng=rng.getstate())
                ga['pending'] = pending
                store.checkpoint()
            else:
                rng.setstate(_tuple(pending['rng']))
            for slot in range(len(pending['programs'])):
                while True:
                    runtime.check()
                    try:
                        key(pending['programs'][slot])
                        break
                    except ValueError as error:
                        if pending['regenerations'][slot] >= 10:
                            raise ValueError(f'非法子代槽{slot}已耗尽10次额外重生: {error}') from error
                    children = variation(select(population, 2), toolbox,
                        config['crossover_probability'], config['mutation_probability'])
                    pending['programs'][slot] = deepcopy(list(children[0]))
                    pending['regenerations'][slot] += 1
                    pending['rng'] = rng.getstate()
                    store.checkpoint()
            rows = scores(pending['programs'])
            current = baseline()
            improved = len(current) > len(ga['baseline']) or any(
                value > old for value, old in zip(current, ga['baseline']))
            ga.update(population=[dict(program=deepcopy(program), key=row['candidate_key'], score=row['dps'])
                                  for program, row in zip(pending['programs'], rows)],
                generation=ga['generation'] + 1, rng=pending['rng'], pending=None,
                baseline=current, stagnant=0 if improved else ga['stagnant'] + 1)
            if ga['stagnant'] >= config['stagnation_generations']:
                ga.update(phase='retest', finalists=[row['key'] for row in ranking()])
            store.checkpoint()
        archive = {row['key']: row for row in store.state['archive']}
        if ga['phase'] == 'retest':
            finalists = ga['finalists']
            programs = [archive[identity]['program'] for identity in finalists]
            for scenario in SCENARIOS:
                for index in range(config['retest_batches']):
                    runtime.check()
                    rows = scores(programs, scenario, index)
                    for identity, row in zip(finalists, rows):
                        ga['finals'].setdefault(identity, {}).setdefault(scenario, {})[str(index)] = row
                    # Receipts live in the bounded finalist state; reports flush at 12 or phase/cancel.
            ga['phase'] = 'qualified'
            store.checkpoint()
        return ga
    return execute


def _unfinished(workspace, *, template=None, targets=None, scope=None):
    """Startup-only scan of known task manifests, never a per-score fallback."""
    import sqlite3
    for path in (Path(workspace).resolve() / 'ga').glob('*/*/identity.json'):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if (template is not None and manifest.get('template_path') != str(Path(template).resolve())
                or targets is not None and manifest['environment']['simulation']['target_count'] != targets
                or scope is not None and path.parent.parent.name != scope):
            continue
        database = path.with_name('task.sqlite3')
        if not database.is_file():
            continue
        with sqlite3.connect('file:' + database.as_posix() + '?mode=ro', uri=True) as db:
            try:
                state = TaskStore.load_state(db)
            except sqlite3.OperationalError as error:
                raise ValueError('GA任务检查点不完整: ' + str(path.parent)) from error
        if state.get('ga', {}).get('phase') != 'published':
            yield path.parent, manifest


def group_configs(workspace, templates, config, targets=(1, 5)):
    """Resolve only this invocation's groups; new TOML values cannot alter resumed groups."""
    paths = {str(Path(row['template']).resolve()): row.get('template_sha256') for row in templates}
    effective = {(path, count): config for path in paths for count in dict.fromkeys(targets)}
    frozen = set()
    for _, manifest in _unfinished(workspace):
        key = (manifest.get('template_path'), manifest['environment']['simulation']['target_count'])
        if any(path != key[0] and sha == manifest['environment']['template'] and (path, key[1]) in effective
               for path, sha in paths.items()):
            raise ValueError('跨模板路径不能恢复未完成GA任务；请使用原模板路径恢复，或使用新工作目录开始新任务')
        if key not in effective:
            continue
        if key in frozen:
            raise ValueError('同模板/目标存在多个未完成GA任务')
        frozen.add(key)
        effective[key] = manifest['training_config']
    return effective


def group_workers(workspace, templates, config, targets=(1, 5), *, effective_configs=None):
    """A conservative joint limit also keeps mixed frozen/new groups within 20 processes."""
    configs = (group_configs(workspace, templates, config, targets)
               if effective_configs is None else effective_configs)
    if not configs:
        return 1
    return min(*(row['max_trainings'] for row in configs.values()),
               20 // max(row['max_processes'] for row in configs.values()))


def run_group(template, targets, workspace, *, cancel_event, use_burst, sources, config,
              prepare_only=False, materials=None, diagnostic_logging=False, search_config=None,
              expected_key=None, timeline_origin=None, burst_identity=None):
    import seed_training as seeds
    from task import _write_json, _rule_hashes
    from engine import ROOT
    if any((Path(workspace) / str(targets)).glob('*/identity.json')):
        raise ValueError('旧逐材料训练目录不能作为GA任务恢复；请使用新工作目录，原完整成果仍可读取')
    frozen = list(_unfinished(workspace, template=template, targets=targets))
    if len(frozen) > 1:
        raise ValueError('同模板/目标存在多个未完成GA任务')
    if frozen:
        from simulation_config import reject_removed_search_settings
        reject_removed_search_settings(frozen[0][1]['search_config'])
        seeds._check_pretraining_observations(frozen[0][1]['search_config'])
        config = frozen[0][1]['training_config']
        sources = [source for row in frozen[0][1]['sources'] for source in row['sources']]
        materials = None  # Resume the original material manifest, not today's registry/subset.
    ready = seeds.ensure_prepared(template, targets, workspace, cancel_event=cancel_event,
        use_burst=use_burst, sources=sources, materials=materials,
        max_processes=config['max_processes'], diagnostic_logging=diagnostic_logging, search_config=search_config,
        burst_identity=burst_identity)
    context = ready['context']
    if not context or not ready['queue']:
        raise ValueError('本组没有有效训练材料')
    configuration_key = context['configuration_key']
    if expected_key is not None and configuration_key != expected_key:
        raise ValueError('受检标准模板实际英雄/目标与冻结训练分组不符')
    if prepare_only:
        return dict(status='prepared', algorithm=ALGORITHM, configuration_key=configuration_key,
                    population_size=len(ready['queue']), config_key=ready['config_key'],
                    preparation=ready['preparation'])
    scope = seeds.shared_scope(configuration_key)
    root = Path(workspace).resolve() / 'ga' / scope
    environment = dict(template=ready['template_sha'], engines=ready['engines'],
        simulation=ready['simulation_config'], burst=context['burst'],
        rules=_rule_hashes(relative_to=ROOT))
    active = list(_unfinished(workspace, scope=scope))
    if len(active) > 1:
        raise ValueError('本组三元范围存在多个未完成GA任务')
    if active:
        folder, manifest = active[0]
        if not frozen or folder != frozen[0][0]:
            raise ValueError('跨模板路径不能恢复未完成GA任务；请使用原模板路径恢复，或使用新工作目录开始新任务')
        if manifest['environment'] != environment:
            raise ValueError('GA恢复的角色/引擎/规则身份变化，拒绝混接')
        config = manifest['training_config']
    else:
        manifest = dict(environment=environment, training_config=config, template_path=str(Path(template).resolve()),
            starts=[row['program'] for row in ready['queue']], sources=ready['queue'],
            search_config=ready['config'], seed=uuid.uuid4().int % 1000000000)
        manifest['stage_plan'] = _stage_plan(config, manifest['seed'])
        folder = root / uuid.uuid4().hex
        folder.mkdir(parents=True)
        _write_json(folder / 'identity.json', manifest, atomic=True)
    profile = folder / 'standard.simc'
    if not profile.exists():
        profile.write_text(ready['text'], encoding='utf-8')
    elif profile.read_text(encoding='utf-8') != ready['text']:
        raise ValueError('GA冻结标准角色副本已变化')
    store = TaskStore(folder)
    character = replace(ready['character'], spec_id=context['native']['identity']['spec_id'],
                        race=context['native']['identity']['race'])
    runtime = TaskRuntime(float('inf'), cancel_event=cancel_event, diagnostic_logging=diagnostic_logging)
    execution_config = dict(manifest['search_config'], diagnostic_logging=diagnostic_logging,
        diagnostics='summary' if diagnostic_logging else 'off')
    timeline = None
    if (search_config or {}).get('search_timeline'):
        from search_timeline import Timeline
        timeline = Timeline(origin=timeline_origin, context=dict(configuration_key=configuration_key,
            simulation_config=ready['simulation_config']), resumed=bool(active))
        timeline.configure(profile_sha=ready['template_sha'], engines=ready['engines'],
            simulation_config=ready['simulation_config'], config=manifest['search_config'], burst=context['burst'])
        timeline.context['algorithm'].update(training=ALGORITHM, random_seed=manifest['seed'], training_config=config)
        runtime.search_timeline = timeline
    try:
        if not store.state:
            rng = random.Random(manifest['seed'])
            store.state.update(run_id=uuid.uuid4().hex, starts=manifest['starts'], config=execution_config,
                capabilities=context['capabilities'], configuration_key=configuration_key, burst=context['burst'],
                ga=dict(algorithm=ALGORITHM, phase='initial', generation=0, stagnant=0,
                        population=[], pending=None, rng=rng.getstate(), finals={}))
        if (store.state.get('ga', {}).get('algorithm') != ALGORITHM
                or store.state.get('starts') != manifest['starts']):
            raise ValueError('GA检查点算法或冻结初始种群身份不符')
        store.character, store.simulation_config = character, ready['simulation_config']
        store.recover_reports(character, ready['simulation_config'])
        store.state['error'] = ''
        # 日志采集跟随本次调用，算法与评分身份仍使用原冻结manifest。
        store.state['config'] = execution_config
        with store.active(runtime):
            if timeline is not None:
                timeline.start()
            ga = optimize(profile=profile, character=character, capabilities=context['capabilities'],
                reference=context['native'], destination=folder, runtime=runtime,
                config=execution_config, condition_key=digest(manifest), store=store,
                simulation_config=ready['simulation_config'], training=True,
                training_stage_plan=manifest['stage_plan'],
                training_runner=_evolution(store, context['capabilities'], runtime, config))
            if timeline is not None:
                timeline.stop('stagnation')
            selected = _selected(ga, store, manifest, character, ready, configuration_key)
            runtime.check()
            # Evidence verification precedes the only current-snapshot replacement.
            result_store = __import__('result_store')
            result_store.write('seed_selected', scope, selected, schema=seeds.SELECTED_V2_SCHEMA)
            ga['phase'] = 'published'
            store.state['status'] = 'completed'
            store.checkpoint()
            if timeline is not None:
                timeline.saved('completed')
        return dict(status='completed', algorithm=ALGORITHM, population_size=len(manifest['starts']),
            complete_generations=ga['generation'], configuration_key=configuration_key,
            selected=len(selected), task_path=str(folder), training_config=config,
            ineligible=ga.get('ineligible', {}))
    except BaseException as error:
        store.state.update(status='paused', error=str(error))
        store.checkpoint()
        if timeline is not None:
            status = 'cancelled' if isinstance(error, (TaskCancelled, KeyboardInterrupt)) else 'failed'
            timeline.stop(status)
            timeline.saved(status)
        raise
    finally:
        try:
            store.close()
        finally:
            if timeline is not None:
                timeline.finish(folder)


def _selected(ga, store, manifest, character, ready, configuration_key):
    from result_store import DATA_ROOT, read_many, report_locations
    from seed_training import SELECTED_V2_SCHEMA
    from program import canonicalize_search_program
    archive = {row['key']: row for row in store.state['archive']}
    condition = digest(manifest)
    receipts = {}
    qualified = []
    for identity in ga['finalists']:
        scenarios = {}
        for scenario in SCENARIOS:
            batches = [ga['finals'][identity][scenario][str(index)]
                       for index in range(manifest['training_config']['retest_batches'])]
            for index, row in enumerate(batches):
                cached = store.batch(row['batch_key'])
                if not cached or cached.get('status') != 'success':
                    raise ValueError('发布缺少可靠复测批次')
                request = cached['request']
                expected_seed = manifest['stage_plan'][scenario]['seeds'][index]
                if (digest(request) != row['batch_key'] or request['condition'] != condition
                        or request['behavior_identity'] != identity or request['purpose'] != scenario
                        or request['seed'] != expected_seed
                        or request['iterations'] != manifest['training_config']['retest_iterations']
                        or any(row[field] != cached[field] for field in ('dps', 'samples'))
                        or row['candidate_key'] != identity):
                    raise ValueError('发布复测凭据与冻结候选/条件/成绩不符')
                if row['batch_key'] in receipts:
                    raise ValueError('发布复测凭据重复；旧四条保持不变')
                receipts[row['batch_key']] = (cached, index, scenario)
            samples = sum(row['samples'] for row in batches)
            scenarios[scenario] = dict(dps=sum(row['dps'] * row['samples'] for row in batches) / samples,
                                       samples=samples, batches=batches)
        nominal = scenarios['nominal']['dps']
        if nominal <= 0:
            ga.setdefault('ineligible', {})[identity] = '正常复测均分≤0，无法定义相对损失'
            continue
        loss = max((nominal - scenarios[name]['dps']) / nominal for name in SCENARIOS[1:])
        qualified.append(dict(identity=identity, nominal=nominal, loss=loss, scenarios=scenarios))
    missing_locations = [key for key, (cached, _, _) in receipts.items()
                         if not cached.get('storage_group_key')]
    locations = (report_locations(missing_locations)
                 if missing_locations and (DATA_ROOT / '.report-locations.jsonl').exists() else {})
    groups = {}
    for key, receipt in receipts.items():
        group = receipt[0].get('storage_group_key') or locations.get(key) or key
        groups.setdefault(group, {})[key] = receipt
    for group, targets in groups.items():
        saved_rows = read_many('batches', [group])
        if len(saved_rows) > 12:
            raise ValueError('发布报告组超过十二份；旧四条保持不变')
        found = set()
        for saved in saved_rows:
            key = saved.get('batch_key')
            if key not in targets:
                continue
            if key in found:
                raise ValueError('发布复测报告重复；旧四条保持不变')
            found.add(key)
            cached, index, scenario = targets[key]
            _validate_saved_batch(saved, key, cached, character, index, scenario,
                                  ready['simulation_config'])
        if found != targets.keys():
            raise ValueError('发布缺少完整复测报告；旧四条保持不变')
        # Only small receipts survive the group; do not retain the last full report.
        del saved_rows, saved
    if len(qualified) < 4:
        reasons = '; '.join(identity[:12] + ': ' + reason for identity, reason in ga.get('ineligible', {}).items())
        raise ValueError('五场景完整复测后合格不同行为不足四条；旧四条保持不变' + ('; ' + reasons if reasons else ''))
    nominal = sorted(qualified, key=lambda row: (-row['nominal'], row['identity']))
    stable = min(qualified, key=lambda row: (row['loss'], -row['nominal'], row['identity']))
    chosen = []
    for row in [nominal[0], stable, *nominal]:
        if row['identity'] not in {item['identity'] for item in chosen}:
            chosen.append(row)
        if len(chosen) == 4:
            break
    result = []
    for row in chosen:
        program = archive[row['identity']]['program']
        if canonicalize_search_program(program, ready['context']['capabilities'])['identity'] != row['identity']:
            raise ValueError('发布程序行为身份不符')
        record = dict.fromkeys(SELECTED_V2_SCHEMA)
        record.update(configuration_key=configuration_key, candidate_id=row['identity'], condition=condition,
            class_name=character.class_name, spec=character.spec, targets=ready['simulation_config']['target_count'],
            program=program, family='ga', score=row['nominal'],
            scores=[item['dps'] for item in row['scenarios']['nominal']['batches']],
            template_sha256=ready['template_sha'], engines=ready['engines'], contract_version=2,
            evaluation=dict(scenarios=row['scenarios'], stability_loss=row['loss'],
                nominal_champion=row['identity'] == nominal[0]['identity'],
                stable_representative=row['identity'] == stable['identity']))
        result.append(record)
    return result
