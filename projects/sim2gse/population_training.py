"""A代际预训练。复用现有评价/报告/TaskStore，不创建第二套模拟后端。"""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack, closing
import hashlib
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import random
import types
import uuid

from runtime import TaskRuntime, TaskCancelled
from search import TaskStore, digest, optimize, mutate, _tuple, _validate_saved_batch, _observe_ga

SCENARIOS = ('nominal', 'jitter', 'pause', 'slow', 'phase')
ALGORITHM = 'ga-easimple-v1'


def _cross(left, right, rng, *, observation=None):
    if observation is not None:
        observation['crossover_cut'] = None
    def wrapped(member):
        return (len(member) == 1 and isinstance(member[0], dict) and member[0].get('kind') == 'Loop')
    if wrapped(left) != wrapped(right):
        return False
    def blocks(member):
        return member[0]['blocks'] if (len(member) == 1 and isinstance(member[0], dict)
                                       and member[0].get('kind') == 'Loop') else member
    a, b = blocks(left), blocks(right)
    if min(len(a), len(b)) < 2:
        return False
    cut = rng.randint(1, min(len(a), len(b)) - 1)
    if observation is not None:
        observation['crossover_cut'] = cut
    if a[cut:] == b[cut:]:
        return False
    a[cut:], b[cut:] = deepcopy(b[cut:]), deepcopy(a[cut:])
    return True


def select_parents(population, count, rng, tournament_size):
    """Production tournament selection, also used by the bounded pilot."""
    return [max((rng.choice(population) for _ in range(tournament_size)),
                key=lambda member: member.fitness) for _ in range(count)]


def vary_offspring(population, toolbox, *, rng, config, capabilities, reference,
                   legal, check, observe, flags=(), counts=None):
    """The shared target/random/crossover gates; no global DEAP random changes."""
    from breeding import target_mutation, random_operations
    children = [toolbox.clone(parent) for parent in population]
    for child in children:
        check()
        if rng.random() < config['target_mutation_probability']:
            if counts is not None: counts['target_triggered'] += 1
            changed, details = target_mutation(list(child), capabilities, rng, reference,
                child.action_summary, legal)
            before = deepcopy(list(child))
            child[:] = changed
            observe(before, child, dict(sampled_mutation='target', **details))
            if child != before:
                if counts is not None: counts['target_changed'] += 1
                del child.fitness.values
        if rng.random() < config['random_mutation_probability']:
            if counts is not None: counts['random_triggered'] += 1
            operations = random_operations(child, capabilities, flags)
            if operations:
                before = deepcopy(list(child))
                details = {}
                child[:] = mutate(child, capabilities, rng, operation_override=rng.choice(operations),
                    observation=details, reset_flags=flags)
                observe(before, child, dict(details, mutation_route='random'))
                if child != before:
                    if counts is not None: counts['random_changed'] += 1
                    del child.fitness.values
    for index in range(1, len(children), 2):
        if rng.random() < config['crossover_probability']:
            if counts is not None: counts['crossover_triggered'] += 1
            before = (deepcopy(list(children[index-1])), deepcopy(list(children[index])))
            toolbox.mate(children[index-1], children[index])
            if counts is not None and any(child != original for child, original in zip(children[index-1:index+1], before)):
                counts['crossover_changed'] += 1
            for child, original in zip(children[index-1:index+1], before):
                if child != original:
                    del child.fitness.values
    return children


def _stage_plan(config, seed, *, scenarios=SCENARIOS):
    # Independent deterministic streams, frozen before the first request.
    rng = random.Random(seed)
    seeds, used = [], set()
    while len(seeds) < 2 + len(scenarios) * config['retest_batches']:
        value = rng.randrange(1, 1000000000)
        if not {value, value - 500000, value + 500000} & used:
            seeds.append(value)
            used.add(value)
    plan = dict(search=dict(iterations=config['coarse_iterations'], seeds=seeds[:1]),
                feedback=dict(iterations=2, seeds=seeds[1:2]))
    offset = 2
    for name in scenarios:
        plan[name] = dict(iterations=config['retest_iterations'],
                          seeds=seeds[offset:offset + config['retest_batches']])
        offset += config['retest_batches']
    return plan


def _evolution(store, capabilities, runtime, config, *, scenarios=SCENARIOS):
    """保留完整换代，按冻结版本选繁殖顺序；每组随机流独立。"""
    from deap import algorithms, base
    from program import canonicalize_search_program, _search_expanded_nodes
    from codec import load_targeting, prepare_block, prepare_castsequence
    from engine import CandidateScoreError
    from search import _coarse_score_failure
    from simulation_config import syntax_for
    capabilities['search_syntax'] = syntax_for(store.state['config']['syntax'])
    from program import check_search_syntax
    for candidate in [*store.state.get('starts', []),
            *(row['program'] for row in store.state.get('archive', [])),
            *(row['program'] for row in store.state.get('ga', {}).get('population', [])),
            *((store.state.get('ga', {}).get('pending') or {}).get('programs', []))]:
        check_search_syntax(candidate, capabilities['search_syntax'])
    observe_search = store.diagnostic_logging and store.state['config']['search_observability'] != 'off'
    policy = (store.state.get('formal_search') or {}).get('coarse_failure_policy')
    if policy is not None:
        from formal_search import COARSE_FAILURE_POLICY
        if not isinstance(policy, dict) or type(policy.get('version')) is not int or policy != COARSE_FAILURE_POLICY:
            raise ValueError('正式粗评候选容错政策不符，不能混接恢复')
    target_masks = load_targeting(runtime=runtime)['target_masks']
    class Fitness(base.Fitness):
        weights = (1.0,)
    class Individual(list):
        pass
    ga = store.state['ga']
    guided = 'target_mutation_probability' in config
    coarse_summaries = {}
    if guided:
        from breeding import VERSION, ORDER
        reference = store.state.get('breeding_reference')
        if config['target_mutation_probability'] > 0:
            from action_summary import checked, scoped
            if not isinstance(reference, dict):
                raise ValueError('目标变异缺少冻结参考成功摘要')
            reference = scoped(checked(reference, reference.get('samples')), capabilities)
            if not any(reference['successes'].values()):
                raise ValueError('目标变异参考没有可比较普通按钮')
        binding = dict(version=VERSION, order=ORDER, probabilities={k: config[k] for k in
            ('target_mutation_probability', 'random_mutation_probability', 'crossover_probability')},
            reference=digest(reference) if config['target_mutation_probability'] > 0 else None)
        binding['order'] = list(binding['order'])
        if ga.get('breeding') is None and (ga.get('phase') != 'initial' or store.state.get('archive')):
            raise ValueError('繁殖策略凭据缺失，不能把旧任务换成新策略续跑')
        if ga.get('breeding') not in (None, binding):
            raise ValueError('繁殖策略或冻结参考已变化，不能恢复旧任务')
        ga['breeding'] = binding
    if ga['phase'] == 'qualified':
        ga['phase'] = 'retest'  # Re-verify all frozen receipts after a failed publication; refill only missing evidence.
    rng = random.Random()
    rng.setstate(_tuple(ga['rng']))
    toolbox = base.Toolbox()
    def individual(row):
        member = Individual(deepcopy(row['program']))
        member.fitness = Fitness((row['score'],))
        if guided:
            member.action_summary = coarse_summaries.get(row['key'])
        return member
    def clone(parent):
        child = deepcopy(parent)
        child.parent_program, child.crossed = deepcopy(list(parent)), False
        return child
    def select(population, count):
        return select_parents(population, count, rng, config['tournament_size'])
    def mate(left, right):
        before = deepcopy(list(left)), deepcopy(list(right))
        details = {} if observe_search else None
        changed = _cross(left, right, rng, observation=details)
        if changed:
            left.crossed = right.crossed = True
        if details is not None:
            for index, child in enumerate((left, right)):
                partner_identity, partner_reason = observed_identity(before[1-index])
                evidence = dict(details, sampled_mutation='crossover',
                    actual_mutation='crossover' if changed else 'no_change',
                    partner_identity=partner_identity, partner_illegal_reason=partner_reason)
                if store.state['config']['search_observability'] == 'full':
                    evidence['partner_program'] = before[1-index]
                observe_child(before[index], child, evidence)
        return left, right
    feedback_for = None
    def observed_identity(program):
        try:
            return canonicalize_search_program(program, capabilities)['identity'], None
        except (TypeError, ValueError, KeyError) as error:
            return None, str(error)
    def observe_child(parent, child, details):
        if not observe_search or not store.state.get('search_observability'):
            return
        identity, reason = observed_identity(child)
        parent_identity, parent_reason = observed_identity(parent)
        if store.state['config']['search_observability'] == 'full':
            details = dict(details, parent_program=deepcopy(list(parent)), child_program=deepcopy(list(child)))
        _observe_ga(store, 'mutation', parent_identity=parent_identity, parent_illegal_reason=parent_reason,
                    candidate_identity=identity, illegal_reason=reason, **details)
    def mutation(member):
        feedback_getter = None if member.crossed else lambda: feedback_for(member.parent_program)
        details = {} if observe_search and store.state.get('search_observability') else None
        options = {'observation': details} if details is not None else {}
        if store.state.get('formal_search'):
            options['reset_flags'] = tuple(dict.fromkeys(kind for _, kind in store.state['config']['reset_events']
                                                        if kind in ('target', 'combat', 'shift', 'ctrl', 'alt')))
        member[:] = mutate(member, capabilities, rng, feedback_getter=feedback_getter, **options)
        if details is not None:
            observe_child(member.parent_program, member, details)
        return member,
    toolbox.register('clone', clone)
    toolbox.register('mate', mate)
    toolbox.register('mutate', mutation)
    # Rebind only this function's globals, never DEAP's shared module.random.
    variation = types.FunctionType(algorithms.varAnd.__code__,
        dict(algorithms.varAnd.__globals__, random=rng), 'group_varAnd')

    legacy_variation = variation
    legal_for_guidance = None
    last_variation_counts = None
    def three_gates(population, toolbox, cross_probability, unused_probability=None):
        nonlocal last_variation_counts
        counts = {route + suffix: 0 for route in ('target', 'random', 'crossover')
                  for suffix in ('_triggered', '_changed')} if store.diagnostic_logging else None
        children = vary_offspring(population, toolbox, rng=rng, config=config,
            capabilities=capabilities, reference=reference, legal=legal_for_guidance,
            check=runtime.check, observe=observe_child,
            flags=tuple(dict.fromkeys(kind for _, kind in store.state['config']['reset_events']
                if kind in ('target', 'combat', 'shift', 'ctrl', 'alt'))), counts=counts)
        last_variation_counts = counts
        return children
    variation = three_gates if guided else legacy_variation

    def execute(*, evaluate, feedback):
        nonlocal feedback_for, legal_for_guidance
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
        legal_for_guidance = key
        def scores(programs, stage='search', index=0, *, record_timeline=True, allow_rejections=False):
            unique = {}
            for program in programs:
                unique.setdefault(key(program), program)
            if store.diagnostic_logging:
                counters = getattr(store, 'counter_target', store.state)
                counters['canonicalized_duplicates'] = counters.get('canonicalized_duplicates', 0) + len(programs) - len(unique)
            results = {}
            items = list(unique.items())
            error = None
            rejected = False
            def collect(identity, future):
                nonlocal error, rejected
                try:
                    results[identity] = future.result()
                    if guided and stage == 'search':
                        coarse_summaries[identity] = results[identity].get('action_summary')
                    if timeline is not None and record_timeline:
                        row = results[identity]
                        timeline.score(dict(key=identity, score=row['dps'], batches=[row]),
                                       stage, 'training')
                except CandidateScoreError as failure:
                    proof = (_coarse_score_failure(store.state, identity)
                             if policy and allow_rejections and stage == 'search' else None)
                    if proof is None:
                        error = error or failure
                    else:
                        results[identity] = None
                        rejected = True
                        rejections = ga.setdefault('coarse_rejections', {})
                        if identity not in rejections:
                            rejections[identity] = dict(proof, generation=ga['generation'], phase=ga['phase'])
                            store.state.setdefault('errors', []).append(dict(kind='coarse_invalid_score',
                                candidate_key=identity, **rejections[identity]))
                except BaseException as failure:
                    error = error or failure
            if store.memory_execution and stage == 'search':
                at = 0
                pending = {}
                with ThreadPoolExecutor(max_workers=config['max_processes']) as pool:
                    while pending or (error is None and at < len(items)):
                        runtime.check()
                        # Each slot owns the complete compile -> simulate -> validate call.
                        while error is None and at < len(items) and len(pending) < config['max_processes']:
                            runtime.check()
                            identity, program = items[at]
                            pending[pool.submit(evaluate, program, stage, index)] = (at, identity)
                            at += 1
                        done, _ = wait(pending, return_when=FIRST_COMPLETED)
                        for future in sorted(done, key=lambda item: pending[item][0]):
                            _, identity = pending.pop(future)
                            collect(identity, future)
                if error is not None:
                    raise error
                return [results[key(program)] for program in programs]
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
                    rejected = False
                    for identity, future in futures:
                        collect(identity, future)
                    if rejected or len(store.report_buffer) >= 12:
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
            rows = scores(store.state['starts'], allow_rejections=bool(policy))
            ga['population'] = [dict(program=deepcopy(program), key=row['candidate_key'], score=row['dps'])
                                for program, row in zip(store.state['starts'], rows) if row is not None]
            if not ga['population']:
                raise ValueError('没有可靠的正式粗评候选；全部候选评分无效')
            if policy:
                ga['effective_population_size'] = len(ga['population'])
            ga.update(phase='breed', baseline=baseline())
            store.checkpoint(**(dict(boundary='initial') if store.memory_execution else {}))
        while ga['phase'] == 'breed':
            runtime.check()
            if policy and (type(ga.get('effective_population_size')) is not int
                    or ga['effective_population_size'] != len(ga['population']) or not ga['population']):
                raise ValueError('正式有效种群大小与已冻结检查点不符')
            population = [individual(row) for row in ga['population']]
            pending = ga.get('pending')
            if pending is None:
                children = variation(select(population, len(population)), toolbox,
                    config['crossover_probability'], config.get('mutation_probability'))
                pending = dict(programs=[deepcopy(list(child)) for child in children],
                               regenerations=[0] * len(children), rng=rng.getstate())
                if last_variation_counts is not None:
                    pending['breeding_counts'] = deepcopy(last_variation_counts)
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
                        config['crossover_probability'], config.get('mutation_probability'))
                    if last_variation_counts is not None:
                        for name, value in last_variation_counts.items():
                            counters = pending.setdefault('breeding_counts', {})
                            counters[name] = counters.get(name, 0) + value
                    pending['programs'][slot] = deepcopy(list(children[0]))
                    pending['regenerations'][slot] += 1
                    pending['rng'] = rng.getstate()
                    store.checkpoint()
            if policy and len(pending['programs']) != ga['effective_population_size']:
                raise ValueError('正式子代槽数量与已冻结种群不符')
            rows = scores(pending['programs'], allow_rejections=bool(policy))
            members, fallbacks = [], {}
            for slot, (program, row) in enumerate(zip(pending['programs'], rows)):
                if row is None:
                    previous = deepcopy(ga['population'][slot])
                    members.append(previous)
                    fallbacks[str(slot)] = dict(rejected_key=key(program), retained_key=previous['key'])
                else:
                    members.append(dict(program=deepcopy(program), key=row['candidate_key'], score=row['dps']))
            current = baseline()
            improved = len(current) > len(ga['baseline']) or any(
                value > old for value, old in zip(current, ga['baseline']))
            ga.update(population=members,
                generation=ga['generation'] + 1, rng=pending['rng'], pending=None,
                baseline=current, stagnant=0 if improved else ga['stagnant'] + 1)
            if pending.get('breeding_counts'):
                counters = ga.setdefault('breeding_counts', {})
                for name, value in pending['breeding_counts'].items():
                    counters[name] = counters.get(name, 0) + value
            if policy:
                ga['last_fallbacks'] = fallbacks
            if ga['stagnant'] >= config['stagnation_generations']:
                ga.update(phase='retest', finalists=[row['key'] for row in ranking()])
                if timeline is not None and store.state.get('formal_search'):
                    timeline.stop('stagnation')
                    timeline.mark('normal_retest_started')
            store.checkpoint(**(dict(boundary='retest' if ga['phase'] == 'retest' else 'generation')
                                if store.memory_execution else {}))
        archive = {row['key']: row for row in store.state['archive']}
        if ga['phase'] == 'retest':
            finalists = ga['finalists']
            programs = [archive[identity]['program'] for identity in finalists]
            for scenario in scenarios:
                for index in range(config['retest_batches']):
                    runtime.check()
                    rows = scores(programs, scenario, index)
                    for identity, row in zip(finalists, rows):
                        ga['finals'].setdefault(identity, {}).setdefault(scenario, {})[str(index)] = row
                    # Receipts live in the bounded finalist state; reports flush at 12 or phase/cancel.
            ga['phase'] = 'qualified'
            store.checkpoint()
            if timeline is not None and store.state.get('formal_search'):
                timeline.mark('normal_retest_completed')
        return ga
    return execute


def _recovery_version(folder):
    values = []
    for name in ('identity.json', 'task.sqlite3', 'task.sqlite3-wal', 'task.sqlite3-journal'):
        path = folder / name
        if not path.is_file():
            values.append(None)
            continue
        try:
            with path.open('rb') as source:
                values.append(hashlib.file_digest(source, 'sha256').hexdigest())
        except FileNotFoundError:
            values.append(None)
    return tuple(values)


def _unfinished(workspace, *, template=None, targets=None, scope=None, include_state=False,
                recovery=None, _owners=None):
    """Startup-only scan of known task manifests, never a per-score fallback."""
    import sqlite3
    for folder, (_, _, version) in (recovery or {}).items():
        if _recovery_version(folder) != version:
            raise ValueError('GA恢复清单或检查点在准备期间已变化，请重新开始恢复')
    for path in (Path(workspace).resolve() / 'ga').glob('*/*/identity.json'):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if (template is not None and manifest.get('template_path') != str(Path(template).resolve())
                or targets is not None and manifest['environment']['simulation']['target_count'] != targets
                or scope is not None and path.parent.parent.name != scope):
            continue
        database = path.with_name('task.sqlite3')
        if not database.is_file():
            continue
        borrowed = (recovery or {}).get(path.parent)
        store, version = None, None
        if borrowed is not None:
            saved_manifest, store, version = borrowed
            if manifest != saved_manifest:
                raise ValueError('GA恢复清单或检查点在准备期间已变化，请重新开始恢复')
            state = store.state
        else:
            with closing(sqlite3.connect('file:' + database.as_posix() + '?mode=ro', uri=True)) as db:
                try:
                    # 只用小字段决定从哪个入口完整验真；已完成旧格式仍沿原读取。
                    open_snapshot = False
                    if (include_state and _owners is not None
                            and manifest.get('search_config', {}).get('memory_execution')):
                        try:
                            row = db.execute("SELECT value FROM state_fields WHERE key='ga'").fetchone()
                        except sqlite3.OperationalError:
                            row = None  # 无逐字段表的旧格式仍由原加载器完整验真。
                        if row:
                            try:
                                published = json.loads(row[0]).get('phase') == 'published'
                            except (ValueError, TypeError, AttributeError):
                                published = False
                            open_snapshot = not published
                    if not open_snapshot:
                        state = TaskStore.load_state(db)
                except sqlite3.OperationalError as error:
                    raise ValueError('GA任务检查点不完整: ' + str(path.parent)) from error
            if open_snapshot:
                version = _recovery_version(path.parent)
                store = TaskStore(path.parent, memory_execution=True,
                    checkpoint_interval_seconds=manifest['search_config'].get('checkpoint_interval_seconds', 600))
                try:
                    if _recovery_version(path.parent) != version:
                        raise ValueError('GA恢复清单或检查点在准备期间已变化，请重新开始恢复')
                    state = store.state
                    if state.get('ga', {}).get('phase') == 'published':
                        store.close(write_diagnostics=False)
                        continue
                except BaseException:
                    store.close(write_diagnostics=False)
                    raise
                _owners.callback(store.close, write_diagnostics=False)
        if state.get('ga', {}).get('phase') != 'published':
            yield ((path.parent, manifest, state, store, version) if store is not None else
                   (path.parent, manifest, state)) if include_state else (path.parent, manifest)


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
              prepare_only=False, materials=None, diagnostic_logging=None, search_config=None,
              expected_key=None, timeline_origin=None, burst_identity=None, training_overrides=None,
              new_search_config=None):
    with ExitStack() as recovery_owners:
        import seed_training as seeds
        from task import _write_json, _rule_hashes
        from engine import ROOT
        if any((Path(workspace) / str(targets)).glob('*/identity.json')):
            raise ValueError('旧逐材料训练目录不能作为GA任务恢复；请使用新工作目录，原完整成果仍可读取')
        frozen = list(_unfinished(workspace, template=template, targets=targets, include_state=True,
                                  _owners=None if prepare_only else recovery_owners))
        if len(frozen) > 1:
            raise ValueError('同模板/目标存在多个未完成GA任务')
        options = seeds._training_options(search_config, diagnostic_logging)
        inputs = None
        if frozen:
            from simulation_config import reject_removed_search_settings
            from search import config_for
            saved = frozen[0][1]['search_config']
            from simulation_config import verify_syntax_receipt
            verify_syntax_receipt(frozen[0][1].get('syntax'), saved.get('syntax'))
            if 'syntax' not in saved:
                raise ValueError('旧训练任务缺少冻结语法范围，请创建新任务')
            reject_removed_search_settings(saved)
            seeds._check_pretraining_observations(saved)
            observation = {'diagnostic_logging', 'diagnostics', 'search_observability', 'search_timeline'}
            explicit = {key: value for key, value in options.items() if value is not None}
            if 'syntax' in explicit:
                explicit['syntax'] = dict(saved['syntax'], **explicit['syntax'])
            frozen_runtime = config_for(saved, training=True)
            checkpoint = frozen[0][2].get('config') or {}
            # 计算仍取不可变清单；省略观测取最近可靠检查点，不跳回初次选择。
            latest = dict(saved, **{key: checkpoint[key] for key in observation if key in checkpoint})
            seeds._check_pretraining_observations(latest)
            resumed = config_for(dict(latest, **explicit), training=True)
            if (any(resumed[key] != frozen_runtime[key]
                    for key in explicit if key not in observation)
                    or any(value != frozen[0][1]['training_config'][key]
                           for key, value in (training_overrides or {}).items())):
                raise ValueError('恢复训练配置发生变化，请创建新任务')
            config = frozen[0][1]['training_config']
            sources = [source for row in frozen[0][1]['sources'] for source in row['sources']]
            materials = None  # Resume the original material manifest, not today's registry/subset.
            inputs = seeds._training_inputs(template, targets, cancel_event=cancel_event,
                use_burst=use_burst, max_processes=config['max_processes'],
                burst_identity=burst_identity, _frozen_config=resumed)
        elif new_search_config is not None:
            inputs = seeds._training_inputs(template, targets, cancel_event=cancel_event,
                use_burst=use_burst, max_processes=config['max_processes'],
                burst_identity=burst_identity, _frozen_config=new_search_config)
        from simulation_config import load_training_config
        config = load_training_config(_document={'training': config})
        ready = seeds.ensure_prepared(template, targets, workspace, cancel_event=cancel_event,
            use_burst=use_burst, sources=sources, materials=materials, inputs=inputs,
            max_processes=config['max_processes'], search_config=options,
            burst_identity=burst_identity)
        if 'mutation_probability' in config or not all(k in config for k in
                ('target_mutation_probability', 'random_mutation_probability')):
            raise ValueError('旧训练总变异参数已退役，未完成任务不能换策略续跑')
        context = ready['context']
        if not context or not ready['queue']:
            raise ValueError('本组没有有效训练材料')
        configuration_key = context['configuration_key']
        if expected_key is not None and configuration_key != expected_key:
            raise ValueError('受检标准模板实际英雄/目标与冻结训练分组不符')
        from simulation_config import describe_syntax
        syntax_result = dict(syntax=ready['config']['syntax'], syntax_summary=describe_syntax(ready['config']['syntax']),
            source_rejections=[dict(source_id=row['source_id'], reason=row['reason'])
                               for row in ready.get('entries', []) if row['status'] == 'rejected'])
        if prepare_only:
            return dict(status='prepared', algorithm=ALGORITHM, configuration_key=configuration_key,
                        population_size=len(ready['queue']), config_key=ready['config_key'],
                        preparation=ready['preparation'], **syntax_result)
        scope = seeds.shared_scope(configuration_key, ready['config']['syntax'])
        if frozen and frozen[0][0].parent.name != scope:
            raise ValueError('当前分组与冻结恢复任务不一致，拒绝换组恢复；请使用原模板或新工作目录')
        root = Path(workspace).resolve() / 'ga' / scope
        environment = dict(template=ready['template_sha'], engines=ready['engines'],
            simulation=ready['simulation_config'], burst=context['burst'],
            rules=_rule_hashes(relative_to=ROOT))
        retained = {row[0]: (row[1], row[3], row[4]) for row in frozen if len(row) > 3 and row[3] is not None}
        active = list(_unfinished(workspace, scope=scope, recovery=retained))
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
            from simulation_config import syntax_receipt
            from breeding import VERSION, ORDER
            manifest = dict(breeding=dict(version=VERSION, order=list(ORDER)),
                environment=environment, training_config=config, template_path=str(Path(template).resolve()),
                starts=[row['program'] for row in ready['queue']], sources=ready['queue'],
                breeding_reference=context['native'].get('action_summary'),
                search_config=ready['config'], syntax=syntax_receipt(ready['config']['syntax']),
                seed=uuid.uuid4().int % 1000000000)
            manifest['stage_plan'] = _stage_plan(config, manifest['seed'])
            folder = root / uuid.uuid4().hex
            folder.mkdir(parents=True)
            _write_json(folder / 'identity.json', manifest, atomic=True)
        from breeding import VERSION, ORDER
        if manifest.get('breeding') != dict(version=VERSION, order=list(ORDER)):
            raise ValueError('训练繁殖版本或顺序缺失/不兼容，请新建任务')
        profile = folder / 'standard.simc'
        if not profile.exists():
            profile.write_text(ready['text'], encoding='utf-8')
        elif profile.read_text(encoding='utf-8') != ready['text']:
            raise ValueError('GA冻结标准角色副本已变化')
        store = (frozen[0][3] if active and frozen and len(frozen[0]) > 3
                 and frozen[0][0] == folder else None)
        if store is None:
            store = TaskStore(folder, **(dict(memory_execution=True,
                checkpoint_interval_seconds=ready['config']['checkpoint_interval_seconds'])
                if ready['config'].get('memory_execution') else {}))
            recovery_owners.callback(store.close, write_diagnostics=False)
        character = replace(ready['character'], spec_id=context['native']['identity']['spec_id'],
                            race=context['native']['identity']['race'])
        execution_config = ready['config']
        runtime = TaskRuntime(float('inf'), cancel_event=cancel_event,
                              diagnostic_logging=execution_config['diagnostic_logging'])
        runtime.profile_texts = {str(profile.resolve()): ready['text']}
        timeline = None
        if execution_config['search_timeline']:
            from search_timeline import Timeline
            timeline = Timeline(origin=timeline_origin, context=dict(configuration_key=configuration_key,
                simulation_config=ready['simulation_config']), resumed=bool(active))
            timeline.configure(profile_sha=ready['template_sha'], engines=ready['engines'],
                simulation_config=ready['simulation_config'], config=manifest['search_config'], burst=context['burst'])
            timeline.context['algorithm'].update(training=ALGORITHM, random_seed=manifest['seed'], training_config=config)
            runtime.search_timeline = timeline
        # 前置检查全部通过，移交给原执行路径唯一的最终关闭。
        recovery_owners.pop_all()
        try:
            if not store.state:
                rng = random.Random(manifest['seed'])
                store.state.update(run_id=uuid.uuid4().hex, starts=manifest['starts'], config=execution_config,
                    capabilities=context['capabilities'], configuration_key=configuration_key, burst=context['burst'],
                    breeding_reference=manifest.get('breeding_reference'),
                    ga=dict(algorithm=ALGORITHM, phase='initial', generation=0, stagnant=0,
                            population=[], pending=None, rng=rng.getstate(), finals={}))
                if store.memory_execution:
                    from result_store import seed_selected_revision
                    store.state['seed_selection_base'] = seed_selected_revision(scope)
            if store.state.get('breeding_reference') != manifest.get('breeding_reference'):
                raise ValueError('训练参考摘要与冻结任务不符')
            if (store.state.get('ga', {}).get('algorithm') != ALGORITHM
                    or store.state.get('starts') != manifest['starts']):
                raise ValueError('GA检查点算法或冻结初始种群身份不符')
            if (store.state.get('config', {}).get('syntax') != manifest['search_config']['syntax']
                    or store.state.get('capabilities', {}).get('search_syntax') != manifest['search_config']['syntax']):
                raise ValueError('GA检查点冻结语法范围不符')
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
                if store.memory_execution:
                    store.flush_reports(final=True)
                    _publish_seed_evidence(ga, store, manifest, character, ready)
                selected = _selected(ga, store, manifest, character, ready, configuration_key)
                runtime.check()
                # Evidence verification precedes the only current-snapshot replacement.
                result_store = __import__('result_store')
                if store.memory_execution:
                    result_store.publish_seed_selected(scope, selected, store.state['seed_selection_base'],
                        schema=seeds.SELECTED_V2_SCHEMA)
                else:
                    result_store.write('seed_selected', scope, selected, schema=seeds.SELECTED_V2_SCHEMA)
                ga['phase'] = 'published'
                store.state['status'] = 'completed'
                if not store.memory_execution:
                    store.checkpoint()
                if timeline is not None:
                    timeline.saved('completed')
            return dict(status='completed', algorithm=ALGORITHM, breeding=ga.get('breeding'),
                breeding_statistics=(dict(status='collected', counts=ga.get('breeding_counts', {}))
                    if execution_config['diagnostic_logging'] else dict(status='not_collected')),
                population_size=len(manifest['starts']),
                complete_generations=ga['generation'], configuration_key=configuration_key,
                selected=len(selected), task_path=str(folder), training_config=config,
                ineligible=ga.get('ineligible', {}), **syntax_result)
        except BaseException as error:
            store.state.update(status='paused', error=str(error))
            store.checkpoint(**(dict(boundary='pause') if store.memory_execution else {}))
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


def _retest_scores(ga, store, *, condition, stage_plan, config, character, simulation_config,
                   scenarios=SCENARIOS):
    from result_store import DATA_ROOT, iter_group, report_locations
    receipts = {}
    qualified = []
    for identity in ga['finalists']:
        results = {}
        for scenario in scenarios:
            batches = [ga['finals'][identity][scenario][str(index)]
                       for index in range(config['retest_batches'])]
            for index, row in enumerate(batches):
                cached = store.batch(row['batch_key'])
                if not cached or cached.get('status') != 'success':
                    raise ValueError('发布缺少可靠复测批次')
                request = cached['request']
                if cached.get('storage_version') == 3:
                    row.update(storage_version=3, storage_group_key=cached['storage_group_key'])
                    row.pop('cached', None)
                expected_seed = stage_plan[scenario]['seeds'][index]
                if (digest(request) != row['batch_key'] or request['condition'] != condition
                        or request['behavior_identity'] != identity or request['purpose'] != scenario
                        or request['seed'] != expected_seed
                        or request['iterations'] != config['retest_iterations']
                        or any(row[field] != cached[field] for field in ('dps', 'samples'))
                        or row['candidate_key'] != identity):
                    raise ValueError('发布复测凭据与冻结候选/条件/成绩不符')
                if row['batch_key'] in receipts:
                    raise ValueError('发布复测凭据重复；旧四条保持不变')
                receipts[row['batch_key']] = (cached, index, scenario)
            samples = sum(row['samples'] for row in batches)
            results[scenario] = dict(dps=sum(row['dps'] * row['samples'] for row in batches) / samples,
                                       samples=samples, batches=batches)
        nominal = results['nominal']['dps']
        if len(scenarios) > 1 and nominal <= 0:
            ga.setdefault('ineligible', {})[identity] = '正常复测均分≤0，无法定义相对损失'
            continue
        loss = max(((nominal - results[name]['dps']) / nominal for name in scenarios[1:]), default=0.)
        qualified.append(dict(identity=identity, nominal=nominal, loss=loss, scenarios=results))
    if getattr(store, 'memory_execution', False) and receipts and all(
            getattr(store, 'published_report_receipts', {}).get(key) == digest(cached)
            for key, (cached, _, _) in receipts.items()):
        return qualified
    missing_locations = [key for key, (cached, _, _) in receipts.items()
                         if not cached.get('storage_group_key')]
    locations = (report_locations(missing_locations)
                 if missing_locations and (DATA_ROOT / '.report-locations.jsonl').exists() else {})
    groups = {}
    for key, receipt in receipts.items():
        group = receipt[0].get('storage_group_key') or locations.get(key) or key
        groups.setdefault(group, {})[key] = receipt
    for group, targets in groups.items():
        maximum = 64 if all(row[0].get('storage_version') == 3 for row in targets.values()) else 12
        found = set()
        for count, saved in enumerate(iter_group('batches', group), 1):
            if count > maximum:
                raise ValueError('发布报告组超过对应版本上限；旧四条保持不变')
            key = saved.get('batch_key')
            if key not in targets:
                continue
            if key in found:
                raise ValueError('发布复测报告重复；旧四条保持不变')
            found.add(key)
            cached, index, scenario = targets[key]
            _validate_saved_batch(saved, key, cached, character, index, scenario,
                                  simulation_config)
        if found != targets.keys():
            raise ValueError('发布缺少完整复测报告；旧四条保持不变')
        # Only small receipts survive the group; do not retain the last full report.
        if found:
            del saved
    return qualified


_SEED_EVIDENCE_JSON = ('manifest', 'capabilities', 'ga', 'receipts', 'storage', 'character', 'configuration_key')


def _read_seed_evidence(group, checksum):
    import result_store
    from source_catalog import bounded_digest
    rows = result_store.read_records('seed_evidence', group)
    if len(rows) != 1:
        raise ValueError('新版训练完整来源证据缺失')
    record = dict(rows[0])
    for key in _SEED_EVIDENCE_JSON:
        if isinstance(record.get(key), str):
            record[key] = json.loads(record[key])
    if bounded_digest(record) != checksum:
        raise ValueError('新版训练完整来源证据摘要不符')
    return record


def _publish_seed_evidence(ga, store, manifest, character, ready):
    """只保存一次冻结输入与完整复测目录；原生报告仍保留原有结构。"""
    import result_store
    from source_catalog import bounded_digest
    final_keys = {row['batch_key'] for identity in ga['finalists']
                  for batches in ga['finals'][identity].values() for row in batches.values()}
    receipts = {key: store.batch(key) for key in sorted(final_keys)}
    finals = {identity: {scenario: {index: dict(row) for index, row in batches.items()}
                        for scenario, batches in scenarios.items()}
              for identity, scenarios in ga['finals'].items()}
    for identity in ga['finalists']:
        for batches in finals[identity].values():
            for row in batches.values():
                cached = receipts[row['batch_key']]
                row.update(storage_version=3, storage_group_key=cached['storage_group_key'])
                row.pop('cached', None)
    storage = {key: value for key, value in store.state['evidence_storage'].items()
               if key not in ('seed_source_group', 'seed_source_digest')}
    record = dict(run_id=store.state['run_id'], condition=digest(manifest),
        configuration_key=store.state['configuration_key'],
        profile_text=ready['text'], manifest=manifest,
        capabilities=store.state['capabilities'],
        character=dict(spec_id=character.spec_id, race=character.race),
        ga=dict(finalists=ga['finalists'], finals=finals,
                **(dict(breeding=ga['breeding']) if ga.get('breeding') else {})),
        receipts=receipts, storage=storage)
    checksum = bounded_digest(record)
    group = store.state['run_id'] + '_s' + checksum[:20]
    if not result_store.read_records('seed_evidence', group):
        schema = dict(run_id='VARCHAR', condition='VARCHAR', profile_text='VARCHAR',
                      **dict.fromkeys(_SEED_EVIDENCE_JSON, 'JSON'))
        result_store.write('seed_evidence', group, [record], schema=schema)
    _read_seed_evidence(group, checksum)
    store.state['evidence_storage'].update(seed_source_group=group, seed_source_digest=checksum)


def verify_selected_evidence(rows):
    """独立读取完整来源和全部入围者报告，重新选出四条；不补算、不写入。"""
    from types import SimpleNamespace
    import result_store
    from seed_training import decode, template_character
    decoded = [{key: decode(value) if key in ('configuration_key', 'program', 'engines', 'evaluation')
                else value for key, value in row.items()} for row in rows]
    storage = decoded[0]['evaluation']['evidence_storage']
    if any(row['evaluation']['evidence_storage'] != storage for row in decoded):
        raise ValueError('新版训练四条的完整来源证据不一致')
    record = _read_seed_evidence(storage['seed_source_group'], storage['seed_source_digest'])
    if any(row['configuration_key'] != record['configuration_key'] for row in decoded):
        raise ValueError('新版训练四条分组与冻结完整来源证据不符')
    manifest = record['manifest']
    condition = digest(manifest)
    if (record['condition'] != condition or any(row['condition'] != condition for row in decoded)
            or record['storage'] != {key: value for key, value in storage.items()
                                   if key not in ('seed_source_group', 'seed_source_digest')}
            or hashlib.sha256(record['profile_text'].encode('utf-8')).hexdigest()
               != manifest['environment']['template']
            or manifest['stage_plan'] != _stage_plan(manifest['training_config'], manifest['seed'])):
        raise ValueError('新版训练冻结输入与完整来源证据不符')
    archive = result_store.read_search_records(storage, record['run_id'], condition=condition,
                                               columns=['candidate_key', 'program'])
    store = SimpleNamespace(memory_execution=True, published_report_receipts={},
        state=dict(archive=[dict(key=row['candidate_key'], program=row['program']) for row in archive],
                   evidence_storage=storage), batch=lambda key: record['receipts'].get(key))
    character = replace(template_character(record['profile_text']), **record['character'])
    ready = dict(template_sha=manifest['environment']['template'], engines=manifest['environment']['engines'],
                 simulation_config=manifest['environment']['simulation'],
                 context=dict(capabilities=record['capabilities']))
    selected = _selected(record['ga'], store, manifest, character, ready, record['configuration_key'])
    if digest(selected) != digest(decoded):
        raise ValueError('新版训练四条与完整来源证据重新计算结果不符')


def _selected(ga, store, manifest, character, ready, configuration_key):
    from seed_training import SELECTED_V2_SCHEMA
    from program import canonicalize_search_program
    from simulation_config import syntax_receipt
    archive = {row['key']: row for row in store.state['archive']}
    memory_mode = getattr(store, 'memory_execution', store.state.get('execution_storage_version') == 3)
    condition = digest(manifest)
    qualified = _retest_scores(ga, store, condition=condition,
        stage_plan=manifest['stage_plan'], config=manifest['training_config'], character=character,
        simulation_config=ready['simulation_config'])
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
            template_sha256=ready['template_sha'], engines=ready['engines'], contract_version=3 if memory_mode else 2,
            evaluation=dict(**(dict(breeding=deepcopy(ga['breeding'])) if ga.get('breeding') else {}),
                syntax=syntax_receipt(ready['context']['capabilities']['search_syntax']),
                program_digest=digest(program),
                scenarios=row['scenarios'], stability_loss=row['loss'],
                nominal_champion=row['identity'] == nominal[0]['identity'],
                stable_representative=row['identity'] == stable['identity']))
        if memory_mode:
            record['evaluation']['evidence_storage'] = deepcopy(store.state['evidence_storage'])
        result.append(record)
    return result
