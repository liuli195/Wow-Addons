"""共享 GA 的粗评容错状态只用内存；公开页面主路复用现有方差故障代表。"""
from copy import deepcopy
import random
import threading
from types import SimpleNamespace

import pytest


POLICY = dict(version=1, initial='exclude_invalid_score', offspring='retain_verified_slot')
CAPABILITIES = dict(precombat_actions=[], actions=[dict(kind='spell', spell_id=index,
    base_spell_id=index, simc_action=name, name=name, gcd_ms=1500)
    for index, name in enumerate(('outbreak', 'death_coil', 'scourge_strike'), 1)])
STARTS = [[['outbreak']], [['death_coil']]]
BAD = [['scourge_strike']]


def memory_case(monkeypatch, *, fault='score', formal=True, phase='breed', stop=False, bad_stage='search'):
    import codec
    import population_training
    from engine import CandidateError, CandidateScoreError, NativeEvaluationError
    from program import canonicalize_search_program
    from result_store import DataReadError
    from runtime import TaskRuntime, TaskCancelled
    from search import digest
    from simulation_config import TRAINING_DEFAULTS
    key = lambda program: canonicalize_search_program(program, CAPABILITIES)['identity']
    error = {'score': CandidateScoreError('explicit invalid variance'),
        'native': NativeEvaluationError('native exchange failure'), 'timeout': CandidateError('process timeout'),
        'mixed': CandidateScoreError('mixed failure'), 'unknown': CandidateScoreError('unknown history'),
        'storage': DataReadError('storage unavailable'), 'identity': ValueError('identity mismatch'),
        'cancel': TaskCancelled('cancelled')}[fault]
    config = dict(TRAINING_DEFAULTS, top_k=2, max_processes=1,
        crossover_probability=0., mutation_probability=1., tournament_size=1)
    state = dict(config=dict(reset_events=()), condition='memory-condition', starts=deepcopy(STARTS),
        archive=[], errors=[], training_failures={}, training_failure_causes={},
        ga=dict(algorithm=population_training.ALGORITHM, phase=phase, generation=0, stagnant=0,
            population=[], pending=None, rng=random.Random(20260912).getstate(), finals={}, baseline=[]))
    if formal:
        state['formal_search'] = dict(coarse_failure_policy=POLICY)
    store = SimpleNamespace(state=state, lock=threading.RLock(), report_buffer=[],
        diagnostic_logging=False, receipts={}, calls=[], saved=None, stop=stop)
    def checkpoint():
        store.saved = deepcopy((store.state, store.receipts))
        if store.stop and store.state['ga'].get('pending') and store.state['ga'].get('coarse_rejections'):
            store.stop = False
            raise TaskCancelled('checkpoint interruption')
    store.checkpoint = checkpoint
    def evaluate(program, stage, index):
        identity = key(program)
        bad = stage == bad_stage and (program == BAD or phase == 'initial' or bad_stage == 'nominal')
        if bad:
            if fault in ('storage', 'identity', 'cancel'):
                raise error
            attempt = digest(dict(candidate=identity, stage='search', index=0))
            if attempt not in store.state['training_failures']:
                store.calls.extend([(identity, stage)] * 2)  # The existing evaluator owns its two attempts.
                store.state['training_failures'][attempt] = 2
                kinds = (['candidate_score'] * 2 if fault == 'score' else
                         ['native', 'candidate_score'] if fault == 'mixed' else
                         ['candidate' if fault == 'timeout' else fault] * 2)
                if fault != 'unknown':
                    store.state['training_failure_causes'][attempt] = [dict(kind=kind, reason=str(error)) for kind in kinds]
            raise error
        request = dict(condition='memory-condition', behavior_identity=identity, purpose=stage, index=index)
        batch_key = digest(request)
        if batch_key not in store.receipts:
            store.calls.append((identity, stage))
            score = 100. if program == STARTS[0] else 90. if program == STARTS[1] else 80.
            receipt = dict(status='success', request=request, data_key=batch_key, dps=score, samples=31)
            store.receipts[batch_key] = receipt
            if stage == 'search':
                store.state['archive'].append(dict(key=identity, program=deepcopy(program), score=score, batches=[receipt]))
        receipt = store.receipts[batch_key]
        return dict(candidate_key=identity, batch_key=batch_key, dps=receipt['dps'], samples=31)
    if phase == 'breed':
        initial = [evaluate(program, 'search', 0) for program in STARTS]
        state['ga'].update(population=[dict(program=deepcopy(program), key=row['candidate_key'], score=row['dps'])
            for program, row in zip(STARTS, initial)], baseline=[100., 90.], effective_population_size=2)
    mutation_count = [0]
    def mutate(program, *args, **kwargs):
        mutation_count[0] += 1
        return deepcopy(BAD if mutation_count[0] % 2 else program)
    class MutationRandom(random.Random):
        _randbelow = random.Random._randbelow
        def random(self):
            return 0.
    monkeypatch.setattr(codec, 'load_targeting', lambda **kwargs: dict(target_masks={}))
    monkeypatch.setattr(population_training, 'random', SimpleNamespace(Random=MutationRandom))
    monkeypatch.setattr(population_training, 'mutate', mutate)
    def run():
        execute = population_training._evolution(store, CAPABILITIES, TaskRuntime(float('inf')), config, scenarios=('nominal',))
        return execute(evaluate=evaluate, feedback=lambda program: {})
    return store, run, error, key


def test_formal_invalid_offspring_retains_verified_slot_across_checkpoint_resume(monkeypatch):
    from runtime import TaskCancelled
    store, run, _, key = memory_case(monkeypatch, stop=True)
    previous = deepcopy(store.state['ga']['population'][0])
    with pytest.raises(TaskCancelled, match='checkpoint interruption'):
        run()
    store.state, store.receipts = deepcopy(store.saved)
    result = run()
    assert result['phase'] == 'qualified' and result['generation'] == result['stagnant'] == 2
    assert result['effective_population_size'] == len(result['population']) == 2
    assert result['population'][0] == previous
    assert store.calls.count((key(BAD), 'search')) == 2, '恢复不得再给已耗尽的原请求尝试'
    assert key(BAD) not in {row['key'] for row in store.state['archive']}
    assert result['last_fallbacks']['0']['retained_key'] == previous['key']
    with monkeypatch.context() as scoped:
        control, complete, _, _ = memory_case(scoped)
        uninterrupted = complete()
        assert result['rng'] == uninterrupted['rng']
        assert result['population'] == uninterrupted['population']
        assert store.calls == control.calls


def test_formal_coarse_tolerance_fails_closed_outside_proven_new_score_data(monkeypatch):
    for fault in ('native', 'timeout', 'mixed', 'unknown', 'storage', 'identity', 'cancel'):
        with monkeypatch.context() as scoped:
            store, run, error, _ = memory_case(scoped, fault=fault)
            with pytest.raises(type(error), match=str(error)):
                run()
            assert store.state['ga']['generation'] == 0
    for options in (dict(formal=False), dict(bad_stage='nominal')):
        with monkeypatch.context() as scoped:
            _, run, error, _ = memory_case(scoped, **options)
            with pytest.raises(type(error), match=str(error)):
                run()
    with monkeypatch.context() as scoped:
        from search import digest
        store, run, error, key = memory_case(scoped)
        request = dict(condition='memory-condition', behavior_identity=key(BAD), purpose='search', index=0)
        receipt = dict(request=request, data_key=digest(request), dps=80., samples=31)
        store.state['archive'].append(dict(key=key(BAD), program=BAD, score=80., batches=[receipt]))
        with pytest.raises(type(error), match=str(error)):
            run()  # Previously successful archive verification may never quarantine a missing receipt.
        assert not store.state['ga'].get('coarse_rejections')
    with monkeypatch.context() as scoped:
        store, run, _, _ = memory_case(scoped, phase='initial')
        with pytest.raises(ValueError, match='没有可靠'):
            run()
        assert not store.state['ga']['population'] and not store.state['archive']
