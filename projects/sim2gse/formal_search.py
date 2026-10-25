"""真实角色正式适配：共享训练遗传链，只复测正常场景并交付一个冠军。"""
from copy import deepcopy
import math
import random

from runtime import TaskRuntime
from search import digest

ALGORITHM = 'formal-ga-easimple-v1'
STOP_POLICY = dict(version=1, kind='natural_stagnation')
VERSION = 1
COARSE_FAILURE_POLICY = dict(version=1, initial='exclude_invalid_score', offspring='retain_verified_slot')


def runtime_for(config, *, cancel_event=None):
    # Infinite is a runtime limit only. Durable state carries the explicit policy, never Infinity.
    return TaskRuntime(float('inf'), cancel_event=cancel_event,
                       diagnostic_logging=config['diagnostic_logging'])


def freeze_starts(starts, capabilities, runtime):
    from codec import load_targeting, prepare_block, prepare_castsequence
    from program import canonicalize_search_program, _search_expanded_nodes
    masks = load_targeting(runtime=runtime)['target_masks']
    programs, decisions, seen = [], [], set()
    for index, program in enumerate(starts):
        decision = dict(index=index, status='rejected')
        try:
            canonical = canonicalize_search_program(program, capabilities)
            for node in _search_expanded_nodes(canonical['program']):
                if node['kind'] == 'Action':
                    commands = node['commands']
                    if len(commands) == 1 and commands[0].get('kind') == 'castsequence':
                        prepare_castsequence(commands[0])
                    else:
                        prepare_block(commands, masks)
            identity = canonical['identity']
            decision['behavior_identity'] = identity
            if identity in seen:
                decision.update(status='duplicate', reason='与已冻结起点行为相同')
            else:
                programs.append(program)
                seen.add(identity)
                decision['status'] = 'accepted'
        except (TypeError, ValueError, KeyError) as error:
            decision['reason'] = str(error)
        decisions.append(decision)
    if not programs:
        raise ValueError('当前条件没有合法正式搜索起点')
    return programs, decisions


def contract_for(config):
    from population_training import _stage_plan
    from simulation_config import TRAINING_DEFAULTS
    ga_config = {key: value for key, value in TRAINING_DEFAULTS.items() if key != 'max_trainings'}
    ga_config['max_processes'] = config['max_processes']
    return dict(version=VERSION, algorithm=ALGORITHM, stop_policy=STOP_POLICY, config=ga_config,
                coarse_failure_policy=COARSE_FAILURE_POLICY,
                stage_plan=_stage_plan(ga_config, config['random_seed'], scenarios=('nominal',)))


def run(*, profile, character, capabilities, reference, destination, runtime,
        config, condition_key, store, simulation_config):
    from population_training import ALGORITHM as GA_ALGORITHM, _evolution, _retest_scores
    from search import optimize
    state = store.state
    frozen = contract_for(config)
    ga_config, plan = frozen['config'], frozen['stage_plan']
    if state.get('formal_search') not in (None, frozen):
        raise ValueError('正式遗传搜索恢复契约或评分计划变化，不能混接')
    state['formal_search'] = frozen
    state.setdefault('ga', dict(algorithm=GA_ALGORITHM, phase='initial', generation=0,
        stagnant=0, population=[], pending=None, rng=random.Random(config['random_seed']).getstate(), finals={}))
    if state['ga']['algorithm'] != GA_ALGORITHM:
        raise ValueError('正式遗传搜索算法身份不符')
    store.checkpoint()
    timeline = getattr(runtime, 'search_timeline', None)
    if timeline is not None:
        timeline.context['algorithm'].update(formal=ALGORITHM, stop_policy=STOP_POLICY, ga_config=ga_config)
        timeline.start()
    ga = optimize(profile=profile, character=character, capabilities=capabilities,
        reference=reference, destination=destination, runtime=runtime, config=config,
        condition_key=condition_key, store=store, simulation_config=simulation_config,
        training=True, training_stage_plan=plan,
        training_runner=_evolution(store, capabilities, runtime, ga_config, scenarios=('nominal',)))
    if timeline is not None:
        timeline.stop('stagnation')
    qualified = _retest_scores(ga, store, condition=condition_key, stage_plan=plan,
        config=ga_config, character=character, simulation_config=simulation_config, scenarios=('nominal',))
    if len(qualified) != len(ga['finalists']) or not qualified:
        raise ValueError('正式入围名单没有全部完成正常复测')
    archive = {row['key']: row for row in state['archive']}
    finalists = []
    for row in qualified:
        identity = row['identity']
        batches = [deepcopy(store.batch(item['batch_key'])) for item in row['scenarios']['nominal']['batches']]
        finalists.append(dict(key=identity, program=archive[identity]['program'], score=row['nominal'],
                              samples=row['scenarios']['nominal']['samples'], batches=batches))
    winner = min(finalists, key=lambda row: (-row['score'], row['key']))
    selected = deepcopy(archive[winner['key']])
    selected.update(score=winner['score'], batches=winner['batches'])
    selected['candidate']['simulation'] = 'passed_native_model'
    if timeline is not None:
        timeline.score(selected, 'global', 'nominal_retest')
    state.update(formal_finalists=finalists, formal_winner=selected,
                 locked_candidate_key=winner['key'], selected_candidate_key=winner['key'])
    summary = dict(dps=winner['score'], samples=winner['samples'], reference_dps=reference['dps'],
        reference_ratio=winner['score'] / reference['dps'] if reference['dps'] else None,
        retest=dict(scenario='nominal', batches=ga_config['retest_batches'],
                    requested_iterations=ga_config['retest_iterations']))
    state['search_result'] = summary
    runtime.check()
    store.checkpoint()
    result = dict(status='completed', phase='done', candidate=selected['candidate'],
        locked_candidate_key=winner['key'], selected_candidate_key=winner['key'],
        native_reference=reference, search_result=summary, independent_validation_complete=True,
        improvement='search_result', stop_policy=STOP_POLICY,
        search=dict(dataset='search', algorithm=ALGORITHM, starts=state['starts'], records=state['archive'],
            effective_population_size=ga['effective_population_size'],
            coarse_rejections=ga.get('coarse_rejections', {}), last_fallbacks=ga.get('last_fallbacks', {}),
            rounds=ga['generation'], complete_generations=ga['generation'],
            candidate_count=len(state['evaluated_keys']), unique_candidates=len(state['seen']),
            partial_round=False, stop_reason='stagnation', errors=state.get('errors', []),
            formal_search=frozen, retest=summary['retest']),
        validation=dict(dataset='validation', records=[]),
        final=dict(dataset='final', status='completed', scenarios=dict(nominal=dict(finalists=finalists))),
        elapsed_seconds=runtime.elapsed_seconds, completed_batches=state['completed_batches'])
    if config['diagnostic_logging']:
        result['search'].update({key: state.get(key, 0) for key in
            ('canonicalized_duplicates', 'batch_requests', 'batch_cache_hits', 'native_batch_starts')})
    if config['diagnostics'] != 'off':
        result['search']['diagnostics'] = store.diagnostic_summary
    if state.get('search_observability'):
        from search import _export_search_observability
        result['search']['observability'] = _export_search_observability(state['search_observability'])
    return result


def validate_evidence(record, state, character, *, verify_reports):
    """新冠军的正常复测契约；旧CI验证器完全不放宽。"""
    from program import canonicalize_search_program
    from search import _validate_saved_batch, _score, input_times, STATS_VERSION
    from sequence import compiled_identity
    from result_store import InvalidRecordError, read_many, report_locations
    evaluation = record.get('evaluation') or {}
    if (not isinstance(evaluation, dict) or not isinstance(evaluation.get('search'), dict)
            or type(evaluation['search'].get('version')) is not int
            or not isinstance(evaluation['search'].get('coarse_failure_policy'), dict)
            or type((evaluation['search'].get('coarse_failure_policy') or {}).get('version')) is not int):
        raise InvalidRecordError('正式遗传冠军评价契约版本格式不符')
    expected = contract_for(state['config'])
    config = expected['config']
    if (evaluation.get('search') != expected or evaluation.get('engines') != state['engines']
            or type(evaluation.get('complete_generations')) is not int
            or evaluation['complete_generations'] < config['stagnation_generations']
            or evaluation.get('stagnant', 0) < config['stagnation_generations']
            or record.get('promotion_evidence') != []):
        raise InvalidRecordError('正式遗传冠军的算法、停止或引擎凭据不符')
    finalists = evaluation.get('finalists')
    if not isinstance(finalists, list) or not 1 <= len(finalists) <= config['top_k']:
        raise InvalidRecordError('正式遗传冠军入围名单不完整')
    receipts, identities = {}, set()
    for finalist in finalists:
        canonical = canonicalize_search_program(finalist['program'], state['capabilities'])
        key = canonical['identity']
        if key != finalist.get('key') or key in identities:
            raise InvalidRecordError('正式遗传入围候选身份重复或不符')
        identities.add(key)
        batches = finalist.get('batches') or []
        if len(batches) != config['retest_batches']:
            raise InvalidRecordError('正式遗传候选没有完整正常复测')
        for index, cached in enumerate(batches):
            seed = expected['stage_plan']['nominal']['seeds'][index]
            times = input_times('nominal', seed + 500000, state['config']['input_interval_ms'])
            request = dict(condition=record['source_condition_key'], program=canonical['form'],
                behavior_identity=key, purpose='nominal', seed=seed, input_seed=seed + 500000,
                iterations=config['retest_iterations'], times=times, stats=STATS_VERSION,
                trace=False, reset_events=[list(item) for item in state['config']['reset_events']], allow_zero=True)
            if state.get('burst'):
                from burst import combined_inputs
                context = state['burst']
                request['times'], sources = combined_inputs(times, context, state['config']['input_interval_ms'])
                request['burst'] = dict(definition_id=context['definition_id'],
                    program=compiled_identity(context['candidate']), plan=context['plan'],
                    interval_ms=state['config']['input_interval_ms'], sources=sources)
            batch_key = digest(request)
            if (cached.get('status') != 'success' or cached.get('request') != request
                    or cached.get('data_key') != batch_key or batch_key in receipts
                    or type(cached.get('samples')) is not int or cached['samples'] < 1
                    or type(cached.get('dps')) not in (int, float) or not math.isfinite(cached['dps'])
                    or cached['dps'] < 0
                    or cached.get('requested_iterations') != config['retest_iterations']):
                raise InvalidRecordError('正式遗传复测请求或有效样本不符')
            receipts[batch_key] = (cached, index)
        if (_score(batches) != finalist['score']
                or sum(row['samples'] for row in batches) != finalist['samples']):
            raise InvalidRecordError('正式遗传复测成绩不符')
    winner = min(finalists, key=lambda row: (-row['score'], row['key']))
    if (winner['key'] != record['behavior_identity'] or winner['score'] != record['score']
            or winner['samples'] != record['samples'] or set(receipts) != set(record['batch_keys'])
            or evaluation.get('finalist_keys') != [row['key'] for row in finalists]):
        raise InvalidRecordError('正式遗传冠军不是完整入围名单的正常复测赢家')
    if not verify_reports:
        return
    locations = report_locations(list(receipts))
    groups = {}
    for key, (cached, index) in receipts.items():
        group = cached.get('storage_group_key') or locations.get(key) or key
        groups.setdefault(group, {})[key] = (cached, index)
    for group, wanted in groups.items():
        found = set()
        for saved in read_many('batches', [group]):
            key = saved.get('batch_key')
            if key not in wanted:
                continue
            if key in found:
                raise InvalidRecordError('正式遗传复测报告重复')
            found.add(key)
            cached, index = wanted[key]
            _validate_saved_batch(saved, key, cached, character, index, 'nominal', state['simulation_config'])
        if found != wanted.keys():
            raise InvalidRecordError('正式遗传复测原报告缺失')
