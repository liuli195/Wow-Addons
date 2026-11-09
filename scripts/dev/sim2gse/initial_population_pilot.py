"""Run the isolated, bounded initial-population pilot; never publish training seeds."""
import argparse
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import runpy
import statistics
import sys
import threading
import time
import uuid

ENTRY = time.monotonic()
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'projects/sim2gse'))
PILOTS = ROOT / '.local/sim2gse/population-expansion-pilot'


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


class PilotBudget:
    def __init__(self, plan, output, deadline):
        from runtime import TaskRuntime
        self.plan, self.output, self.deadline = plan, output, deadline
        self.runtime = TaskRuntime(max(0, deadline - time.monotonic()))
        self.lock = threading.Lock()
        self.counts = dict(native_attempts=0, native_starts=0, requested_iterations=0)

    @contextmanager
    def measured_engine(self):
        import engine
        from runtime import BudgetExceeded
        original = engine.run

        def run(profile, folder, mode='baseline', options=(), **kwargs):
            self.runtime.check()
            iterations = 100
            for option in options:
                if option.startswith('iterations='):
                    iterations = int(option.split('=', 1)[1])
            with self.lock:
                if (self.counts['native_attempts'] >= self.plan['limits']['native_starts']
                        or self.counts['requested_iterations'] + iterations
                        > self.plan['limits']['requested_iterations']):
                    raise BudgetExceeded('探路已达到引擎请求上限')
                self.counts['native_attempts'] += 1
                self.counts['requested_iterations'] += iterations
                write(self.output / 'budget.json', self.counts)
            on_start = kwargs.get('on_start')

            def started():
                with self.lock:
                    self.counts['native_starts'] += 1
                    write(self.output / 'budget.json', self.counts)
                if on_start:
                    on_start()

            kwargs.update(runtime=self.runtime, on_start=started)
            return original(profile, folder, mode, options, **kwargs)

        engine.run = run
        try:
            yield
        finally:
            engine.run = original


def compare(output, plan, budget):
    import engine
    import result_store
    import seed_training
    from action_summary import button_key, checked, scoped
    from deap import base
    from population_training import SCENARIOS, _cross, _stage_plan, select_parents, vary_offspring
    from program import canonicalize_search_program
    from search import TaskStore, digest, optimize

    if result_store._BOUND_PROJECT is not None:
        raise ValueError('探路必须使用未绑定生产项目的新进程')
    # Freeze existing production inputs read-only before changing the output center.
    from burst import select_definition
    template = engine.training_template()
    definition = select_definition(seed_training.template_character(template.read_text(encoding='utf-8')))
    sources = seed_training.registry_rows()
    write(output / 'sources.json', sources)
    write(output / 'burst-definition.json', definition)
    result_store.DATA_ROOT = PILOTS / 'data'
    result_store._REPORT_LOCATIONS = None
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    result_store.ensure_available()
    result_store.write('burst_definitions', f"current_{definition['spec_id']}", [definition])
    training_config = plan['training_config']
    inputs = seed_training._training_inputs(template, 1, use_burst=True,
        max_processes=training_config['max_processes'], _frozen_config=plan['search_config'])
    ready = seed_training.ensure_prepared(template, 1, output / 'workspace', sources=sources,
        use_burst=True, max_processes=training_config['max_processes'], inputs=inputs)
    budget.runtime.check()
    if not ready['context'] or not ready['queue']:
        raise ValueError('当前原子语法下没有有效原材料，未运行对比')
    context = ready['context']
    capabilities = context['capabilities']
    reference = scoped(checked(context['native'].get('action_summary'),
                               context['native']['samples']), capabilities)
    if not sum(reference['successes'].values()):
        raise ValueError('当前参考没有可比较的普通技能')
    starts = [row['program'] for row in ready['queue']]
    config = ready['config']
    stage_plan = _stage_plan(dict(training_config, retest_iterations=32, retest_batches=2), plan['seed'])
    manifest = dict(plan, status='frozen', sources=digest(sources), template_sha256=ready['template_sha'],
        engines=ready['engines'], configuration_key=context['configuration_key'],
        preparation=ready['preparation'], preparation_key=ready['config_key'],
        search_config=config, training_config=training_config, stage_plan=stage_plan,
        reference=reference, original_starts=starts)
    manifest['code_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__).resolve(), ROOT / 'projects/sim2gse/population_training.py',
                     ROOT / 'projects/sim2gse/breeding.py')}
    write(output / 'manifest.json', manifest)
    profile = output / 'standard.simc'
    profile.write_text(ready['text'], encoding='utf-8')
    character = replace(ready['character'], spec_id=context['native']['identity']['spec_id'],
                        race=context['native']['identity']['race'])
    report = dict(status='running', published=False, evidence_kind=plan['evidence_kind'],
        data_root=str(result_store.DATA_ROOT), manifest_digest=digest(manifest),
        target_count=1, counts=budget.counts, groups={}, untested_scenarios=list(SCENARIOS[1:]))
    (output / 'task').mkdir()
    store = TaskStore(output / 'task')
    store.state.update(run_id=uuid.uuid4().hex, starts=starts, config=config,
        capabilities=capabilities, burst=context['burst'], breeding_reference=reference,
        configuration_key=context['configuration_key'])

    def key(program):
        return canonicalize_search_program(program, capabilities)['identity']

    def runner(*, evaluate, feedback):
        scoring_batches = {}
        report['scoring_requests'] = report['scoring_cache_hits'] = 0

        def score(program, stage='search', index=0):
            budget.runtime.check()
            row = evaluate(program, stage, index)
            report['scoring_requests'] += 1
            report['scoring_cache_hits'] += bool(row['cached'])
            scoring_batches[row['batch_key']] = row['samples']
            report['unique_scoring_samples'] = sum(scoring_batches.values())
            if len(store.report_buffer) >= 8:
                store.checkpoint()
            return row

        parents = []
        calibration_seconds = []
        for program in starts:
            before = time.monotonic()
            row = score(program)
            if not row['cached']:
                calibration_seconds.append(time.monotonic() - before)
            parents.append(dict(program=program, key=key(program), score=row['dps'],
                                action_summary=scoped(row['action_summary'], capabilities)))
            if len(parents) == min(2, len(starts)):
                remaining_batches = len(starts) - len(parents) + 64 + 24
                estimate = (statistics.mean(calibration_seconds) * remaining_batches
                            if calibration_seconds else None)
                report['calibration'] = dict(scored_parents=len(parents),
                    conservative_remaining_requested_iterations=32 * remaining_batches,
                    estimated_scoring_seconds=estimate,
                    note='按不命中缓存且不重试估算；不保证耗时或收益')
                write(output / 'progress.json', report)
                if (32 * remaining_batches + budget.counts['requested_iterations']
                        > plan['limits']['requested_iterations']
                        or estimate is not None and estimate * 1.25 > budget.runtime.remaining_seconds):
                    from runtime import BudgetExceeded
                    raise BudgetExceeded('少量评分校准表明预算不足以完成本次对照和独立复评')
        report['baseline'] = dict(count=len(parents), mean=statistics.mean(p['score'] for p in parents),
            best=max(p['score'] for p in parents), worst=min(p['score'] for p in parents),
            rows=[dict(identity=p['key'], dps=p['score']) for p in parents])
        original_best = sorted(parents, key=lambda row: (-row['score'], row['key']))[:4]
        if len(original_best) < 4:
            raise ValueError('有效原材料不足四条，本次不能作四候选对照')
        report['baseline']['selected'] = [dict(identity=row['key'], program=row['program'], coarse=row['score'])
                                          for row in original_best]
        report['baseline']['locked'] = [row['key'] for row in original_best]
        write(output / 'progress.json', report)

        rng = random.Random(plan['seed'] + 1)
        actions = capabilities['actions']
        total = sum(reference['successes'].values())
        weights = [.5 * reference['successes'].get(button_key(a), 0) / total + .5 / len(actions)
                   for a in actions]
        names = [a['simc_action'] for a in actions]
        bound = 128 - len(capabilities.get('precombat_actions', []))
        if bound < 1:
            raise ValueError('战前动作占满长度，无法新增普通循环')
        generated, seen = [], {p['key'] for p in parents}
        new_attempts = 0
        for _ in range(352):
            budget.runtime.check()
            new_attempts += 1
            program = [[name] for name in rng.choices(names, weights, k=rng.randint(1, bound))]
            try:
                identity = key(program)
            except ValueError:
                continue
            if identity in seen:
                continue
            seen.add(identity)
            generated.append(program)
            if len(generated) == 32:
                break
        if len(generated) != 32:
            raise ValueError('新增起点在352次提案内未补足32个不同行为')

        class Fitness(base.Fitness):
            weights = (1.,)

        class Individual(list):
            pass

        population = []
        for row in parents:
            member = Individual(deepcopy(row['program']))
            member.fitness = Fitness((row['score'],))
            member.action_summary = row['action_summary']
            population.append(member)
        breeding_rng = random.Random(plan['seed'] + 2)
        toolbox = base.Toolbox()
        toolbox.register('clone', deepcopy)
        toolbox.register('mate', lambda left, right: _cross(left, right, breeding_rng))
        flags = tuple(dict.fromkeys(kind for _, kind in config['reset_events']
                                   if kind in ('target', 'combat', 'shift', 'ctrl', 'alt')))

        def propose(count):
            return vary_offspring(select_parents(population, count, breeding_rng,
                training_config['tournament_size']), toolbox, rng=breeding_rng,
                config=training_config, capabilities=capabilities, reference=reference,
                legal=key, check=budget.runtime.check, observe=lambda *a, **k: None, flags=flags)

        offspring = propose(32)
        proposals = 32
        for slot in range(32):
            for attempt in range(11):
                try:
                    key(offspring[slot])
                    break
                except ValueError:
                    if attempt == 10:
                        raise ValueError('非法后代槽在10次补试后仍不合法')
                    offspring[slot] = propose(2)[0]
                    proposals += 2
                    if proposals > 352:
                        raise ValueError('对照组已达到提案上限')
        programs = dict(new_starts=generated, offspring=[list(child) for child in offspring])
        write(output / 'proposals.json', dict(programs=programs,
            attempts=dict(new_starts=new_attempts, offspring=proposals),
            generation_rng=rng.getstate(), breeding_rng=breeding_rng.getstate()))
        # Alternate arms to keep elapsed-time drift from always favoring one arm.
        coarse = {name: {} for name in programs}
        for slot in range(32):
            for name in programs:
                program = programs[name][slot]
                row = score(program)
                coarse[name][key(program)] = dict(identity=key(program), program=program,
                                                  coarse=row['dps'], coarse_batch=row['batch_key'])
        for name, unique in coarse.items():
            if len(unique) < 4:
                raise ValueError('对照组不同候选不足四条，不能判优')
            selected = sorted(unique.values(), key=lambda row: (-row['coarse'], row['identity']))[:4]
            report['groups'][name] = dict(slots=32, unique=len(unique),
                locked=[row['identity'] for row in selected], selected=selected)
        # Persist both lists BEFORE any confirmation is observed.
        confirmation_groups = dict(baseline=report['baseline'], **report['groups'])
        write(output / 'locked.json', {name: group['locked'] for name, group in confirmation_groups.items()})
        write(output / 'progress.json', report)
        for index in range(2):
            for name, group in confirmation_groups.items():
                for row in group['selected']:
                    batch = score(row['program'], 'nominal', index)
                    row.setdefault('confirmation', []).append(batch)
                    row['samples'] = sum(b['samples'] for b in row['confirmation'])
                    row['dps'] = sum(b['dps'] * b['samples'] for b in row['confirmation']) / row['samples']
                    write(output / 'progress.json', report)
        for group in confirmation_groups.values():
            values = [row['dps'] for row in group['selected']]
            group['independent'] = dict(mean=statistics.mean(values), best=max(values), worst=min(values))
        baseline_mean = report['baseline']['independent']['mean']
        for group in report['groups'].values():
            group['change_vs_original_mean_percent'] = (
                100 * (group['independent']['mean'] / baseline_mean - 1) if baseline_mean else None)
        report.update(status='completed', conclusion='仅作投入判断，不能证明300种群或最终推荐更优')
        return report

    try:
        with store.active(budget.runtime):
            return optimize(profile=profile, character=character, capabilities=capabilities,
                reference=context['native'], destination=output / 'task', runtime=budget.runtime,
                config=config, condition_key=digest(manifest), store=store,
                simulation_config=ready['simulation_config'], training=True,
                training_runner=runner, training_stage_plan=stage_plan)
    finally:
        store.close()


def worker(args, plan, output):
    budget = PilotBudget(plan, output, args.deadline)
    adapter = (runpy.run_path(str(args.native_adapter))['boundary'](ROOT, output)
               if args.native_adapter else nullcontext())
    try:
        with adapter, budget.measured_engine():
            report = compare(output, plan, budget)
    except Exception as error:
        import traceback
        (output / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        progress = output / 'progress.json'
        report = json.loads(progress.read_text(encoding='utf-8')) if progress.exists() else {}
        report.update(status='incomplete', error=f'{type(error).__name__}: {error}',
                      conclusion='尚不能判断', published=False, evidence_kind=plan['evidence_kind'])
    report.update(counts=budget.counts, elapsed_seconds=plan['limits']['seconds'] - max(0, args.deadline - time.monotonic()))
    write(output / 'report.json', report)
    return 0 if report['status'] == 'completed' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description='有成本上限的初始起点探路，不运行完整训练')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--max-wait-seconds', type=float, default=1800)
    parser.add_argument('--max-requested-iterations', type=int, default=6000)
    parser.add_argument('--seed', type=int, default=20261109)
    parser.add_argument('--native-adapter', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--deadline', type=float, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    from simulation_config import load_training_config, load_training_search_config
    config = load_training_search_config(_default_interval_ms=200)
    plan = dict(status='preflight', native_starts=0,
                limits=dict(seconds=args.max_wait_seconds, native_starts=256,
                            requested_iterations=args.max_requested_iterations),
                groups=dict(new_starts=32, offspring_slots=32),
                confirmation=dict(candidates_per_group=4, batches=2, iterations=32),
                target_count=1, syntax=config['syntax'], seed=args.seed, version=1,
                search_config=config, training_config=load_training_config(),
                evidence_kind='constructed_native_boundary' if args.native_adapter else 'native_simulation')
    plan = json.loads(json.dumps(plan))
    output = args.output.resolve()
    if (not output.is_relative_to(PILOTS.resolve()) or output == PILOTS.resolve()
            or output.is_relative_to((PILOTS / 'data').resolve())):
        parser.error('输出必须在隔离探路目录内，且不能指向共享数据目录')
    if (not 0 < args.max_wait_seconds <= 1800 or not 1 <= args.max_requested_iterations <= 6000
            or type(args.seed) is not int or not 0 <= args.seed < 1000000000):
        parser.error('预算或种子超出探路允许范围')
    if any(plan['syntax'].values()):
        parser.error('本次探路要求四项复杂语法全部关闭')
    if args.native_adapter:
        args.native_adapter = args.native_adapter.resolve()
        if (not args.native_adapter.is_relative_to(ROOT / 'tests/sim2gse')
                or not args.native_adapter.is_file()):
            parser.error('构造报告适配器必须是仓库测试文件')
    if args.check_only:
        print(json.dumps(plan, ensure_ascii=False))
        return 0
    if args.worker:
        if args.deadline is None or not (output / 'plan.json').is_file():
            parser.error('工作进程缺少冻结计划或截止时间')
        frozen = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
        if frozen != plan:
            parser.error('工作进程配置与冻结计划不符')
        return worker(args, plan, output)
    if output.exists():
        parser.error('输出目录必须全新，保留已有证据')
    output.mkdir(parents=True)
    write(output / 'plan.json', plan)
    from runtime import TaskRuntime, run_command
    deadline = ENTRY + args.max_wait_seconds
    runtime = TaskRuntime(args.max_wait_seconds, used_seconds=min(args.max_wait_seconds, time.monotonic() - ENTRY))
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        run_command([sys.executable, str(Path(__file__).resolve()), *arguments,
                     '--worker', '--deadline', str(deadline)], ROOT,
                    timeout_seconds=runtime.remaining_seconds, runtime=runtime,
                    output_dir=output / 'process')
    except Exception as error:
        progress = output / 'progress.json'
        report = json.loads(progress.read_text(encoding='utf-8')) if progress.exists() else {}
        budget_file = output / 'budget.json'
        report.update(status='incomplete', error=f'{type(error).__name__}: {error}',
            conclusion='尚不能判断', published=False, evidence_kind=plan['evidence_kind'],
            counts=json.loads(budget_file.read_text(encoding='utf-8')) if budget_file.exists() else {})
        write(output / 'report.json', report)
    report_file = output / 'report.json'
    if not report_file.exists():
        write(report_file, dict(status='incomplete', error='工作进程未返回报告', published=False,
                               evidence_kind=plan['evidence_kind'], conclusion='尚不能判断'))
    report = json.loads(report_file.read_text(encoding='utf-8'))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
