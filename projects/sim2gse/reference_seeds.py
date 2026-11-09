"""One manually requested reference refresh; normal training only reads sources."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random

from runtime import BudgetExceeded, TaskRuntime, replace_file
from search import digest

VERSION = 'reference-seeds-weighted-v1'
SIMC_FAMILY = 'simc-reference-weighted-v1'
LEGACY_SIMC = {'manual:simc-sanlayn-a1-20261012', 'manual:simc-sanlayn-a2-20261012'}


def simc_source(row):
    return row.get('source_id') in LEGACY_SIMC or row.get('family') == SIMC_FAMILY


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    replace_file(pending, path)


@contextmanager
def isolated_center(root):
    """A foreground command temporarily binds only its preparation writes."""
    import result_store
    previous = result_store.DATA_ROOT, result_store._REPORT_LOCATIONS
    root = Path(root).resolve()
    if root == Path(previous[0]).resolve() or root.is_relative_to(Path(previous[0]).resolve()):
        raise ValueError('隔离准备目录不能位于正式数据根内')
    try:
        result_store.DATA_ROOT, result_store._REPORT_LOCATIONS = root, None
        root.mkdir(parents=True, exist_ok=True)
        yield
    finally:
        result_store.DATA_ROOT, result_store._REPORT_LOCATIONS = previous


def generated_source(program, group, identity, index):
    source_id = 'simc-weighted:' + digest(dict(condition=identity, group=group, program=program))
    row = dict(candidate_id=digest(source_id), source_id=source_id, active=True, unavailable_reason='',
        label=f'SimC参考加权 {group["hero_talent"]}/{group["target_count"]}/{index}',
        class_name='deathknight', spec='unholy', source='SimC summary weighted synthesis',
        original=json.dumps(identity, ensure_ascii=False), instructions='重复单动作列表；不是原生成功轨迹',
        semantic='rewritten', changes=['按同组成功占比与合法技能等权各50%生成'],
        family=SIMC_FAMILY, core=[], program=program, allowed_groups=[group])
    return dict(row, source_revision=digest(row))


def prepare_simc(args, ready, policy, sources, document):
    import result_store
    import seed_training as seeds
    from action_summary import checked, scoped
    from program import canonicalize_search_program
    from task import _rule_hashes, _task_lease
    from weighted_seeds import generate
    from simulation_config import load_training_search_config
    from burst import load as load_burst
    definition = load_burst(252)
    root = args.workspace.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = dict(version=VERSION, policy=policy, seed=args.seed, setup=ready, sources=digest(sources),
                    configuration=document,
                    burst_definition=definition,
                    rules=_rule_hashes(relative_to=Path(__file__).resolve().parents[2]),
                    implementation={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                    for name in ('reference_seeds.py', 'weighted_seeds.py')})
    with _task_lease(root, lock_name='.reference-refresh.lock'):
        plan_path = root / 'plan.json'
        if plan_path.exists():
            state = json.loads(plan_path.read_text(encoding='utf-8'))
            if state.get('checksum') != digest({k: v for k, v in state.items() if k != 'checksum'}):
                raise ValueError('准备计划校验损坏，不能恢复')
            if state['manifest'] != manifest:
                raise ValueError('冻结来源、配置、角色或实现已变化，请创建新计划')
            if state['status'] == 'preparing':
                raise ValueError('上次进程非正常退出，无法证明在途耗时；保留计划，拒绝重置预算')
        else:
            state = dict(manifest=manifest, status='preparing', published=False, used_seconds=0.,
                         requested_iterations=0, native_attempts=0, groups=[], generated=[])
            write_json(root / 'sources.json', sources)
        runtime = TaskRuntime(300, used_seconds=state['used_seconds'])

        def checkpoint():
            state['used_seconds'] = runtime.elapsed_seconds
            state['checksum'] = digest({k: v for k, v in state.items() if k != 'checksum'})
            write_json(plan_path, state)

        def reserve(iterations):
            runtime.check()
            if state['requested_iterations'] + iterations > 1000:
                raise ValueError('整批材料准备1000次请求迭代额度耗尽')
            state['requested_iterations'] += iterations
            state['native_attempts'] += 1
            checkpoint()
        runtime.reserve_native = reserve
        state['status'] = 'preparing'
        checkpoint()
        try:
            with isolated_center(root / 'data'):
                result_store.write('burst_definitions', 'current_252', [definition])
                for index, group_info in enumerate(ready['groups']):
                    group = dict(group_info['configuration_key'])
                    targets = 1 if group['target_type'] == 'single_target' else 5
                    group['target_count'] = targets
                    if index < len(state['groups']):
                        progress = state['groups'][index]
                    else:
                        progress = dict(group=group, status='preparing')
                        state['groups'].append(progress)
                    if progress['status'] == 'prepared':
                        continue
                    template = Path(group_info['template'])
                    inputs = seeds._training_inputs(template, targets, use_burst=True,
                        _frozen_config=load_training_search_config(_document=document, _default_interval_ms=200))
                    original = seeds.ensure_prepared(template, targets, root / 'workspace',
                        sources=sources, use_burst=True, runtime=runtime, inputs=inputs)
                    if not original['queue'] or not original['context']:
                        raise ValueError('当前组没有有效原材料，不能初始化')
                    context = original['context']
                    actual = dict(context['configuration_key'], target_count=targets)
                    if actual != group:
                        raise ValueError('模拟实际英雄或目标与计划不符')
                    capabilities = context['capabilities']
                    reference = scoped(checked(context['native'].get('action_summary'),
                                                context['native']['samples']), capabilities)
                    existing = {entry['behavior_id'] for entry in original['entries']
                                if entry['status'] == 'ready' and simc_source(entry)}
                    gap = max(0, policy['reference_seed_target'] - len(existing))
                    provenance = dict(group=group, template=original['template_sha'], engines=original['engines'],
                        reference=digest(reference), seed=args.seed + 1 + index, strategy=VERSION,
                        syntax=original['config']['syntax'], simulation=original['simulation_config'],
                        burst=context['burst'])
                    if progress.get('provenance', provenance) != provenance:
                        raise ValueError('恢复时同组参考或生成条件发生变化')
                    progress.update(provenance=provenance, original_simc=len(existing), gap=gap)
                    if gap:
                        def save_generation(value):
                            progress['generation'] = value
                            checkpoint()
                        generated = generate(capabilities, reference, random.Random(args.seed + 1 + index),
                            count=gap, excluded=existing,
                            legal=lambda p: canonicalize_search_program(p, capabilities)['identity'],
                            check=runtime.check, progress=progress.get('generation'), checkpoint=save_generation)['programs']
                    else:
                        generated = []
                    new = [generated_source(p, group, provenance, number + 1) for number, p in enumerate(generated)]
                    all_new = [row for row in state['generated'] if row['allowed_groups'] != [group]] + new
                    prepared = seeds.ensure_prepared(template, targets, root / 'workspace',
                        sources=[*sources, *all_new], use_burst=True, runtime=runtime, inputs=inputs)
                    count = len({r['behavior_id'] for r in prepared['entries']
                                 if r['status'] == 'ready' and simc_source(r)})
                    if count < policy['reference_seed_target']:
                        raise ValueError(f'适配编译后模拟来源不足目标，实际{count}')
                    state['generated'] = all_new
                    progress.update(status='prepared', simc_behaviors=count, unique_inputs=len(prepared['queue']),
                                    preparation_key=prepared['config_key'])
                    checkpoint()
                state['status'] = 'simc_prepared'
                checkpoint()
        except BaseException as error:
            message = '整批材料准备300秒累计预算耗尽' if isinstance(error, BudgetExceeded) else str(error)
            state.update(status='paused', error=message)
            checkpoint()
            if isinstance(error, BudgetExceeded):
                raise ValueError(message) from error
            raise
        return state


def run(args):
    import seed_training as seeds
    from simulation_config import load_reference_seed_config, load_training_config, _load_document
    document = _load_document()
    policy = load_reference_seed_config(document=document)
    ready = seeds.check_training(use_burst=True, training_config=load_training_config(_document=document))
    if args.check_only:
        return dict(status='preflight', target=policy['reference_seed_target'],
                    mode=policy['reference_seed_mode'], groups=ready['groups'],
                    native_starts=0, published=False)
    if policy['reference_seed_mode'] != 'weighted-v1':
        raise ValueError('请在原配置training区启用reference_seed_mode=weighted-v1')
    sources = seeds.registry_rows()
    if args.apply_plan or not args.simc_only:
        raise ValueError('联合插件发布阶段尚未完成')
    return prepare_simc(args, ready, policy, sources, document)
