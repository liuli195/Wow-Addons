"""冠军规则的明确输入，非数据库、原生引擎或第二套评分器。"""
from copy import deepcopy
from dataclasses import replace
import json


def formal_cohort(*, target_count=1, source_run_id='source-run', programs=None,
                  condition='frozen-condition', config=None):
    """两名完整入围者、各三份128次请求和127有效样本的外部报告输入。"""
    from test_character_export import sample_profile
    from test_search import _fast_capabilities, _fast_report
    from formal_search import contract_for
    from program import canonicalize_search_program
    from search import config_for, digest, input_times, STATS_VERSION
    from simulation_config import config_for as simulation_config_for
    from task import parse_character

    character = replace(parse_character(sample_profile()), spec_id=252)
    state = dict(condition=condition, input_effective_sha256='frozen-character',
        capabilities=_fast_capabilities(), engines=dict(baseline='source-base', controlled='source-controlled'),
        simulation_config=simulation_config_for(dict(target_count=target_count,
            scene='single_target' if target_count == 1 else 'aoe')),
        config=dict(config) if config is not None else config_for(dict(input_interval_ms=200)))
    contract = deepcopy(contract_for(state['config']))
    finalists, reports = [], []
    programs = programs or [[['outbreak']], [['death_coil']]]
    for program, score in zip(programs, (100., 200.)):
        canonical = canonicalize_search_program(program, state['capabilities'])
        receipts = []
        for index, seed in enumerate(contract['stage_plan']['nominal']['seeds']):
            request = dict(condition=state['condition'], program=canonical['form'],
                behavior_identity=canonical['identity'], purpose='nominal', seed=seed,
                input_seed=seed + 500000, iterations=128,
                times=input_times('nominal', seed + 500000, 200), stats=STATS_VERSION,
                trace=False, reset_events=[], allow_zero=True)
            key = digest(request)
            receipts.append(dict(status='success', request=request, data_key=key,
                storage_group_key='cohort-reports', dps=score, samples=127, variance=0.,
                requested_iterations=128))
            report = _fast_report(character, score, 127)
            report['sim']['targets'] *= target_count
            reports.append(dict(batch_key=key, condition_key=state['condition'],
                candidate_key=canonical['identity'], purpose='nominal',
                program_identity=json.dumps(canonical['form'], ensure_ascii=False, sort_keys=True,
                    separators=(',', ':')), seed=seed, input_seed=seed + 500000,
                iterations=128, requested_iterations=128, batch_index=index, scenario='nominal',
                stats_version=STATS_VERSION, times=request['times'], trace=False,
                dps=score, samples=127, variance=0., report=report))
        finalists.append(dict(key=canonical['identity'], program=program, score=score,
                              samples=381, batches=receipts))
    winner = finalists[1]  # 已知示例：200胜过100，不复刻生产排序。
    binding = dict(condition=state['condition'], input_effective_sha256=state['input_effective_sha256'],
        class_name=character.class_name, spec=character.spec, spec_id=252, target_count=target_count)
    record = dict(contract_version=2, version=1, binding=binding, condition_key=digest(binding),
        source_run_id=source_run_id, source_condition_key=state['condition'],
        source_candidate_key='source-artifact', source_candidate_data_key='source-artifact-data',
        behavior_identity=winner['key'], program=winner['program'], score=200., samples=381,
        batch_keys=[receipt['data_key'] for row in finalists for receipt in row['batches']],
        promotion_evidence=[], evaluation=dict(search=contract, engines=state['engines'],
            complete_generations=2, stagnant=2, finalists=finalists,
            finalist_keys=[row['key'] for row in finalists]))
    run = dict(run_id=source_run_id, status='completed', profile=dict(
        input_effective_sha256='frozen-character', identity=dict(
            **{'class': character.class_name}, spec=character.spec, spec_id=252)),
        condition_key=state['condition'], selected_candidate_key=winner['key'],
        locked_candidate_key=winner['key'], candidate_key='source-artifact',
        candidate_data_key='source-artifact-data', search_dps=200., search_samples=381,
        batch_keys=list(record['batch_keys']), final_scenarios=dict(nominal=dict(finalists=deepcopy(finalists))))
    from program import canonicalize_search_program
    candidate = dict(run_id=source_run_id, candidate_key='source-artifact',
        candidate_data_key='source-artifact-data', source='search', simulation='passed_native_model',
        program=canonicalize_search_program(winner['program'], state['capabilities'])['program'],
        export_text='external compiled export')
    return record, state, character, run, candidate, reports


def formal_publication_inputs(**options):
    """完整显式正式证据适配生产发布入口，不构造检查点或模拟数据库。"""
    from program import _search_blocks, _search_clicks, _with_compiled_program
    from search import digest

    record, state, character, run, candidate, reports = formal_cohort(**options)
    for finalist in record['evaluation']['finalists']:
        for receipt in finalist['batches']:
            receipt['storage_group_key'] = run['run_id'] + '-reports'
    run['final_scenarios']['nominal']['finalists'] = deepcopy(record['evaluation']['finalists'])
    mapped = candidate['program']
    blocks = _search_blocks(mapped)
    clicks = _search_clicks(dict(blocks=blocks), mapped)
    compiled = _with_compiled_program(dict(blocks=blocks, compiled_steps=list(range(len(clicks))),
        mapped_blocks=[row.get('commands', []) for row in clicks], text=candidate['export_text'],
        identity=candidate['candidate_key'], simulation='passed_native_model'), mapped, clicks)
    data_key = digest(dict(run_id=run['run_id'], candidate_key=candidate['candidate_key']))
    record['source_candidate_data_key'] = run['candidate_data_key'] = candidate['candidate_data_key'] = data_key
    winner = deepcopy(record['evaluation']['finalists'][1])
    winner['candidate'] = compiled
    state.update(run_id=run['run_id'], native=dict(identity=dict(spec_id=252, race=character.race)),
        formal_search=record['evaluation']['search'], formal_winner=winner,
        formal_finalists=deepcopy(record['evaluation']['finalists']),
        ga=dict(generation=2, stagnant=2, finalists=record['evaluation']['finalist_keys']),
        locked_candidate_key=winner['key'], selected_candidate_key=winner['key'])
    return record, state, character, run, candidate, reports


def legacy_formal_inputs():
    """明确旧v1 run/candidate/原search请求报告；不借用v2评价契约。"""
    from test_character_export import sample_profile
    from test_search import _fast_capabilities, _fast_report
    from task import parse_character
    from program import canonicalize_search_program
    from search import config_for, digest, input_times, STATS_VERSION
    from simulation_config import config_for as simulation_config_for

    character = replace(parse_character(sample_profile()), spec_id=252)
    config = config_for(dict(candidate_limit=1, batch_targets=(2,), iterations=2,
        validation_batches=1, final_batches=1, final_iterations=2,
        scenarios=('nominal',), input_interval_ms=200), legacy=True)
    state = dict(condition='current-condition', config=config_for(dict(iterations=2, input_interval_ms=200)),
        input_effective_sha256='same-character',
        engines=dict(baseline='same-base', controlled='same-controlled'),
        simulation_config=simulation_config_for(dict(target_count=1, scene='single_target')),
        capabilities=_fast_capabilities())
    runs, candidates, reports = [], [], []
    for run_id, program, score, targets in [
            ('a' * 32, [['outbreak'], ['death_coil']], 200., 1),
            ('b' * 32, [['outbreak'], ['scourge_strike']], 300., 1),
            ('c' * 32, [['outbreak'], ['scourge_strike']], 300., 5)]:
        canonical = canonicalize_search_program(program, state['capabilities'])
        seed = config['random_seed']
        times = input_times('nominal', seed + 500000, 200)
        condition = 'old-v1-' + run_id
        request = dict(condition=condition, program=canonical['form'], behavior_identity=canonical['identity'],
            purpose='search', seed=seed, input_seed=seed + 500000, iterations=2,
            times=times, stats=STATS_VERSION, trace=False, reset_events=[])
        key = digest(request)
        report = _fast_report(character, score, 1)
        report['sim']['targets'] *= targets
        reports.append(dict(batch_key=key, condition_key=condition, candidate_key=canonical['identity'],
            program_identity=json.dumps(canonical['form'], ensure_ascii=False, sort_keys=True, separators=(',', ':')),
            purpose='search', seed=seed, input_seed=seed + 500000, batch_index=0, scenario='nominal',
            stats_version=STATS_VERSION, times=times, trace=False, iterations=2, requested_iterations=2,
            dps=score, samples=1, variance=0., report=report))
        candidates.append(dict(run_id=run_id, candidate_key='artifact-' + run_id,
            candidate_data_key='data-' + run_id, program=canonical['program'],
            simulation='passed_native_model', export_text='explicit v1 export', source='search'))
        runs.append(dict(run_id=run_id, status='completed', profile=dict(input_effective_sha256='same-character',
            identity=dict(**{'class': character.class_name}, spec=character.spec, spec_id=252)),
            config=deepcopy(config), simulation_config=simulation_config_for(dict(target_count=targets,
                scene='single_target' if targets == 1 else 'aoe')), engines=deepcopy(state['engines']), burst=None,
            condition_key=condition, candidate_key='artifact-' + run_id, candidate_data_key='data-' + run_id,
            selected_candidate_key=canonical['identity'], locked_candidate_key=canonical['identity'],
            search_dps=score, search_samples=1, batch_keys=[key]))
    return state, character, runs, candidates, reports


def training_history(monkeypatch, programs, *, legacy_search=False, source_engines=None, report_engines=None):
    """明确三份原复测与真实SQLite内存快照；只替换文件/中心读取边界。"""
    import sqlite3
    import stat
    from pathlib import Path
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    from urllib.request import url2pathname
    import result_store
    import seed_training
    from legacy_training_fixture import _minimal_rule_pack
    from legacy_training_rules import validate, bind
    from program import canonicalize_search_program
    from search import digest, STATS_VERSION
    from test_character_export import sample_profile
    from test_engine import static_snapshot
    from test_search import _fast_capabilities, _fast_report

    batch = Path(__file__).resolve().parents[2] / '.local' / 'champion-input' / 'known-batch'
    text = sample_profile()
    files = {batch / 'standard.simc': text}
    snapshots, checkpoints, reports, rows = {}, [], {}, []
    source_engines = source_engines or dict(baseline=dict(revision='previous'), controlled=dict(revision='previous'))
    read_text, glob, path_stat, connect = Path.read_text, Path.glob, Path.stat, sqlite3.connect

    def read_input(path, *args, **kwargs):
        if path in files:
            return files[path]
        return read_text(path, *args, **kwargs)

    def known_checkpoints(path, pattern):
        if path == batch and pattern == '*/task.sqlite3':
            return iter(checkpoints)
        return glob(path, pattern)

    def checkpoint_stat(path, *args, **kwargs):
        if path in snapshots:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_size=len(snapshots[path]))
        return path_stat(path, *args, **kwargs)

    def open_snapshot(database, *args, **kwargs):
        if isinstance(database, str) and database.startswith('file:'):
            path = Path(url2pathname(urlsplit(database).path))
            if path in snapshots:
                database = connect(':memory:')
                database.executescript(snapshots[path])
                return database
        raise AssertionError('冠军规则测试不能打开未知数据库: ' + str(database))

    monkeypatch.setattr(Path, 'read_text', read_input)
    monkeypatch.setattr(Path, 'glob', known_checkpoints)
    monkeypatch.setattr(Path, 'stat', checkpoint_stat)
    monkeypatch.setattr(sqlite3, 'connect', open_snapshot)
    pack = _minimal_rule_pack()
    rule_snapshot = dict(pack=pack, resolved=validate(pack), rule_config_digest=digest(pack))
    # 原模板读取、配置、角色、身份与报告核验都执行生产实现。
    inputs = seed_training._training_inputs(batch / 'standard.simc', 1,
        verified_engines=source_engines, rule_snapshot=rule_snapshot)
    capabilities = _fast_capabilities()
    key = bind(capabilities, static_snapshot(), 1, spec_id=252,
        scene='single_target', rule_snapshot=rule_snapshot)['configuration_key']
    versions = seed_training.semantic_versions()
    if legacy_search:
        versions['search'] = 'rule-single-step-coba-linucb-v1'
        for name in ('rule_initialization_enabled', 'adaptive_selector_enabled', 'search_timeline'):
            inputs['config'].pop(name, None)
    payload = seed_training.training_condition_input(inputs['template_sha'], source_engines,
        inputs['config'], inputs['simulation_config'], rule_snapshot=rule_snapshot)
    condition = seed_training.semantic_condition(payload, versions)
    manifest = dict(format=1, condition=condition, condition_input=payload,
        rule_snapshot=rule_snapshot, input_sha256=digest(payload), semantic_versions=versions,
        semantic_condition=condition, executions=[])
    files[batch / 'identity.json'] = json.dumps(manifest)
    files[batch / 'condition.txt'] = condition
    states, receipts = {}, {}
    for ordinal, (program, scores) in enumerate(programs):
        candidate_id = f'{ordinal + 1:012d}' + '0' * 52
        folder = batch / candidate_id[:12]
        checkpoint = folder / 'task.sqlite3'
        checkpoints.append(checkpoint)
        state = dict(training_candidate_id=candidate_id, training_condition=condition,
            config=inputs['config'], capabilities=capabilities,
            rule_initialization=dict(configuration_key=key, static_snapshot=static_snapshot()))
        states[candidate_id] = state
        form = canonicalize_search_program(program, capabilities)['form']
        candidate_receipts = {}
        for index, (seed, score) in enumerate(zip(seed_training.RETEST_SEEDS, scores)):
            data_key = digest(dict(folder=str(folder / 'retest-final'), seed=seed))
            request = dict(condition=condition, program=form, behavior_identity=digest(form),
                purpose='seed_retest', seed=seed, input_seed=seed, iterations=128,
                times=list(range(0, 180000, inputs['config']['input_interval_ms'])),
                stats=STATS_VERSION, trace=False, reset_events=[])
            receipt = dict(status='success', request=request, data_key=data_key,
                storage_group_key='original-reports', requested_iterations=128,
                dps=score, samples=127, variance=0.)
            candidate_receipts[data_key] = receipt
            report = _fast_report(inputs['character'], score, 127)
            report['sim']['players'][0]['sim2gse_static_snapshot'] = static_snapshot()
            reports[data_key] = dict(batch_key=data_key, condition_key=condition,
                candidate_key=digest(form), purpose='seed_retest',
                program_identity=json.dumps(form, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                seed=seed, input_seed=seed, iterations=128, requested_iterations=128,
                batch_index=index, scenario='nominal', stats_version=STATS_VERSION,
                times=request['times'], trace=False, dps=score, samples=127, variance=0.,
                engines=report_engines if report_engines is not None else source_engines, report=report)
        receipts[candidate_id] = candidate_receipts
        rows.append(dict(configuration_key=key, candidate_id=candidate_id, condition=condition,
            status='completed', program=program, scores=scores, task_path=str(folder)))

    def refresh():
        files[batch / 'identity.json'] = json.dumps(manifest)
        for row in rows:
            candidate_id = row['candidate_id']
            with connect(':memory:') as database:
                database.execute('CREATE TABLE state (id INTEGER PRIMARY KEY,value TEXT NOT NULL)')
                database.execute('INSERT INTO state VALUES (1,?)', (json.dumps(states[candidate_id]),))
                database.execute('CREATE TABLE runtime_progress (id INTEGER PRIMARY KEY,elapsed REAL)')
                database.execute('CREATE TABLE batches (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                database.executemany('INSERT INTO batches VALUES (?,?)',
                    [(name, json.dumps(value)) for name, value in receipts[candidate_id].items()])
                database.commit()
                snapshots[Path(row['task_path']) / 'task.sqlite3'] = '\n'.join(database.iterdump())

    refresh()
    monkeypatch.setattr(result_store, 'read_records', lambda *args, **kwargs: rows)
    monkeypatch.setattr(result_store, 'one', lambda table, field, value, **kwargs: reports.get(value))
    return dict(rows=rows, manifest=manifest, files=files, inputs=inputs, states=states,
        receipts=receipts, reports=reports, refresh=refresh, configuration_key=key)


def read_training_history(history):
    import seed_training
    return seed_training.training_champion('deathknight', 'unholy',
        history['inputs']['simulation_config'], engines=dict(baseline='current', controlled='current'),
        input_interval_ms=200, configuration_key=history['configuration_key'])
