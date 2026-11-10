"""GA规则使用内存输入；公开持久化、共享并发和取消链显式标记real。"""
import json
from pathlib import Path
import pytest


@pytest.fixture
def memory_ga(monkeypatch):
    """Existing optimizer/SQLite state with explicit compiler and report IO inputs.

    This does not model a result center or claim file/WAL durability. Publication,
    shared pools and file recovery have separately marked real representatives.
    """
    from copy import deepcopy
    from itertools import permutations
    import random
    import sqlite3
    from types import SimpleNamespace
    import codec
    import engine
    import population_training as training
    import program
    import result_store
    import sequence
    from runtime import TaskRuntime
    from search import TaskStore, config_for, optimize
    from seed_training import template_character
    from simulation_config import TRAINING_DEFAULTS
    from test_search import _fast_capabilities, _fast_report
    from test_character_export import sample_profile
    stores = []
    def make(*, programs=None, settings=None, native=None, score_for=None, formal=False, search_settings=None,
             manifest_fields=None, memory_destination=None):
        capabilities = _fast_capabilities()
        starts = (deepcopy(programs) if programs is not None else
                  [[[name] for name in order] for order in permutations(
                      ('outbreak', 'death_coil', 'scourge_strike'))])
        config = dict(TRAINING_DEFAULTS, top_k=4, max_processes=1,
                      crossover_probability=0., target_mutation_probability=0., random_mutation_probability=0.)
        if set(settings or {}) - set(config):
            raise ValueError('训练样例包含未知参数')
        config.update(settings or {})
        # Overrides must not be duplicated in dict's keyword construction.
        search_values = dict(max_processes=1)
        search_values.update(search_settings or {})
        search_config = config_for(search_values, training=not formal)
        character = template_character(sample_profile())
        store = (TaskStore(memory_destination, memory_execution=True,
                           reusable_database=':memory:', report_locations={}) if memory_destination is not None else
                 TaskStore(Path('/memory/ga'), connection=sqlite3.connect(':memory:', check_same_thread=False),
                           reusable_database=':memory:', report_locations={}))
        stores.append(store)
        plan = training._stage_plan(config, 20260912)
        if formal:
            from formal_search import contract_for
            if settings: raise ValueError('formal GA settings must come from the production contract')
            frozen = contract_for(search_config)
            config, plan = frozen['config'], frozen['stage_plan']
        manifest = dict(training_config=config, stage_plan=plan, **(manifest_fields or {}))
        from search import digest
        condition = digest(manifest)
        store.state.update(run_id='memory', condition=condition, starts=starts, config=search_config,
            behavior_identity_version=program.BEHAVIOR_IDENTITY_VERSION,
            archive=[], errors=[], ga=dict(algorithm=training.ALGORITHM, phase='initial', generation=0,
            stagnant=0, population=[], pending=None, rng=random.Random(20260912).getstate(), finals={}, baseline=[]))
        if formal: store.state['formal_search'] = frozen
        calls, reports, records = [], {}, {}
        def compile_input(mapped, folder, **kwargs):
            # A native-compiler response fixture, using the existing Program mapping.
            blocks = program._search_blocks(mapped)
            clicks = program._search_clicks(dict(blocks=blocks), mapped)
            commands = [row.get('commands', []) for row in clicks]
            return program._with_compiled_program(dict(blocks=blocks, compiled_steps=list(range(len(clicks))),
                mapped_blocks=commands, text='verified compiler fixture'), mapped, clicks)
        def evaluate(profile, candidate, folder, **options):
            calls.append((str(folder), deepcopy(candidate), deepcopy({k:v for k,v in options.items()
                          if k not in ('runtime', 'on_native_start', 'character')})))
            if options.get('on_native_start'):
                options['on_native_start']()
            if native is not None:
                return native(profile, candidate, folder, **options)
            score = 100. if score_for is None else score_for(candidate, options)
            report = _fast_report(character, score, max(1, options['iterations'] - 1))
            report['sim']['targets'] *= options['simulation_config']['target_count']
            summary = engine.check_report(report, character, options['iterations'],
                simulation_config=options['simulation_config'], allow_zero=True)
            return dict(report=report, summary=summary, trace=[])
        def stage_report(key, row, stored, **kwargs):
            reports[key] = deepcopy(stored)
            store.put_batch(key, row, verified=True)
            if store.memory_execution and row['request']['purpose'] != 'diagnostic':
                store.state['completed_batches'] += 1
        monkeypatch.setattr(codec, 'load_targeting', lambda **kwargs: dict(target_masks={}))
        monkeypatch.setattr(program, 'compile_program', compile_input)
        monkeypatch.setattr(sequence, 'evaluate', evaluate)
        monkeypatch.setattr(result_store, 'DATA_ROOT', Path('/memory/ga-result-center'))
        monkeypatch.setattr(result_store, 'report_locations', lambda keys:
                            {key: key if key in reports else None for key in keys})
        monkeypatch.setattr(result_store, 'write', lambda table, key, rows, **kwargs:
                            records.__setitem__((table, key), deepcopy(rows)))
        monkeypatch.setattr(result_store, 'write_traces', lambda *args, **kwargs: None)
        monkeypatch.setattr(result_store, 'one', lambda table, field, key, **kwargs: deepcopy(reports.get(key)))
        class MissingStoredKey(KeyError):
            pass
        def read_many(table, keys, **kwargs):
            if table == 'batches':
                return [deepcopy(reports[key]) for key in keys if key in reports]
            if any((table, key) not in records for key in keys):
                raise result_store.DataReadError('指定记录组缺失') from MissingStoredKey(keys)
            return [deepcopy(row) for key in keys for row in records[table, key]]
        monkeypatch.setattr(result_store, 'read_many', read_many)
        if memory_destination is not None:
            monkeypatch.setattr(result_store, '_api', lambda: dict(MissingKeyError=MissingStoredKey))
        monkeypatch.setattr(store, 'stage_report', stage_report)
        monkeypatch.setattr(Path, 'unlink', lambda self, **kwargs: None)
        monkeypatch.setattr(engine, 'discard_diagnostic_files', lambda *args: None)
        ready = dict(simulation_config=dict(target_count=1, scene='single_target'),
                     context=dict(capabilities=capabilities), template_sha='memory-template', engines={})
        def run(runner=None, *, timeline=None, runtime=None):
            runtime = runtime or TaskRuntime(float('inf'), diagnostic_logging=search_config['diagnostic_logging'])
            if timeline is not None: runtime.search_timeline=timeline
            if formal and runner is None:
                from formal_search import run as run_formal
                summary = _fast_report(character, 100., 99)['sim']['players'][0]['sim2gse_action_summary']
                summary.update(successes={'spell:1001':99})
                summary['scope']['allowed'] = {'spell:1001': True}
                return run_formal(profile=Path('/memory/standard.simc'), character=character,
                    capabilities=capabilities, reference=dict(dps=100., identity=dict(resource='runic_power'), action_summary=summary),
                    destination=Path('/memory/ga'), runtime=runtime, config=search_config,
                    condition_key=condition, store=store, simulation_config=ready['simulation_config'])
            default_execute = training._evolution(store, capabilities, runtime, config)
            execute = default_execute if runner is None else runner
            return optimize(profile=Path('/memory/standard.simc'), character=character,
                capabilities=capabilities, reference=dict(identity=dict(resource='runic_power')),
                destination=Path('/memory/ga'), runtime=runtime, config=search_config,
                condition_key=condition, store=store, simulation_config=ready['simulation_config'],
                training=True, training_runner=execute, training_stage_plan=plan)
        return SimpleNamespace(store=store, config=config, starts=starts, capabilities=capabilities,
            character=character, plan=plan, calls=calls, reports=reports, run=run, ready=ready,
            manifest=manifest, condition=condition, search_config=search_config)
    yield make
    for store in stores:
        store.diagnostic_logging_override = False
        store.close()

@pytest.mark.real
@pytest.mark.parametrize('formal', [False, True], ids=['training', 'formal'])
def test_memory_compile_allows_another_candidate_and_live_progress(memory_ga, tmp_path, monkeypatch, formal):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock
    import program
    from runtime import TaskRuntime
    from task import read_task
    settings = dict(max_processes=2, top_k=4, stagnation_generations=2,
        target_mutation_probability=0., random_mutation_probability=0., crossover_probability=0.)
    case = memory_ga(programs=[[['outbreak']], [['death_coil']], [['scourge_strike']]],
        formal=formal, settings=None if formal else settings,
        search_settings=settings if formal else dict(max_processes=2), memory_destination=tmp_path)
    compile_response = program.compile_program
    first, second, release = Event(), Event(), Event()
    guard = Lock()
    calls = 0
    def controlled_compile(*args, **kwargs):
        nonlocal calls
        with guard:
            calls += 1
            position = calls
        if position == 1:
            first.set()
            assert release.wait(10), '受控编译未得到收尾信号'
        else:
            second.set()
        return compile_response(*args, **kwargs)
    monkeypatch.setattr(program, 'compile_program', controlled_compile)
    runtime = TaskRuntime(float('inf'))
    def run():
        with case.store.active(runtime):
            return case.run(runtime=runtime)
    with ThreadPoolExecutor(max_workers=2) as clients:
        computation = clients.submit(run)
        try:
            assert first.wait(2)
            progress = clients.submit(read_task, tmp_path)
            assert second.wait(2), '其他候选不应等待第一条完整编译'
            assert progress.result(timeout=2)['status'] == 'running'
        finally:
            release.set()
        computation.result(timeout=10)
    assert calls == 3


@pytest.mark.real
@pytest.mark.parametrize('failure', [None, 'reject', 'cancel', 'budget', 'mismatch'])
def test_memory_shared_compile_notifies_waiters_and_preserves_failure_accounting(
        memory_ga, tmp_path, monkeypatch, failure):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, get_ident
    import program
    from engine import CandidateError
    from runtime import BudgetExceeded, TaskCancelled, TaskRuntime
    entered, waiting, release = Event(), Event(), Event()
    owner = None
    attempts = 0
    class ObservedRuntime(TaskRuntime):
        def check(self):
            super().check()
            if entered.is_set() and get_ident() != owner:
                waiting.set()
    runtime = ObservedRuntime(float('inf'), diagnostic_logging=True)
    runtime.memory_execution = True
    case = memory_ga(programs=[[['outbreak']]], settings=dict(max_processes=2),
        search_settings=dict(max_processes=2, diagnostic_logging=True, diagnostics='summary'),
        memory_destination=tmp_path)
    compile_response = program.compile_program
    def controlled_compile(*args, **kwargs):
        nonlocal owner, attempts
        attempts += 1
        owner = get_ident()
        entered.set()
        assert release.wait(10)
        kwargs['on_lua_start']()
        if failure == 'reject':
            raise ValueError('编译拒绝样例')
        if failure == 'cancel':
            runtime.cancel()
            runtime.check()
        if failure == 'budget':
            runtime.phase_limit = 0
            runtime.check()
        result = compile_response(*args, **kwargs)
        if failure == 'mismatch':
            result['compiled_program']['clicks'][0]['commands'] = ['death_coil']
        return result
    monkeypatch.setattr(program, 'compile_program', controlled_compile)
    def simultaneous(*, evaluate, feedback):
        def request(stage):
            try:
                return evaluate(case.starts[0], stage, 0)
            except (CandidateError, TaskCancelled, BudgetExceeded) as error:
                return error
        with ThreadPoolExecutor(max_workers=2) as callers:
            rows = [callers.submit(request, stage) for stage in ('search', 'nominal')]
            return [row.result(timeout=10) for row in rows]
    with ThreadPoolExecutor(max_workers=1) as client:
        result = client.submit(case.run, simultaneous, runtime=runtime)
        try:
            assert entered.wait(2)
            assert waiting.wait(2), '重复候选必须在共用锁之外等待编译'
        finally:
            release.set()
        rows = result.result(timeout=10)
    assert attempts == 1 and case.store.lua_compiler_starts == 1
    assert case.store.diagnostic_summary['candidate_compilations'] == (0 if failure in ('reject', 'cancel', 'budget') else 1)
    assert not case.store.state.get('training_failures')
    if failure is None:
        assert all(isinstance(row, dict) for row in rows) and len(case.calls) == 2
        assert rows[0]['candidate_key'] == rows[1]['candidate_key']
    else:
        expected = {'cancel': TaskCancelled, 'budget': BudgetExceeded}.get(failure, CandidateError)
        assert all(isinstance(row, expected) for row in rows) and not case.calls
        failure = None
        runtime = ObservedRuntime(float('inf'), diagnostic_logging=True)
        runtime.memory_execution = True
        case.run(runtime=runtime)
        assert case.store.state['ga']['phase'] == 'qualified'


@pytest.mark.real
@pytest.mark.parametrize('formal', [False, True], ids=['training', 'formal'])
def test_memory_coarse_scoring_fills_free_slots_before_slow_first_request_finishes(memory_ga, tmp_path, formal):
    from itertools import permutations
    from threading import Event, Lock
    programs = [[[name] for name in order] for order in list(permutations(
        ('outbreak', 'death_coil', 'scourge_strike', 'dark_transformation')))[:13]]
    thirteenth = Event()
    lock = Lock()
    active = peak = started = 0
    def score(candidate, options):
        nonlocal active, peak, started
        if options['iterations'] != 32:
            return 100.
        with lock:
            started += 1
            position = started
            active += 1
            peak = max(peak, active)
        try:
            if position == 13:
                thirteenth.set()
            if position == 1:
                assert thirteenth.wait(2), '第十三个粗评必须在首个慢请求结束前补位'
            return 100.
        finally:
            with lock:
                active -= 1
    settings = dict(max_processes=5, top_k=4, stagnation_generations=2,
                    target_mutation_probability=0., random_mutation_probability=0., crossover_probability=0.)
    case = memory_ga(programs=[*programs, programs[0]], formal=formal, score_for=score,
        settings=None if formal else settings, search_settings=settings if formal else dict(max_processes=5),
        memory_destination=tmp_path)
    case.run()
    ga = case.store.state['ga']
    assert thirteenth.is_set() and started == 13 and 1 < peak <= 5 and active == 0
    assert ga['generation'] == 2 and len(ga['population']) == 14
    assert len(case.store.state['archive']) == 13
    assert {row['score'] for row in ga['population']} == {100.}


@pytest.mark.real
@pytest.mark.parametrize('formal', [False, True], ids=['training', 'formal'])
def test_memory_rolling_coarse_keeps_requests_random_state_and_final_selection(memory_ga, tmp_path, formal):
    from copy import deepcopy
    from itertools import permutations
    from search import digest
    programs = [[[name] for name in order] for order in list(permutations(
        ('outbreak', 'death_coil', 'scourge_strike', 'dark_transformation')))[:13]]
    settings = dict(max_processes=3, top_k=4, stagnation_generations=2,
                    target_mutation_probability=0., random_mutation_probability=0., crossover_probability=0.)
    def score(candidate, options):
        return 100. + int(digest(candidate['blocks'])[:4], 16) / 1000
    observations = []
    for destination in (None, tmp_path):
        case = memory_ga(programs=[*programs, programs[0]], formal=formal, score_for=score,
            settings=None if formal else settings,
            search_settings=settings if formal else dict(max_processes=3), memory_destination=destination)
        result = case.run()
        if formal:
            result = deepcopy(result)
            result.pop('elapsed_seconds')
            result['search']['records'].sort(key=lambda row: row['key'])
        observations.append(dict(result=deepcopy(result), ga=deepcopy(case.store.state['ga']),
            requests=sorted(digest(row['request']) for row in case.store.verified_batches.values()),
            evaluations=len(case.calls),
            archive=sorted((row['key'], row['score']) for row in case.store.state['archive'])))
    assert observations[0] == observations[1]


@pytest.mark.real
@pytest.mark.parametrize('failure', ['fatal', 'cancel'])
def test_memory_rolling_coarse_stops_refilling_and_drains_owned_work(memory_ga, tmp_path, failure):
    from itertools import permutations
    from threading import Event, Lock
    from runtime import TaskCancelled, TaskRuntime
    programs = [[[name] for name in order] for order in permutations(
        ('outbreak', 'death_coil', 'scourge_strike', 'dark_transformation'))]
    runtime = TaskRuntime(float('inf'))
    lock, failed = Lock(), Event()
    active = started = 0
    def score(candidate, options):
        nonlocal active, started
        with lock:
            started += 1
            first = started == 1
            active += 1
        try:
            if first:
                failed.set()
                if failure == 'cancel':
                    runtime.cancel()
                    runtime.check()
                raise RuntimeError('评分连接失败')
            assert failed.wait(2)
            runtime.check()
            return 100.
        finally:
            with lock:
                active -= 1
    case = memory_ga(programs=programs, settings=dict(max_processes=3),
        search_settings=dict(max_processes=3), score_for=score, memory_destination=tmp_path)
    with pytest.raises(TaskCancelled if failure == 'cancel' else RuntimeError,
                       match='任务已取消' if failure == 'cancel' else '评分连接失败'):
        case.run(runtime=runtime)
    assert failed.is_set() and active == 0 and started < len(programs)
    assert case.store.state['ga']['phase'] == 'initial'
    assert case.store.state['ga']['generation'] == 0
    case.store.checkpoint(boundary='pause')
    runtime = TaskRuntime(float('inf'))
    case.run(runtime=runtime)
    assert case.store.state['ga']['generation'] == 2
    assert len(case.store.state['archive']) == len(programs)


def test_v3_selected_independently_reads_full_source_cohort(monkeypatch, memory_ga):
    from copy import deepcopy
    import hashlib
    from types import SimpleNamespace
    import population_training as training
    import result_store
    from search import digest
    from test_character_export import sample_profile
    text = sample_profile()
    environment = dict(template=hashlib.sha256(text.encode()).hexdigest(), engines={},
                       simulation=dict(target_count=1, scene='single_target'))
    case = memory_ga(manifest_fields=dict(seed=20260912, environment=environment))
    ga = case.run()
    records = {}
    read_many = result_store.read_many
    monkeypatch.setattr(result_store, 'write', lambda table, key, rows, **kwargs:
                        records.__setitem__((table, key), deepcopy(rows)))
    monkeypatch.setattr(result_store, 'read_records', lambda table, key:
                        deepcopy(records.get((table, key), [])))
    monkeypatch.setattr(result_store, 'read_many', lambda table, keys, **kwargs:
        read_many(table, keys, **kwargs) if table == 'batches' else
        [deepcopy(row) for key in keys for row in records.get((table, key), [])])
    receipts = {}
    groups = {}
    for identity in ga['finalists']:
        for batches in ga['finals'][identity].values():
            for row in batches.values():
                key = row['batch_key']
                receipts[key] = dict(case.store.batch(key), storage_version=3, storage_group_key=key)
                groups[key] = key
    state = dict(case.store.state, capabilities=case.capabilities,
                 evidence_storage=dict(version=3, report_groups=groups))
    archive = [dict(run_id=state['run_id'], candidate_key=row['key'], search_order=index,
        program=row['program'], program_digest=digest(row['program']), score=row['score'],
        batches=row['batches'], candidate=None) for index, row in enumerate(state['archive'])]
    records['search_records', 'archive'] = archive
    state['evidence_storage'].update(archive_group='archive', archive_digest=digest(archive),
                                     archive_count=len(archive))
    store = SimpleNamespace(memory_execution=True, state=state, batch=receipts.get,
                            published_report_receipts={})
    manifest = case.manifest
    ready = dict(case.ready, text=text, template_sha=environment['template'])
    key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')
    state['configuration_key'] = key
    training._publish_seed_evidence(ga, store, manifest, case.character, ready)
    selected = training._selected(ga, store, manifest, case.character, ready, key)
    training.verify_selected_evidence(selected)
    wrong_group = deepcopy(selected)
    for row in wrong_group:
        row['configuration_key'] = dict(key, hero_talent='sanlayn')
    with pytest.raises(ValueError, match='分组'):
        training.verify_selected_evidence(wrong_group)
    missing = next(iter(receipts))
    case.reports.pop(missing)
    with pytest.raises(ValueError, match='完整复测报告'):
        training.verify_selected_evidence(selected)


def test_public_check_freezes_both_verified_heroes_and_four_groups(monkeypatch):
    from unittest.mock import mock_open, patch
    import engine
    import seed_training
    from simulation_config import TRAINING_DEFAULTS
    from test_character_export import sample_profile
    templates = (Path('/templates/Rider.simc'), Path("/templates/San'layn.simc"))
    monkeypatch.setattr(engine, 'training_templates', lambda: templates)
    monkeypatch.setattr(engine, 'identity', lambda mode: (Path('/engine'), dict(upstream_commit='fixed')))
    with patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'read_text', return_value=sample_profile()):
        result = seed_training.check_training(use_burst=False, training_config=dict(TRAINING_DEFAULTS))
    assert len(result['templates']) == 2
    assert {row['configuration_key']['hero_talent'] for row in result['groups']} == {
        'rider_of_the_apocalypse', 'sanlayn'}
    assert {row['configuration_key']['target_type'] for row in result['groups']} == {'single_target', 'aoe'}
    assert result['training_config']['max_trainings'] == 4
    assert result['training_config']['max_processes'] == 5
    assert result['final_requested_iterations_per_group'] == 15360


def test_public_selection_reads_each_report_group_once_without_skipping_receipts(monkeypatch,memory_ga):
    from copy import deepcopy
    from weakref import WeakValueDictionary
    import population_training
    import result_store
    from search import digest
    case=memory_ga(settings=dict(top_k=6,retest_batches=4))
    ga=case.run()
    finals=[row for row in case.reports.values() if row['purpose']!='search']
    groups={f'group{index}':finals[at:at+12] for index,at in enumerate(range(0,len(finals),12))}
    for group,rows in groups.items():
        for row in rows:
            receipt=case.store.batch(row['batch_key'])
            case.store.put_batch(row['batch_key'],dict(receipt,storage_group_key=group))
    counts=dict(reports=0,summaries=0,validations=0,manifests=0)
    sizes=[]
    live=WeakValueDictionary()
    class Report(dict): pass
    duplicate=False
    def read_many(table,keys,**kwargs):
        counts['reports']+=1
        assert table=='batches' and len(keys)==1 and not live
        rows=[Report(deepcopy(row)) for row in groups[keys[0]]]
        if duplicate: rows[1]=rows[0]
        sizes.append(len(rows))
        live.update((id(row),row) for row in rows)
        assert len(live)<=12
        return rows
    batch,validate,hashed=case.store.batch,population_training._validate_saved_batch,population_training.digest
    first_key=finals[0]['batch_key']
    def summary(key):
        counts['summaries']+=1
        row=batch(key)
        return dict(row,storage_group_key=None) if key==first_key else row
    def verified(*args):
        counts['validations']+=1
        return validate(*args)
    def counted_digest(value):
        counts['manifests']+=value is case.manifest
        return hashed(value)
    monkeypatch.setattr(case.store,'batch',summary)
    monkeypatch.setattr(result_store,'read_many',read_many)
    monkeypatch.setattr(result_store,'report_locations',lambda keys:{first_key:'group0'})
    monkeypatch.setattr(Path,'exists',lambda path:path.name=='.report-locations.jsonl')
    monkeypatch.setattr(population_training,'_validate_saved_batch',verified)
    monkeypatch.setattr(population_training,'digest',counted_digest)
    key=dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target')
    rows=population_training._selected(ga,case.store,case.manifest,case.character,case.ready,key)
    assert len(rows)==4 and [row['candidate_id'] for row in rows]==sorted(row['candidate_id'] for row in rows)
    assert {row['score'] for row in rows}=={100.}
    assert counts==dict(reports=10,summaries=120,validations=120,manifests=1)
    assert sizes==[12]*10 and not live
    duplicate=True
    with pytest.raises(ValueError,match='发布复测报告重复'):
        population_training._selected(ga,case.store,case.manifest,case.character,case.ready,key)


def test_public_training_accepts_verified_zero_stress_as_full_loss_without_retry(memory_ga):
    import population_training
    def score(candidate, options):
        stress = options['iterations'] == 128 and options['input_times'] != list(range(0, 180000, 300))
        return 0. if stress else 100.
    case = memory_ga(score_for=score)
    ga = case.run()
    rows = population_training._selected(ga, case.store, case.manifest, case.character,
        case.ready, dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'))
    zeros = [folder for folder, _, options in case.calls
             if options['iterations'] == 128 and options['input_times'] != list(range(0,180000,300))]
    assert len(zeros) == len(set(zeros)) == 48
    assert all(row['evaluation']['stability_loss'] == 1. for row in rows)


@pytest.mark.parametrize('failure_kind,failures',
    [(kind, count) for kind in ('candidate', 'exit', 'missing', 'json', 'nan', 'inf', 'samples') for count in (1, 2)]
    + [('identity', 1), ('storage', 1), ('duration', 1)])
def test_public_run_retries_original_request_once_and_preserves_exhaustion_on_resume(
        monkeypatch, memory_ga, failures, failure_kind):
    from copy import deepcopy
    import engine
    from engine import CandidateError, NativeEvaluationError
    from test_search import _fast_report
    attempts = []
    def native(profile, candidate, folder, **options):
        attempts.append((options['seed'], tuple(options['input_times']), deepcopy(candidate)))
        bad = len(attempts) <= failures
        if bad and failure_kind == 'candidate':
            raise CandidateError('constructed native failure')
        if bad and failure_kind == 'exit':
            from types import SimpleNamespace
            from unittest.mock import patch
            process = SimpleNamespace(returncode=1, stdout=b'constructed failure', stderr=b'')
            with patch.object(Path, 'mkdir'), patch.object(engine, 'identity', return_value=(Path('/engine'), {})), \
                    patch.object(engine, 'run_command', return_value=process):
                return engine.run(profile, folder, runtime=options['runtime'])
        if bad and failure_kind in ('missing', 'json', 'storage'):
            # Parse/translate at the existing sequence IO seam, not in retry code.
            import sequence
            from unittest.mock import patch
            log = '\n'.join(f'S2GBLOCK\t{i}\t{j}\t{name}'
                for i, block in enumerate(sequence.compiled_program(candidate)) for j, name in enumerate(block))
            def read(path, **kwargs):
                if path.name == 'native.pending.json':
                    if failure_kind == 'missing': raise FileNotFoundError('missing report')
                    if failure_kind == 'storage': raise PermissionError('constructed report storage denied')
                    return '{broken'
                return 'fixture profile'
            with patch.object(Path, 'mkdir'), patch.object(Path, 'write_text'), \
                    patch.object(Path, 'read_text', read), patch.object(sequence, 'run', return_value=log):
                return original_sequence_evaluate(profile, candidate, folder, **options)
        report = _fast_report(options['character'],
            float(failure_kind) if bad and failure_kind in ('nan','inf') else 100.,
            30 if bad and failure_kind == 'samples' else 31)
        if bad and failure_kind == 'identity': report['sim']['targets'] *= 5
        if bad and failure_kind == 'duration':
            report['sim']['players'][0]['collected_data']['fight_length']['mean'] = 179
        summary = engine.check_report(report, options['character'], options['iterations'],
            simulation_config=options['simulation_config'], allow_zero=True)
        return dict(report=report, summary=summary, trace=[])
    import sequence
    original_sequence_evaluate = sequence.evaluate
    case = memory_ga(native=native)
    runner = lambda **callbacks: callbacks['evaluate'](case.starts[0], 'search', 0)
    retryable = failure_kind not in ('identity', 'storage', 'duration')
    if failures == 1 and retryable:
        assert case.run(runner)['dps'] == 100.
    else:
        error = (PermissionError if failure_kind == 'storage' else ValueError
                 if failure_kind in ('identity', 'duration') else CandidateError
                 if failure_kind == 'candidate' else engine.CandidateScoreError
                 if failure_kind in ('nan', 'inf') else NativeEvaluationError)
        reason = ('constructed native failure' if failure_kind == 'candidate' else
                  '原生引擎失败' if failure_kind == 'exit' else '原生报告缺失' if failure_kind in ('missing', 'json') else
                  '目标数量不符' if failure_kind == 'identity' else 'storage denied' if failure_kind == 'storage' else
                  '原生参考数值或实际样本数无效')
        with pytest.raises(error, match=reason): case.run(runner)
        before = deepcopy(attempts)
        if retryable:
            with pytest.raises(CandidateError, match='已用尽一次重试'): case.run(runner)
            assert attempts == before
        else:
            assert not case.store.state['training_failures']
    assert len(attempts) == (2 if retryable else 1)
    if retryable: assert attempts[0] == attempts[1]


def test_public_run_feedback_failure_uses_same_persistent_single_retry_budget(memory_ga):
    from engine import CandidateError
    def native(*args, **kwargs): raise CandidateError('constructed feedback failure')
    case = memory_ga(native=native)
    runner = lambda **callbacks: callbacks['feedback'](case.starts[0])
    with pytest.raises(CandidateError, match='constructed feedback failure'): case.run(runner)
    assert len(case.calls) == 2 and case.calls[0] == case.calls[1]
    assert list(case.store.state['training_failures'].values()) == [2]
    # Reload the actual persisted SQLite state, not a fabricated retry counter.
    case.store.state = case.store.load_state(case.store.db)
    with pytest.raises(CandidateError, match='已用尽一次重试'): case.run(runner)
    assert len(case.calls) == 2


@pytest.mark.parametrize('overflow', ['clicks', 'macro'])
def test_public_illegal_slot_uses_first_child_and_ten_persistent_extra_regenerations(
        monkeypatch, memory_ga, overflow):
    import random
    from types import SimpleNamespace
    import population_training
    operations = []
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow = real_random._randbelow
        def random(self): return .99
        def choice(self, values):
            if isinstance(values,list) and values and values[0]=='swap' and 'insert' in values:
                count = getattr(self,'operations',0)+1
                self.operations=count
                operation = ('insert' if overflow=='clicks' else 'block') if count==1 or count%2==0 else 'delete'
                operations.append(operation)
                return operation
            if overflow=='macro' and values==[0,1]: return 0
            return super().choice(values)
        def randrange(self,*args):
            if args==(2,): return 1 if overflow=='clicks' else 0
            return super().randrange(*args)
    program = ([['outbreak'],dict(kind='WaitClicks',clicks=4095)] if overflow=='clicks'
               else [['scourge_strike']*12,['outbreak']])
    case=memory_ga(programs=[program],settings=dict(random_mutation_probability=1.))
    monkeypatch.setattr(population_training,'random',SimpleNamespace(Random=BoundaryRandom))
    for resume in (False,True):
        if resume: case.store.state=case.store.load_state(case.store.db)
        with pytest.raises(ValueError,match='已耗尽10次额外重生'): case.run()
        operation='insert' if overflow=='clicks' else 'block'
        assert operations==[operation,*[operation,'delete']*10]
        assert case.store.state['ga']['pending']['regenerations']==[10]


def test_public_a_tournament_and_block_crossover_keep_duplicate_slots_and_reuse_scores(monkeypatch,memory_ga):
    import random
    from types import SimpleNamespace
    import population_training
    draws=[]
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow=real_random._randbelow
        def random(self): return .5
        def choice(self,values):
            if values and hasattr(values[0],'fitness'):
                offset=len(draws)%len(values)
                draws.append(offset)
                return values[offset]
            return super().choice(values)
        def randint(self,first,last): return first
    case=memory_ga(settings=dict(crossover_probability=1.))
    monkeypatch.setattr(population_training,'random',SimpleNamespace(Random=BoundaryRandom))
    ga=case.run()
    coarse=[tuple(tuple(command['simc_action'] for command in block) for block in candidate['blocks'])
            for _,candidate,options in case.calls if options['iterations']==32]
    assert len(draws)==6*3*2
    assert (('outbreak',),('scourge_strike',),('outbreak',)) in coarse
    assert (('death_coil',),('death_coil',),('scourge_strike',)) in coarse
    assert len(coarse)==len(set(coarse))==8
    slots=[row['key'] for row in ga['population']]
    assert len(slots)==6 and len(set(slots))==2
    assert len(case.calls)==68


@pytest.mark.parametrize('invalid_nominal', [False, True])
def test_public_selection_keeps_nominal_and_minimax_stability_champions_and_reports_ineligible(
        memory_ga, invalid_nominal):
    import population_training
    from itertools import permutations
    programs = {tuple((name,) for name in order): index for index, order in enumerate(
        permutations(('outbreak', 'death_coil', 'scourge_strike')))}
    nominal, stress = [200.,180.,160.,140.,120.,100.], [150.,162.,144.,139.,115.,110.]
    def score(candidate, options):
        index = programs[tuple(tuple(row['simc_action'] for row in block) for block in candidate['blocks'])]
        is_nominal = options['input_times'] == list(range(0,180000,300))
        return (0. if invalid_nominal and index == 5 and is_nominal and options['iterations'] == 128
                else nominal[index] if is_nominal else stress[index])
    case = memory_ga(settings=dict(top_k=6), score_for=score)
    ga = case.run()
    rows = population_training._selected(ga, case.store, case.manifest, case.character,
        case.ready, dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target'))
    assert {row['score'] for row in rows} == ({200.,180.,160.,140.} if invalid_nominal else {200.,180.,160.,100.})
    evaluations = {row['score']:row['evaluation'] for row in rows}
    assert evaluations[200.]['nominal_champion']
    assert evaluations[200.]['stability_loss'] == .25
    assert evaluations[140. if invalid_nominal else 100.]['stable_representative']
    if invalid_nominal:
        assert len(ga['ineligible']) == 1
        assert '正常复测均分≤0' in next(iter(ga['ineligible'].values()))
    else:
        assert evaluations[100.]['stability_loss'] == -.1
    assert sum(options['iterations']==32 for _,_,options in case.calls) == 6
    assert sum(options['iterations']==128 for _,_,options in case.calls) == 90
    seeds = {iterations:{options['seed'] for _,_,options in case.calls if options['iterations']==iterations}
             for iterations in (32,128)}
    assert len(seeds[128]) == 15 and not seeds[32] & seeds[128]


@pytest.mark.parametrize('version',[None,1,2,99])
def test_public_formal_entry_reads_legacy_contract_rejects_unknown_and_recycles_completed_winner(monkeypatch,memory_ga,version):
    from seed_training import selected_contract_version
    from task import _seed_programs
    from runtime import TaskRuntime
    case=memory_ga()
    key=dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target')
    rows=[dict(configuration_key=key,candidate_id='old-'+str(index),class_name='deathknight',spec='unholy',
        program=program,score=99999.,scores=[99999.]*3,template_sha256='different-role',
        **(dict(contract_version=version) if version is not None else {})) for index,program in enumerate(case.starts[:4])]
    if version==99:
        with pytest.raises(ValueError,match='不支持的训练成果契约版本'): selected_contract_version(rows)
        assert not case.calls
        return
    assert selected_contract_version(rows)==(1 if version is None else version)
    if version != 2:
        import result_store
        from seed_training import training_champion
        monkeypatch.setattr(result_store, 'read_records', lambda *args, **kwargs: [])
        assert training_champion('deathknight', 'unholy', case.ready['simulation_config'],
            engines={}, input_interval_ms=300, configuration_key=key)['status'] == 'absent'
    starts,decisions=_seed_programs([],rows,character=case.character,targets=1,configuration_key=key,
        capabilities=case.capabilities,runtime=TaskRuntime(float('inf')))
    assert len(starts)==4 and {row['status'] for row in decisions}=={'accepted'}
    case.store.state['starts']=starts
    ga=case.run()
    assert {row['score'] for row in ga['population']}=={100.},'旧模板成绩不得借用'
    # The completed-winner registry read/write chain remains in the public real run.


def test_public_configured_sample_plan_and_stagnation_are_used_without_old_stage_caps(memory_ga):
    case = memory_ga(settings=dict(coarse_iterations=4, retest_batches=2, retest_iterations=8,
                                  stagnation_generations=3, tournament_size=7))
    ga = case.run()
    requests = [options['iterations'] for _,_,options in case.calls]
    assert ga['generation'] == ga['stagnant'] == 3
    assert requests.count(4) == 6 and requests.count(8) == 40 and len(requests) == 46
    assert case.config['top_k'] * 5 * case.config['retest_batches'] * case.config['retest_iterations'] == 320


# Coarse recovery stays in memory below; physical publication recovery keeps one retest group.


@pytest.mark.parametrize('mixed_new_groups',[False,True],ids=['all_frozen','mixed_new'])
def test_public_four_group_resume_uses_frozen_outer_pool_after_next_batch_toml_changes(monkeypatch,mixed_new_groups):
    from copy import deepcopy
    import population_training
    from simulation_config import TRAINING_DEFAULTS
    templates=[dict(template=str((Path('/templates')/f'{hero}.simc').resolve()),template_sha256=hero) for hero in ('rider','sanlayn')]
    old=dict(TRAINING_DEFAULTS)
    new=dict(old,max_trainings=10,max_processes=2) if mixed_new_groups else dict(old,max_trainings=1,max_processes=1)
    manifests=[(Path('/saved')/f'{index}-{count}',dict(template_path=row['template'],
        environment=dict(template=row['template_sha256'],simulation=dict(target_count=count)),training_config=deepcopy(old)))
        for index,row in enumerate(templates) for count in ((1,) if mixed_new_groups else (1,5))]
    before=deepcopy(manifests)
    monkeypatch.setattr(population_training,'_unfinished',lambda workspace:iter(manifests))
    configs=population_training.group_configs('/memory',templates,new)
    assert len(configs)==4
    assert population_training.group_workers('/memory',templates,new,effective_configs=configs)==4
    for (path,count),config in configs.items():
        fresh=mixed_new_groups and count==5
        assert config['max_trainings']==(10 if fresh else 4)
        assert config['max_processes']==(2 if fresh else 5)
    assert 4*max(row['max_processes'] for row in configs.values())==20
    assert manifests==before


@pytest.mark.parametrize('resume_logging', [False, True], ids=['logging-off', 'search-records-off'])
def test_formal_resume_stops_new_search_observations_without_removing_history(memory_ga, resume_logging):
    from copy import deepcopy
    from types import SimpleNamespace
    from runtime import TaskCancelled, TaskRuntime
    from search import config_for
    case = memory_ga(formal=True, programs=[[['outbreak']]],
                     search_settings=dict(diagnostic_logging=True, search_observability='full'))
    cancel = SimpleNamespace(is_set=lambda: case.store.state['ga']['generation'] >= 1)
    with pytest.raises(TaskCancelled):
        case.run(runtime=TaskRuntime(float('inf'), diagnostic_logging=True, cancel_event=cancel))
    case.store.checkpoint()
    case.store.state = case.store.load_state(case.store.db)
    history = deepcopy(case.store.state['search_observability'])
    assert history['summary']['mutation_attempts'] > 0 and history['details']
    frozen = deepcopy(case.store.state['formal_search'])
    previous_calls = [folder for folder, _, _ in case.calls]
    case.search_config.update(config_for(dict(case.search_config,
        diagnostic_logging=resume_logging, search_observability='off')))
    case.store.state['config'] = case.search_config
    result = case.run()
    assert result['status'] == 'completed'
    assert case.store.state['ga']['generation'] > 1
    assert case.store.load_state(case.store.db)['search_observability'] == history
    assert case.store.state['formal_search'] == frozen
    all_calls = [folder for folder, _, _ in case.calls]
    assert len(all_calls) == len(set(all_calls)) and all_calls[:len(previous_calls)] == previous_calls
    baseline = memory_ga(formal=True, programs=[[['outbreak']]])
    expected = baseline.run()
    assert result['selected_candidate_key'] == expected['selected_candidate_key']
    assert result['search_result'] == expected['search_result']
    assert case.calls == baseline.calls


def test_public_resume_verifies_coarse_before_breeding_and_keeps_temporary_read_errors(monkeypatch,memory_ga):
    from copy import deepcopy
    import population_training
    import result_store
    from runtime import TaskCancelled
    case=memory_ga(settings=dict(random_mutation_probability=1.))
    def pause(**callbacks):
        for program in case.starts: callbacks['evaluate'](program,'search',0)
        raise TaskCancelled('pause before breeding')
    with pytest.raises(TaskCancelled): case.run(pause)
    keys={row['batches'][0]['data_key'] for row in case.store.state['archive']}
    assert len(keys)==6
    case.store.state['ga'].update(phase='breed',population=[dict(program=deepcopy(row['program']),key=row['key'],score=row['score'])
        for row in case.store.state['archive']],baseline=[100.]*4)
    case.store.checkpoint()
    attempts=[]
    def unavailable(table,field,key,**kwargs):
        attempts.append(key)
        raise result_store.DataReadError('constructed temporary coarse read failure')
    case.store.verified_batches.clear()
    case.calls.clear()
    monkeypatch.setattr(result_store,'one',unavailable)
    with pytest.raises(result_store.DataReadError,match='temporary coarse read failure'): case.run()
    assert attempts and len(attempts)==len(set(attempts)) and not case.calls
    # Missing reliable IO evidence is repaired by the original evaluator, before mutation.
    verified=[]
    def missing(table,field,key,**kwargs):
        verified.append(key)
        return None
    monkeypatch.setattr(result_store,'one',missing)
    def mutation(*args,**kwargs): raise TaskCancelled('original feedback may resume after repair')
    with monkeypatch.context() as breeding:
        breeding.setattr(population_training,'mutate',mutation)
        with pytest.raises(TaskCancelled,match='after repair'): case.run()
    assert set(verified)==keys and len(verified)==len(keys)
    assert {Path(folder).name for folder,_,options in case.calls if options['iterations']==32}==keys
    assert len(case.calls)==6

    # Qualified recovery replaces only the missing coarse group, not successful retests.
    case=memory_ga()
    assert case.run()['phase']=='qualified'
    requests={key:deepcopy(case.store.batch(key)['request']) for key in case.reports}
    coarse={key for key,request in requests.items() if request['purpose']=='search'}
    retained={key:(deepcopy(case.reports[key]),deepcopy(case.store.batch(key)))
              for key in requests if key not in coarse}
    assert len(coarse)==6 and len(retained)==60 and len(case.calls)==66
    for key in coarse: case.reports.pop(key)
    case.store.verified_batches.clear()
    case.calls.clear()
    assert case.run()['phase']=='qualified'
    assert {Path(folder).name for folder,_,_ in case.calls}==coarse
    assert len(case.calls)==6 and all(options['iterations']==32 for _,_,options in case.calls)
    assert len(case.reports)==case.store.state['completed_batches']==66
    assert {key:case.store.batch(key)['request'] for key in case.reports}==requests
    assert {key:(case.reports[key],case.store.batch(key)) for key in retained}==retained


def test_public_alias_template_cannot_bypass_frozen_group_scheduling(monkeypatch):
    from copy import deepcopy
    import population_training
    import seed_training
    from simulation_config import TRAINING_DEFAULTS
    original=str(Path('/templates/original.simc').resolve())
    alias=str(Path('/templates/copied.simc').resolve())
    manifest=dict(template_path=original,training_config=dict(TRAINING_DEFAULTS,max_trainings=1,max_processes=16),
        environment=dict(template='same-role-bytes',simulation=dict(target_count=1)))
    frozen=deepcopy(manifest)
    def unfinished(workspace,**options):
        return iter([(Path('/saved/task'),manifest)]) if not options or options.get('scope') else iter(())
    monkeypatch.setattr(population_training,'_unfinished',unfinished)
    templates=[dict(template=alias,template_sha256='same-role-bytes')]
    with pytest.raises(ValueError,match='跨模板路径.*原模板路径'):
        population_training.group_configs('/memory',templates,dict(TRAINING_DEFAULTS,max_trainings=10,max_processes=2))
    # Public API uses the same scope guard before creating a task directory or scoring.
    context=dict(configuration_key=dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target'),burst=None)
    monkeypatch.setattr(Path,'glob',lambda *args:iter(()))
    monkeypatch.setattr(seed_training,'ensure_prepared',lambda *args,**kwargs:dict(context=context,queue=[{}],
        template_sha='same-role-bytes',engines={},simulation_config=dict(target_count=1),
        config={'syntax': __import__('simulation_config').syntax_for()}))
    import task
    monkeypatch.setattr(task,'_rule_hashes',lambda **kwargs:{})
    with pytest.raises(ValueError,match='跨模板路径'):
        population_training.run_group(alias,1,'/memory',cancel_event=None,use_burst=False,sources=[],config=TRAINING_DEFAULTS)
    assert manifest==frozen


def test_public_run_training_defaults_really_cross_and_mutate_without_global_rng_patch(monkeypatch,memory_ga):
    import random
    from types import SimpleNamespace
    import population_training
    from deap import algorithms
    original=algorithms.random
    real_random = random.Random
    class BoundaryRandom(real_random):
        _randbelow=real_random._randbelow
        def random(self): return .5
    case=memory_ga(settings=dict(crossover_probability=.8,random_mutation_probability=.8))
    monkeypatch.setattr(population_training,'random',SimpleNamespace(Random=BoundaryRandom))
    ga=case.run()
    coarse=[folder for folder,_,options in case.calls if options['iterations']==32]
    assert ga['algorithm']=='ga-easimple-v1' and ga['generation']==2
    assert len(ga['population'])==6 and len(coarse)==len(set(coarse))>6
    assert all(options['iterations']!=2 for _,_,options in case.calls)
    assert algorithms.random is original


def test_training_simple_policy_closes_children_and_publication(memory_ga):
    from itertools import product
    from test_search_syntax import SIMPLE
    import population_training
    from program import check_search_syntax
    # 两技能、长度1～4，共30条。变异与交叉都实际执行，不用复制补起点。
    programs = [[[name] for name in order] for size in range(1,5)
                for order in product(('outbreak','death_coil'), repeat=size)]
    case = memory_ga(programs=programs, settings=dict(random_mutation_probability=1., crossover_probability=1.),
                     search_settings={'syntax': SIMPLE, 'diagnostic_logging': True})
    ga = case.run()
    assert ga['breeding_counts']['random_triggered'] > 0
    assert ga['breeding_counts']['random_changed'] > 0
    assert ga['generation'] >= 2
    for _, candidate, _ in case.calls:
        check_search_syntax(candidate['program'], SIMPLE)
    rows = population_training._selected(ga, case.store, case.manifest, case.character, case.ready,
        dict(specialization_id=252,hero_talent='rider_of_the_apocalypse',target_type='single_target'))
    assert len(rows) == len({row['candidate_id'] for row in rows}) == 4
    assert all(row['evaluation']['syntax']['policy'] == SIMPLE for row in rows)
    assert case.capabilities['search_syntax'] == SIMPLE


@pytest.mark.parametrize('entry',['cli','api'])
@pytest.mark.parametrize('enabled',[False,True])
def test_public_ga_timeline_switch_exports_existing_scores_without_extra_evaluations(monkeypatch,memory_ga,enabled,entry):
    import argparse
    from unittest.mock import patch
    import simulation_config
    from search_timeline import Timeline
    if entry=='cli':
        parser=argparse.ArgumentParser()
        simulation_config.add_search_arguments(parser)
        parsed=parser.parse_args(['--search-timeline'] if enabled else ['--no-search-timeline'])
        options=simulation_config.load_search_config(search_timeline=parsed.search_timeline)
    else: options=simulation_config.load_search_config(search_timeline=enabled)
    assert options['search_timeline'] is enabled
    case=memory_ga()
    timeline=Timeline(context=dict(algorithm=dict(training='ga-easimple-v1'))) if enabled else None
    if timeline is not None: timeline.start()
    case.run(timeline=timeline)
    assert len(case.calls)==len({row[0] for row in case.calls})==66
    writes=[]
    if enabled:
        timeline.stop('stagnation')
        timeline.saved('completed')
        with patch.object(Path,'mkdir'),patch.object(Path,'write_text',lambda path,text,**kwargs:writes.append((path,text))):
            path=timeline.finish('/memory/ga')
        curve=json.loads(next(text for file,text in writes if file.suffix=='.json'))
        assert curve['schema']=='sim2gse-search-timeline-v1' and curve['status']=='completed'
        assert curve['search_start_seconds']<=curve['search_stop_seconds']<=curve['result_saved_seconds']
        assert curve['context']['algorithm']['training']=='ga-easimple-v1'
        assert {row['series'] for row in curve['events'] if row['kind']=='score'}=={'search','nominal','jitter','pause','slow','phase'}
        assert path.with_suffix('.html') in {file for file,text in writes}
    else: assert writes==[]


def test_public_pending_generation_reuses_coarse_receipts_without_resampling(monkeypatch,memory_ga):
    from copy import deepcopy
    from itertools import islice,product
    import random
    from runtime import TaskCancelled
    programs=[[[name] for name in order] for order in islice(product(('outbreak','death_coil','scourge_strike'),repeat=4),70)]
    case=memory_ga(programs=programs,formal=True,search_settings=dict(
        target_mutation_probability=0., random_mutation_probability=1., crossover_probability=0.))
    # Real SQLite checkpoints; compiler/report publication remain explicit IO inputs.
    real_stage,real_checkpoint=case.store.stage_report,case.store.checkpoint
    checkpoints=[]
    def staged(key,row,stored,**kwargs):
        real_stage(key,row,stored,**kwargs)
        if case.store.state['ga']['pending'] is not None:
            case.store.report_buffer.append((key,row,{}))
    def checkpoint():
        size=len(case.store.report_buffer)
        case.store.report_buffer.clear()  # Explicit report publisher IO boundary.
        real_checkpoint()
        if size:
            checkpoints.append(size)
            raise TaskCancelled('checkpoint interruption')
    monkeypatch.setattr(case.store,'stage_report',staged)
    monkeypatch.setattr(case.store,'checkpoint',checkpoint)
    with pytest.raises(TaskCancelled): case.run()
    assert checkpoints == [12]
    paused=case.store.load_state(case.store.db)['ga']
    frozen=deepcopy(paused['pending'])
    assert paused['generation']==0 and len(frozen['programs'])==70
    case.store.state=case.store.load_state(case.store.db)
    base_random = random.Random
    class NoResampling(base_random):
        _randbelow=base_random._randbelow
        def random(self):
            raise AssertionError('恢复已冻结子代时不得重抽繁殖概率')
    monkeypatch.setattr(random,'Random',NoResampling)
    with pytest.raises(TaskCancelled): case.run()
    resumed=case.store.load_state(case.store.db)['ga']
    assert resumed['generation']==0 and resumed['pending']==frozen
    assert checkpoints==[12,12]
    folders=[folder for folder,_,options in case.calls]
    assert len(folders)==len(set(folders))
    assert all(options['iterations']!=2 for _,_,options in case.calls)


def test_formal_resume_can_switch_observation_detail_without_changing_computation(memory_ga):
    from copy import deepcopy
    from types import SimpleNamespace
    from runtime import TaskCancelled, TaskRuntime
    case = memory_ga(formal=True, programs=[[['outbreak']]],
                     search_settings=dict(diagnostic_logging=True, search_observability='summary'))
    cancel = SimpleNamespace(is_set=lambda: case.store.state['ga']['generation'] >= 1)
    with pytest.raises(TaskCancelled):
        case.run(runtime=TaskRuntime(float('inf'), diagnostic_logging=True, cancel_event=cancel))
    frozen = deepcopy(case.store.state['formal_search'])
    history = deepcopy(case.store.state['search_observability'])
    assert not history['details']
    case.search_config['search_observability'] = 'full'
    result = case.run()
    assert result['status'] == 'completed'
    assert case.store.state['formal_search'] == frozen
    assert case.store.state['search_observability']['details']
    assert case.store.state['search_observability']['summary']['mutation_attempts'] > history['summary']['mutation_attempts']


def test_formal_invalid_child_has_same_outcome_with_observation_on_and_off(monkeypatch, memory_ga):
    import population_training
    from copy import deepcopy
    outcomes = []
    for enabled in (False, True):
        case = memory_ga(formal=True, programs=[[['outbreak'], ['death_coil']], [['scourge_strike']]],
            search_settings=dict(target_mutation_probability=0., random_mutation_probability=1.,
                crossover_probability=1., diagnostic_logging=enabled, search_observability='full'))
        calls = 0
        def temporary_invalid(program, *args, **kwargs):
            nonlocal calls
            calls += 1
            return [['missing_action']] if calls == 1 else deepcopy(list(program))
        monkeypatch.setattr(population_training, 'mutate', temporary_invalid)
        result = case.run()
        outcomes.append((result['candidate'], result['search_result'],
            [(candidate['program'], options['seed'], options['iterations']) for _,candidate,options in case.calls],
            case.store.state['ga']['rng']))
    assert outcomes[0] == outcomes[1]


def test_formal_master_off_retains_expected_detail_without_collecting_new_logs(memory_ga):
    case = memory_ga(formal=True, programs=[[['outbreak']]])
    result = case.run()
    assert case.search_config['diagnostic_logging'] is False
    assert (case.search_config['diagnostics'], case.search_config['search_observability']) == ('summary', 'full')
    assert 'search_observability' not in case.store.state
    assert 'diagnostics' not in result['search']
    assert not getattr(case.store, 'diagnostic_summary', None)


def test_single_resume_missing_simulation_keeps_saved_and_explicit_difference_rejects(memory_ga, monkeypatch):
    import hashlib, json, sqlite3
    from contextlib import nullcontext
    from types import SimpleNamespace
    import engine, result_store, search, seed_activity, task
    case = memory_ga(formal=True, programs=[[['outbreak']]])
    raw = b'frozen input'
    hashes = dict(input_original_sha256=hashlib.sha256(raw).hexdigest(),
                  input_effective_sha256=hashlib.sha256(raw).hexdigest())
    from simulation_config import syntax_receipt
    case.store.state.update(hashes, formal_search_version=1, syntax=syntax_receipt(case.search_config['syntax']),
        simulation_config=dict(target_count=5, scene='aoe', enable_omnium_talents=False))
    case.store.checkpoint()
    connection = SimpleNamespace(execute=case.store.db.execute, close=lambda: None)
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: connection)
    monkeypatch.setattr(search, 'TaskStore', lambda *a, **kw: case.store)
    close_store = case.store.close
    monkeypatch.setattr(case.store, 'close', lambda: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(task, '_task_lease', lambda *a: nullcontext())
    monkeypatch.setattr(seed_activity, 'foreground_search', nullcontext)
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: json.dumps(hashes))
    monkeypatch.setattr(Path, 'read_bytes', lambda *a: raw)
    monkeypatch.setattr(engine, 'identity', lambda *a: (_ for _ in ()).throw(ValueError('原生身份不可用')))
    monkeypatch.setattr('simulation_config._load_document', lambda *a: (_ for _ in ()).throw(AssertionError('不得读当前文件')))
    with pytest.raises(task.TaskError, match='原生身份不可用'):
        task.resume_task('/memory/ga')
    with pytest.raises(task.TaskError, match='恢复模拟配置发生变化'):
        task.resume_task('/memory/ga', simulation_config=dict(target_count=1, scene='single_target'))
    close_store()


def test_shared_variation_keeps_frozen_baseline_random_stream_and_children():
    """Oracle captured from 37a44b53's original gates, not from the new helper."""
    from copy import deepcopy
    import hashlib
    import random
    from deap import base
    from population_training import vary_offspring, _cross
    from program import canonicalize_search_program
    from test_search import _fast_capabilities
    capabilities = _fast_capabilities()
    reference = dict(version=1, samples=31, duration_ms=5580000, successes={'spell:1001': 31},
        pairs={}, outgoing={}, scope=dict(allowed={'spell:1001': True}, excluded={},
                                          windows='', policy='@apl', controlled=False))

    class Fitness(base.Fitness):
        weights = (1.,)

    class Member(list):
        pass

    outputs = []
    for seed in range(30):
        rng = random.Random(seed)
        toolbox = base.Toolbox()
        toolbox.register('clone', deepcopy)
        toolbox.register('mate', lambda a, b: _cross(a, b, rng))
        parents = []
        for program in ([['outbreak'], ['death_coil']], [['scourge_strike'], ['outbreak']]):
            member = Member(deepcopy(program))
            member.fitness = Fitness((100.,))
            member.action_summary = reference
            parents.append(member)
        counts = {route + suffix: 0 for route in ('target', 'random', 'crossover')
                  for suffix in ('_triggered', '_changed')}
        children = vary_offspring(parents, toolbox, rng=rng,
            config=dict(target_mutation_probability=.8, random_mutation_probability=.3, crossover_probability=.3),
            capabilities=capabilities, reference=reference,
            legal=lambda p: canonicalize_search_program(p, capabilities)['identity'],
            check=lambda: None, observe=lambda *a, **k: None, counts=counts)
        outputs.append(dict(children=[list(child) for child in children], rng=rng.getstate(), counts=counts))
    assert hashlib.sha256(json.dumps(outputs, sort_keys=True).encode()).hexdigest() == (
        '18c2223cfab8f5e99e77627a365db8c4da7dd3bdf55d3f68e4e110f7a8100750')
