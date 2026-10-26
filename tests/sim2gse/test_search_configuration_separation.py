"""公开入口的正式配置、训练隔离与冻结成果兼容。"""
import pytest


def test_public_search_validates_formal_algorithm_before_profile_io():
    from task import run_task
    with pytest.raises(ValueError, match='top_k'):
        run_task('/absent/role.simc', '/absent/task', search_config=dict(top_k=3))


from test_population_training import memory_ga


def test_formal_run_uses_five_workers_and_eight_stagnant_generations(memory_ga):
    import threading
    from itertools import permutations
    barrier = threading.Barrier(5, timeout=3)
    lock = threading.Lock()
    active = peak = 0
    def score(candidate, options):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            if options['iterations'] == 32:
                # First complete worker wave must be able to start all five.
                if peak < 5:
                    barrier.wait()
                elif barrier.n_waiting:
                    barrier.wait()
            return 100.
        finally:
            with lock:
                active -= 1
    starts = [[[name] for name in order] for order in permutations(('outbreak', 'death_coil', 'scourge_strike'))]
    case = memory_ga(formal=True, programs=starts, score_for=score,
        search_settings=dict(max_processes=5, crossover_probability=0., mutation_probability=0.))
    result = case.run()
    assert result['status'] == 'completed'
    assert peak == 5
    assert result['search']['complete_generations'] == 8
    assert result['search']['formal_search']['version'] == 2


@pytest.mark.parametrize('file_values, overrides, expected', [
    ('', {}, (128, 20260912)),
    ("""[search]
max_processes=4
coarse_iterations=24
retest_batches=2
retest_iterations=96
stagnation_generations=6
top_k=4
tournament_size=2
crossover_probability=0.3
mutation_probability=0.4
iterations=141
random_seed=567
search_timeline=false
diagnostic_logging=false
diagnostics='summary'
search_observability='full'
input_interval_ms=200
reset_events=[]
""", {}, (141, 567)),
    ('[search]\niterations=141\nrandom_seed=567\nsearch_timeline=true',
     dict(iterations=128, random_seed=20260912, search_timeline=False), (128, 20260912)),
])
def test_public_run_dispatches_reference_with_runtime_file_default_priority(monkeypatch, file_values, overrides, expected):
    from pathlib import Path
    import os
    import sqlite3
    import codec
    import simulation_config
    import engine
    import result_store
    import search
    from task import run_task
    from test_character_export import sample_profile
    from test_search import _fast_identity
    files = {'/memory/role.simc': sample_profile().encode(), str(codec.LUA): b'fixed compiler identity'}
    # The suite's default document isolation is intentionally replaced with an explicit in-memory TOML source.
    from io import StringIO
    document_loader = simulation_config._load_document
    monkeypatch.setattr(simulation_config, '_load_document', lambda path=None: document_loader(StringIO(file_values)))
    read_bytes, read_text = Path.read_bytes, Path.read_text
    is_file, exists = Path.is_file, Path.exists
    def in_memory(path): return str(path).startswith('/memory/')
    monkeypatch.setattr(Path, 'read_bytes', lambda p: files[str(p)] if str(p) in files else read_bytes(p))
    monkeypatch.setattr(Path, 'read_text', lambda p, **kw: files[str(p)].decode() if in_memory(p) else read_text(p, **kw))
    monkeypatch.setattr(Path, 'write_bytes', lambda p, value: files.__setitem__(str(p), value))
    monkeypatch.setattr(Path, 'write_text', lambda p, value, **kw: files.__setitem__(str(p), value.encode()))
    monkeypatch.setattr(Path, 'is_file', lambda p: str(p) in files if in_memory(p) else is_file(p))
    monkeypatch.setattr(Path, 'exists', lambda p: str(p) in files if in_memory(p) else exists(p))
    monkeypatch.setattr(Path, 'mkdir', lambda *a, **kw: None)
    monkeypatch.setattr(os, 'replace', lambda src, dst: files.__setitem__(str(dst), files.pop(str(src))))
    store_type = search.TaskStore
    monkeypatch.setattr(search, 'TaskStore', lambda destination: store_type(destination,
        connection=sqlite3.connect(':memory:', check_same_thread=False), reusable_database=':memory:', report_locations={}))
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(engine, 'identity', _fast_identity)
    monkeypatch.setattr(engine, 'discard_diagnostic_files', lambda *a: None)
    class ReachedNativeBoundary(BaseException): pass
    requests = []
    def reference(*args, **options):
        requests.append((options['iterations'], options['seed']))
        raise ReachedNativeBoundary
    monkeypatch.setattr(engine, 'reference', reference)
    with pytest.raises(ReachedNativeBoundary):
        run_task('/memory/role.simc', '/memory/task', _lease=True, search_config=overrides)
    assert requests == [expected]


@pytest.mark.parametrize('reset_events', [(), ((300, 'shift'),)])
def test_public_result_reads_frozen_v1_without_current_defaults(monkeypatch, reset_events):
    from pathlib import Path
    from copy import deepcopy
    import json
    import result_store
    import search
    from task import read_task
    # Literal historical contract: deliberately independent of contract_for/new defaults.
    ga = dict(max_processes=2, coarse_iterations=32, retest_batches=3, retest_iterations=128,
        stagnation_generations=2, top_k=8, tournament_size=3,
        crossover_probability=.8, mutation_probability=.8)
    from population_training import _stage_plan
    frozen = dict(version=1, algorithm='formal-ga-easimple-v1',
        stop_policy=dict(version=1, kind='natural_stagnation'), config=ga,
        coarse_failure_policy=dict(version=1, initial='exclude_invalid_score', offspring='retain_verified_slot'),
        stage_plan=_stage_plan(ga, 20260912, scenarios=('nominal',)))
    saved = dict.fromkeys(result_store.RUN_SCHEMA)
    saved.update(status='completed', phase='done', config=dict(search.TRAINING_SEARCH_DEFAULTS, reset_events=reset_events),
        search_metrics=dict(formal_search=frozen), batch_keys=[], search_rounds=2)
    monkeypatch.setattr(Path, 'is_file', lambda p: p.name == 'result.json')
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: json.dumps(dict(run_id='old-run')))
    monkeypatch.setattr(result_store, 'one', lambda *a, **kw: deepcopy(saved))
    monkeypatch.setitem(search.DEFAULT_CONFIG, 'stagnation_generations', 99)
    result = read_task('/memory/old-run')
    assert result['status'] == 'completed'
    assert result['search']['formal_search'] == frozen


def test_training_file_projection_keeps_only_preexisting_timeline_setting():
    from io import StringIO
    from simulation_config import load_training_search_config, load_training_config
    values = load_training_search_config(StringIO('''[search]
iterations=128
max_processes=5
stagnation_generations=8
random_seed=17
input_interval_ms=200
reset_events=[[400, 'target']]
diagnostic_logging=true
diagnostics='full'
search_observability='full'
search_timeline=true
'''))
    assert values == dict(iterations=100, max_processes=2, random_seed=20260912,
        input_interval_ms=300, reset_events=(), diagnostic_logging=False,
        diagnostics='off', search_observability='off', search_timeline=True)
    assert load_training_search_config(StringIO('[search]\nsearch_timeline=true'),
        search_timeline=False)['search_timeline'] is False
    with pytest.raises(ValueError, match='max_processes'):
        load_training_search_config(StringIO(''), max_processes=16)
    assert load_training_config(StringIO(''))['stagnation_generations'] == 2
