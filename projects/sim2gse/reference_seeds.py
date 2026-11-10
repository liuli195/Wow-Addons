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
ADOPTION_PATH = Path(__file__).resolve().parents[2] / 'myspec/changes/sim2gse-gearinsight-reference-refresh/legacy-source-adoption.json'


def source_digest(rows):
    return digest(sorted([dict(r, allowed_groups=r.get('allowed_groups')) for r in rows], key=lambda r: r['source_id']))


def simc_source(row):
    return row.get('source_id') in LEGACY_SIMC or row.get('family') == SIMC_FAMILY


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    replace_file(pending, path)


def load_plan(root):
    state = json.loads((Path(root) / 'plan.json').read_text(encoding='utf-8'))
    if state.get('checksum') != digest({k: v for k, v in state.items() if k != 'checksum'}):
        raise ValueError('准备计划校验损坏，不能恢复')
    return state


def preparation_budget(state, root):
    runtime = TaskRuntime(300, used_seconds=state['used_seconds'])
    original_check = runtime.check
    last_space_check = -1.
    def check():
        nonlocal last_space_check
        original_check()
        if runtime.elapsed_seconds - last_space_check >= 1:
            last_space_check = runtime.elapsed_seconds
            if sum(path.stat().st_size for path in Path(root).rglob('*') if path.is_file()) >= 1024 ** 3:
                raise ValueError('本次隔离准备数据达到1GiB停止线')
    runtime.check = check
    def checkpoint():
        state['used_seconds'] = runtime.elapsed_seconds
        state['checksum'] = digest({k: v for k, v in state.items() if k != 'checksum'})
        write_json(Path(root) / 'plan.json', state)
    def reserve(iterations):
        runtime.check()
        if state['requested_iterations'] + iterations > 1000:
            raise ValueError('整批材料准备1000次请求迭代额度耗尽')
        state['requested_iterations'] += iterations
        state['native_attempts'] += 1
        checkpoint()
    runtime.reserve_native = reserve
    return runtime, checkpoint


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


def frozen_inputs(group_info, targets, setup, document):
    import seed_training as seeds
    from simulation_config import load_training_search_config
    template = Path(group_info['template'])
    expected = next(row for row in setup['templates'] if Path(row['template']) == template)
    inputs = seeds._training_inputs(template, targets, use_burst=True,
        max_processes=setup['training_config']['max_processes'],
        verified_engines=setup['engines'], burst_identity=expected.get('burst_identity'),
        _frozen_config=load_training_search_config(_document=document, _default_interval_ms=200))
    if inputs['template_sha'] != expected['template_sha256']:
        raise ValueError('角色模板在冻结后已变化')
    return inputs


def joint_sources(sources, generated, plugin_sources, adoption):
    """Only explicit owned batches may be retired; unrelated rows are retained."""
    from gearinsight_reference import FAMILY, PREFIX
    by_id = {row['source_id']: row for row in sources}
    managed = [r for r in sources if r.get('family') == FAMILY and r['source_id'].startswith(PREFIX)]
    if managed:
        retiring = {r['source_id'] for r in managed if r.get('active', True)}
    else:
        retiring = set()
        for expected in adoption['legacy_sources']:
            row = by_id.get(expected['source_id'])
            if (row is None or any(row.get(k) != expected[k] for k in ('candidate_id', 'source_revision'))
                    or hashlib.sha256(row['original'].encode('utf-8')).hexdigest() != expected['original_sha256']
                    or digest(row['program']) != expected['program_sha256']):
                raise ValueError('旧插件来源与精确接管清单不符')
            retiring.add(expected['source_id'])
    if not set(adoption['protected_manual_source_ids']) <= set(by_id):
        raise ValueError('受保护人工插件来源缺失')
    incoming = {r['source_id']: r for r in [*generated, *plugin_sources]}
    if len(incoming) != len(generated) + len(plugin_sources):
        raise ValueError('拟发布来源身份重复')
    for row in plugin_sources:
        old = by_id.get(row['source_id'])
        if old and old.get('family') != FAMILY:
            raise ValueError('新版插件来源与非受管材料身份冲突')
    for row in generated:
        old = by_id.get(row['source_id'])
        if old and old.get('family') != SIMC_FAMILY:
            raise ValueError('模拟来源与非受管材料身份冲突')
    result = []
    for row in sources:
        if row['source_id'] in incoming:
            continue
        if row['source_id'] in retiring:
            row = dict(row, active=False, unavailable_reason='已由验证成功的新参考库接替')
            row.pop('source_revision', None)
            row['source_revision'] = digest(row)
        result.append(row)
    return [*result, *incoming.values()]


def plugin_unchanged(plugin):
    for key, sha in (('source', 'source_sha256'), ('toc', 'toc_sha256')):
        path = Path(plugin[key])
        if path.stat().st_size > 2 * 1024 * 1024 or hashlib.sha256(path.read_bytes()).hexdigest() != plugin[sha]:
            raise ValueError('插件资料在计划验证后已变化，请创建新计划')


def prepare_plugin(args, state, sources, document):
    import result_store
    import seed_training as seeds
    from gearinsight_reference import read, sources as clean_sources
    from task import _task_lease
    root = args.workspace.resolve()
    with _task_lease(root, lock_name='.reference-refresh.lock'):
        latest = load_plan(root)
        if latest['manifest'] != state['manifest']:
            raise ValueError('阶段交接时冻结计划已变化')
        state = latest
        if state['status'] in ('prepared', 'published'):
            plugin_unchanged(state['plugin'])
            return state
        if state['status'] == 'preparing':
            raise ValueError('上次插件准备非正常退出，无法证明在途耗时')
        if args.plugin_dir is None:
            raise ValueError('请明确指定插件资料目录')
        runtime, checkpoint = preparation_budget(state, root)
        state['status'] = 'preparing'
        checkpoint()
        try:
            runtime.check()
            plugin = read(args.plugin_dir, root / 'plugin', runtime=runtime)
            if state.get('plugin') and state['plugin'] != plugin:
                raise ValueError('恢复时插件资料已变化，请创建新计划')
            state['plugin'] = plugin
            adoption = json.loads(ADOPTION_PATH.read_text(encoding='utf-8'))
            if state.get('adoption', adoption) != adoption:
                raise ValueError('精确接管清单已变化，请创建新计划')
            state['adoption'] = adoption
            groups = [row['group'] for row in state['groups']]
            candidates = clean_sources(plugin, state['manifest']['burst_definition'], groups)
            final = joint_sources(sources, state['generated'], candidates, adoption)
            published_ids = {row['source_id'] for row in candidates}
            final_groups = []
            with isolated_center(root / 'data'):
                result_store.write('burst_definitions', 'current_252', [state['manifest']['burst_definition']])
                for group_info in state['manifest']['setup']['groups']:
                    runtime.check()
                    group = dict(group_info['configuration_key'])
                    targets = 1 if group['target_type'] == 'single_target' else 5
                    group['target_count'] = targets
                    template = Path(group_info['template'])
                    inputs = frozen_inputs(group_info, targets, state['manifest']['setup'], document)
                    prepared = seeds.ensure_prepared(template, targets, root / 'workspace', sources=final,
                                                    use_burst=True, runtime=runtime, inputs=inputs)
                    valid = [r for r in prepared['entries'] if r['status'] == 'ready']
                    new_ids = {r['source_id'] for r in valid if r['source_id'] in published_ids}
                    simc = len({r['behavior_id'] for r in valid if simc_source(r)})
                    if not new_ids or simc < state['manifest']['policy']['reference_seed_target']:
                        raise ValueError('四组材料未齐，不能接替旧来源')
                    final_groups.append(dict(group=group, simc_behaviors=simc,
                        plugin_sources=len(new_ids), plugin_behaviors=len({r['behavior_id'] for r in valid if r['source_id'] in new_ids}),
                        unique_inputs=len(prepared['queue']), preparation_key=prepared['config_key'],
                        rejected=[dict(source_id=r['source_id'], reason=r['reason']) for r in prepared['entries']
                                  if r['source_id'] in published_ids and r['status'] != 'ready']))
                    checkpoint()
            plugin_unchanged(plugin)
            runtime.check()
            state.update(status='prepared', final_sources=final, final_digest=source_digest(final),
                         final_groups=final_groups)
            checkpoint()
            return state
        except BaseException as error:
            message = '整批材料准备300秒累计预算耗尽' if isinstance(error, BudgetExceeded) else str(error)
            state.update(status='paused', error=message)
            checkpoint()
            if isinstance(error, BudgetExceeded):
                raise ValueError(message) from error
            raise


def apply_plan(args, ready, policy, document):
    import result_store
    import seed_training as seeds
    from burst import load as load_burst
    from task import _rule_hashes, _task_lease
    root = args.workspace.resolve()
    with _task_lease(root, lock_name='.reference-refresh.lock'):
        state = load_plan(root)
        if state['status'] not in ('prepared', 'published') or not state.get('final_groups'):
            raise ValueError('联合计划未验证完成，不能发布')
        expected_groups = {digest(dict(r['configuration_key'],
            target_count=1 if r['configuration_key']['target_type'] == 'single_target' else 5)) for r in ready['groups']}
        if (len(expected_groups) != 4 or len(state['final_groups']) != 4
                or {digest(r['group']) for r in state['final_groups']} != expected_groups
                or any(r['simc_behaviors'] < policy['reference_seed_target'] or r['plugin_sources'] < 1
                       for r in state['final_groups'])):
            raise ValueError('四组联合验真凭据不完整')
        if state['final_digest'] != source_digest(state['final_sources']):
            raise ValueError('联合计划最终来源摘要不符')
        with seeds.writer_lock():
            current = seeds.registry_rows()
            actual = source_digest(current)
            if actual == state['final_digest']:
                return dict(status='published', published=True, already_published=True,
                            final_digest=actual, groups=state['final_groups'])
            if actual != state['manifest']['sources']:
                raise ValueError('正式来源在计划后已变化，拒绝覆盖')
            expected = dict(state['manifest'], configuration=document, setup=ready, policy=policy,
                burst_definition=load_burst(252), rules=_rule_hashes(relative_to=Path(__file__).resolve().parents[2]),
                implementation={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    for name in ('reference_seeds.py', 'weighted_seeds.py', 'gearinsight_reference.lua')})
            if expected != state['manifest']:
                raise ValueError('发布时配置、角色或实现已变化，请创建新计划')
            if state['adoption'] != json.loads(ADOPTION_PATH.read_text(encoding='utf-8')):
                raise ValueError('精确接管清单已变化')
            plugin_unchanged(state['plugin'])
            for row in state['final_sources']:
                seeds.source_groups(row)
            result_store.write('seed_candidates', 'registry', state['final_sources'], schema=seeds.CANDIDATE_SCHEMA)
            if source_digest(seeds.registry_rows()) != state['final_digest']:
                raise ValueError('来源发布后读取身份不符，保留计划等待核实')
            state.update(status='published', published=True)
            state['checksum'] = digest({k: v for k, v in state.items() if k != 'checksum'})
            write_json(root / 'plan.json', state)
        return dict(status='published', published=True, already_published=False,
                    final_digest=state['final_digest'], groups=state['final_groups'])


def prepare_simc(args, ready, policy, sources, document):
    import result_store
    import seed_training as seeds
    from action_summary import checked, scoped
    from program import canonicalize_search_program
    from task import _rule_hashes, _task_lease
    from weighted_seeds import generate
    from burst import load as load_burst
    definition = load_burst(252)
    root = args.workspace.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = dict(version=VERSION, policy=policy, seed=args.seed, setup=ready, sources=source_digest(sources),
                    configuration=document,
                    burst_definition=definition,
                    rules=_rule_hashes(relative_to=Path(__file__).resolve().parents[2]),
                    implementation={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                    for name in ('reference_seeds.py', 'weighted_seeds.py', 'gearinsight_reference.lua')})
    with _task_lease(root, lock_name='.reference-refresh.lock'):
        plan_path = root / 'plan.json'
        if plan_path.exists():
            state = load_plan(root)
            if state['manifest'] != manifest:
                raise ValueError('冻结来源、配置、角色或实现已变化，请创建新计划')
            if state['status'] == 'preparing':
                raise ValueError('上次进程非正常退出，无法证明在途耗时；保留计划，拒绝重置预算')
            if state['status'] in ('prepared', 'published'):
                return state
        else:
            state = dict(manifest=manifest, status='preparing', published=False, used_seconds=0.,
                         requested_iterations=0, native_attempts=0, groups=[], generated=[])
            write_json(root / 'sources.json', sources)
        runtime, checkpoint = preparation_budget(state, root)
        state['status'] = 'preparing'
        checkpoint()
        try:
            runtime.check()
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
                    inputs = frozen_inputs(group_info, targets, state['manifest']['setup'], document)
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
    import result_store
    import seed_training as seeds
    from simulation_config import load_reference_seed_config, load_training_config, _load_document
    document = _load_document()
    policy = load_reference_seed_config(document=document)
    ready = seeds.check_training(use_burst=True, training_config=load_training_config(_document=document))
    if args.plugin_dir is not None and not args.simc_only:
        source_root, work = args.plugin_dir.resolve(), args.workspace.resolve()
        if source_root == work or source_root.is_relative_to(work) or work.is_relative_to(source_root):
            raise ValueError('插件安装目录和准备目录不能相互包含，安装目录必须只读')
    if args.workspace.resolve().is_relative_to(Path(result_store.DATA_ROOT).resolve()):
        raise ValueError('准备目录不能位于正式数据根内')
    if args.check_only:
        result = dict(status='preflight', target=policy['reference_seed_target'],
                    mode=policy['reference_seed_mode'], groups=ready['groups'],
                    native_starts=0, published=False)
        if not args.simc_only:
            if args.plugin_dir is None:
                raise ValueError('请明确指定插件资料目录')
            from gearinsight_reference import read
            result['plugin'] = read(args.plugin_dir, args.workspace / 'plugin')
        return result
    if policy['reference_seed_mode'] != 'weighted-v1':
        raise ValueError('请在原配置training区启用reference_seed_mode=weighted-v1')
    if args.apply_plan:
        return apply_plan(args, ready, policy, document)
    sources = seeds.registry_rows()
    state = prepare_simc(args, ready, policy, sources, document)
    return state if args.simc_only else prepare_plugin(args, state, sources, document)
