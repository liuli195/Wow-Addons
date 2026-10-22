"""Rebuilt isolated pretraining pilot. No production optimizer/score is duplicated."""
from __future__ import annotations
import argparse
import ctypes
from copy import deepcopy
from dataclasses import replace
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess  # Import before the test-only Windows lock shim.
import sys
import time
import types
import uuid

def kill_on_parent_death(parent_pid):
    # Linux-only experiment: direct child ownership survives even a SIGKILL of its parent.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'Cannot bind experiment child to parent lifetime')
    if os.getppid() != parent_pid:  # Parent may have exited between fork and prctl.
        os.kill(os.getpid(), signal.SIGKILL)

if __name__ == '__main__' and sys.argv[1:2] == ['--parent-death-exec']:
    # Already exec'd into a fresh interpreter: no Python/dlopen runs between threaded fork and exec.
    kill_on_parent_death(int(sys.argv[2]))
    os.execvp(sys.argv[3], sys.argv[3:])

def parent_bound_command(command):
    return [sys.executable, str(Path(__file__).resolve()), '--parent-death-exec',
            str(os.getpid()), *map(str, command)]

ROOT = Path(__file__).resolve().parents[3]
ENTRY = time.monotonic()
sys.path.insert(0, str(ROOT / 'projects/sim2gse'))
if sys.platform not in ('linux', 'win32'):
    raise RuntimeError('Only the approved Linux/Windows experiment boundaries are supported')
if sys.platform == 'linux':
    import fcntl
    shim = types.ModuleType('msvcrt')
    shim.LK_NBLCK, shim.LK_UNLCK = 2, 0
    def locking(fd, mode, count):
        if count != 1 or mode not in (2, 0):
            raise ValueError('Unsupported experiment lock operation')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB if mode == 2 else fcntl.LOCK_UN)
    shim.locking = locking
    sys.modules['msvcrt'] = shim
import runtime
import result_store
from search import TaskStore, config_for, digest, mutate, optimize
from program import canonicalize_search_program

POLICY = 'rebuilt-joint-pilot-v1-2elites-2rotating-originals'
ORDERS = ('AB', 'BA', 'AB', 'BA', 'BA', 'AB', 'BA', 'AB')
SOURCES = tuple(sorted(p.relative_to(ROOT).as_posix() for p in
    (ROOT / 'projects/sim2gse').rglob('*') if p.is_file() and p.suffix in ('.py', '.json', '.patch', '.cpp', '.hpp'))) + (
    'scripts/dev/sim2gse/population_ab.py',)

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.pending')
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    os.replace(temp, path)

def load_materials(path):
    data = json.loads(Path(path).read_text())
    rows = data['material_snapshot']['materials']
    condition = data['material_snapshot']['condition']
    expected = dict(specialization_id=252, target_count=5, input_interval_ms=200,
                    hero_subtree_id=32, reset_events=[])
    if any(condition.get(k) != v for k, v in expected.items()) or len(rows) != 4:
        raise ValueError('Only the approved four-material scenario is supported')
    if len({r['id'] for r in rows}) != 4:
        raise ValueError('Duplicate material identities')
    for row in rows:
        if digest(row['program']) != row['program_sha256'] or not row['source_revision']:
            raise ValueError('Material digest/revision mismatch')
    return data

def manifest_for(source):
    trials = []
    ids = [r['id'] for r in source['material_snapshot']['materials']]
    for i in range(8):
        base = 200000000 + i * 1000000
        rotation = i % 4
        trials.append(dict(index=i, order=ORDERS[i], material_ids=ids[rotation:] + ids[:rotation],
            search_seed=base, endpoint_seeds=[base + 300000 + j for j in range(4)]))
    settings = ROOT / '.local/sim2gse/config.toml'
    manifest = dict(policy=POLICY, deap_version=version('deap'),
        local_config_sha256=hashlib.sha256(settings.read_bytes()).hexdigest() if settings.exists() else None,
        reference_seed=20260912, total_seconds=4800, pair_seconds=600, arm_seconds=180,
        search_seconds=175, closeout_seconds=5, endpoint_iterations=128,
        nominal_search_indices=[0, 1, 2, 99], validation_indices=[0, 1, 2, 3],
        batch_targets=[32, 128, 256], validation_batches=4, max_processes=2,
        input_seed_offset=500000, training_final='not_requested',
        material_digest=digest(source), sources={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                                               for p in SOURCES}, trials=trials)
    validate_manifest(manifest, source)
    return manifest

def validate_manifest(manifest, source):
    if manifest['policy'] != POLICY or len(manifest['trials']) != 8:
        raise ValueError('Pilot identity/slot count mismatch')
    ids = [r['id'] for r in source['material_snapshot']['materials']]
    all_seeds = set()
    for i, trial in enumerate(manifest['trials']):
        base = 200000000 + i * 1000000
        expected_ids = ids[i % 4:] + ids[:i % 4]
        if (trial['index'] != i or trial['order'] != ORDERS[i]
                or trial['search_seed'] != base or trial['material_ids'] != expected_ids
                or trial['endpoint_seeds'] != [base + 300000 + j for j in range(4)]):
            raise ValueError('Pre-registered seed/order/material plan changed')
        search = {base + j for j in (0, 1, 2, 99)} | {base + 100000 + j for j in range(4)}
        inputs = {x + 500000 for x in search}
        endpoints = set(trial['endpoint_seeds'])
        if search & inputs or (search | inputs) & endpoints:
            raise ValueError('Search/input/endpoint seed collision')
        current = search | inputs | endpoints
        if current & all_seeds:
            raise ValueError('Cross-trial seed collision')
        all_seeds |= current
    if manifest['material_digest'] != digest(source):
        raise ValueError('Frozen materials changed')
    settings = ROOT / '.local/sim2gse/config.toml'
    settings_sha = hashlib.sha256(settings.read_bytes()).hexdigest() if settings.exists() else None
    if (manifest.get('deap_version') != '1.4.4' or version('deap') != '1.4.4'
            or manifest.get('local_config_sha256') != settings_sha):
        raise ValueError('Frozen dependencies/local configuration changed')
    if set(manifest['sources']) != set(SOURCES):
        raise ValueError('Missing frozen source identities')
    for name, sha in manifest['sources'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen source changed')
    fixed = dict(reference_seed=20260912, total_seconds=4800, pair_seconds=600, arm_seconds=180, search_seconds=175,
        closeout_seconds=5, endpoint_iterations=128, nominal_search_indices=[0, 1, 2, 99],
        validation_indices=[0, 1, 2, 3], batch_targets=[32, 128, 256], validation_batches=4,
        max_processes=2, input_seed_offset=500000, training_final='not_requested')
    if any(manifest.get(k) != v for k, v in fixed.items()):
        raise ValueError('Frozen configuration changed')

class JointPopulation:
    def __init__(self, materials, capabilities, identity):
        from deap import algorithms, base, tools
        self.algorithms, self.base, self.tools = algorithms, base, tools
        self.materials, self.capabilities, self.identity = materials, capabilities, identity
        self.original = {canonicalize_search_program(r['program'], capabilities)['identity']: r['id']
                         for r in materials}

    def __call__(self, *, archive, seen, rng, feedback_for, state):
        class Fitness(self.base.Fitness): weights = (1.0,)
        class Individual(list): pass
        rows = {r['key']: r for r in archive}
        ranked = []
        for key, row in rows.items():
            batch = row['batches'][0]
            if batch['requested_iterations'] != 32 or batch['samples'] < 2 or not math.isfinite(batch['dps']):
                raise ValueError('Breeding requires reliable first-32 scores')
            member = Individual(deepcopy(row['program']))
            member.fitness = Fitness((batch['dps'],))
            member.key = key
            member.lineage = row.get('training_lineage') or [self.original[key]]
            member.parents, member.crossed = [key], False
            ranked.append(member)
        ranked = self.tools.selBest(ranked, len(ranked))
        selected = ranked[:2]
        generation = state.get('generation', 0)
        keys = list(self.original)
        reserved = [keys[generation % 4], keys[(generation + 1) % 4]]
        for key in reserved:
            if all(m.key != key for m in selected):
                selected.append(next(m for m in ranked if m.key == key))
        for member in ranked:
            if len(selected) >= 8: break
            if all(m.key != member.key for m in selected): selected.append(member)
        state.update(pool=[m.key for m in selected], reserved_originals=reserved)
        state.setdefault('proposals', [])
        feedbacks = {}
        toolbox = self.base.Toolbox()
        def mate(a, b):
            parents, lineage = sorted(set(a.parents + b.parents)), sorted(set(a.lineage + b.lineage))
            if crossover_blocks(a, b, rng):
                for child in (a, b): child.parents, child.lineage, child.crossed = parents, lineage, True
            return a, b
        def mutation(member):
            feedback = None
            if not member.crossed:
                key = member.parents[0]
                if key not in feedbacks: feedbacks[key] = feedback_for(rows[key])
                feedback = feedbacks[key]
            member[:] = mutate(member, self.capabilities, rng, feedback=feedback)
            return member,
        toolbox.register('mate', mate)
        toolbox.register('mutate', mutation)
        result, unique = [], set(seen)
        old_random = self.algorithms.random
        self.algorithms.random = rng
        try:
            for _ in range(20):
                parents = list(selected)
                rng.shuffle(parents)
                if len(parents) % 2: parents.append(parents[0])
                for child in self.algorithms.varAnd(parents, toolbox, cxpb=.8, mutpb=.8):
                    try: canonical = canonicalize_search_program(child, self.capabilities)
                    except ValueError:
                        state['invalid'] = state.get('invalid', 0) + 1
                        continue
                    key = canonical['identity']
                    if key in unique:
                        state['duplicates'] = state.get('duplicates', 0) + 1
                        continue
                    unique.add(key)
                    row = dict(key=key, program=deepcopy(list(child)), lineage=sorted(set(child.lineage)),
                               parents=child.parents, crossed=child.crossed, generation=generation + 1)
                    result.append(row)
                    state['proposals'].append({k: v for k, v in row.items() if k != 'program'})
                    if len(result) == 16: break
                if len(result) == 16: break
        finally: self.algorithms.random = old_random
        state['generation'] = generation + 1
        return result

def crossover_blocks(left, right, rng):
    def blocks(member):
        if len(member) == 1 and isinstance(member[0], dict) and member[0].get('kind') == 'Loop':
            return member[0]['blocks']
        return member
    a, b = blocks(left), blocks(right)
    if min(len(a), len(b)) < 2: return False
    cut = rng.randint(1, min(len(a), len(b)) - 1)
    if a[cut:] == b[cut:]: return False
    a[cut:], b[cut:] = deepcopy(b[cut:]), deepcopy(a[cut:])
    return True

class CloudProcess:
    def __init__(self, command, cwd, folder):
        token = uuid.uuid4().hex
        self.stdout_path, self.stderr_path = (folder / f'cloud-{token}.out', folder / f'cloud-{token}.err')
        self.out, self.err = self.stdout_path.open('wb'), self.stderr_path.open('wb')
        try:
            # Inherit the worker process group: pilot deadline kills worker AND all native children.
            self.process = subprocess.Popen(parent_bound_command(command), cwd=cwd, stdin=subprocess.DEVNULL,
                                            stdout=self.out, stderr=self.err)
        except BaseException:
            self.out.close(); self.err.close(); raise
    def poll(self): return self.process.poll()
    def wait(self, timeout_seconds):
        try: return self.process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as e: raise runtime.ProcessTimeout('Native process deadline') from e
    def terminate(self):
        if self.process.poll() is None: self.process.kill()
    def close(self):
        self.out.close(); self.err.close()

class ExperimentRuntime(runtime.TaskRuntime):
    def __init__(self, seconds, deadline):
        super().__init__(seconds)
        self.deadline = min(self.started + seconds, deadline)
    @property
    def remaining_seconds(self):
        return max(0, min(super().remaining_seconds, self.deadline - time.monotonic()))

class ExperimentStore(TaskStore):
    def save(self, *args, **kwargs):
        best = self.state.get('best')
        record = next((r for r in self.state.get('archive', []) if r['key'] == best), None)
        if record is not None:
            samples = sum(b['samples'] for b in record['batches'])
            curve = self.state.setdefault('experiment_curve', [])
            if not curve or (best, record['score'], samples) != (curve[-1]['key'], curve[-1]['dps'], curve[-1]['samples']):
                curve.append(dict(key=best, dps=record['score'], samples=samples,
                                  elapsed=time.monotonic() - self.experiment_origin))
        return super().save(*args, **kwargs)

def isolate_center(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / '.local/population-mvp') or result_store._BOUND_PROJECT is not None:
        raise ValueError('Refusing production-bound/outside experiment center')
    result_store.DATA_ROOT = path / 'data'
    result_store._REPORT_LOCATIONS = None
    result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    result_store.ensure_available()
    return path

def prepare_burst_source(source, output):
    from burst import validate, definition_id, publish
    isolate_center(output / 'prepare')
    definition = json.loads((ROOT / 'projects/sim2gse/burst/unholy.json').read_text())
    validate(definition)
    if definition_id(definition) != source['material_snapshot']['condition']['burst_definition_id']:
        raise ValueError('Reviewed burst source differs from frozen material identity')
    return publish(definition)

def native_score(profile, program, folder, context, run, seed, iterations):
    from program import from_search_program, compile_program
    from sequence import evaluate
    from burst import combined_inputs
    compiled = compile_program(from_search_program(program, context['capabilities']), folder / 'export',
        identity=context['native']['identity'], runtime=run, capabilities=context['capabilities'])
    times, sources = combined_inputs(list(range(0, 180000, 200)), context['burst'], 200)
    return evaluate(profile, compiled, folder, character=context['character'], iterations=iterations,
        seed=seed, trace=False, input_times=times, input_sources=sources,
        burst_candidate=context['burst']['candidate'], reset_events=list(context['config']['reset_events']),
        simulation_config=context['simulation_config'], runtime=run)

def usable_winner(state):
    row = next((r for r in state.get('archive', []) if r['key'] == state.get('best')), None)
    if (row is None or not math.isfinite(row.get('score', float('nan'))) or not row.get('batches')
            or any(b.get('samples', 0) < 2 or not math.isfinite(b.get('dps', float('nan')))
                   for b in row['batches'])):
        return None
    return deepcopy(row)

def run_route(name, rows, profile, context, output, global_deadline, identity):
    start = time.monotonic()  # Include center setup, task opening and final reliable save.
    deadline = min(start + 180, global_deadline)
    search_deadline = deadline - 5
    route = isolate_center(output / name)
    paths, winners = [], []
    for i, selected in enumerate([[r] for r in rows] if name == 'A' else [rows]):
        detail = dict(material_ids=[r['id'] for r in selected], coverage=False, winner=None)
        paths.append(detail)
        if time.monotonic() >= search_deadline:
            detail['error'] = 'search deadline before path start'
            continue
        store = None
        try:
            folder = route / 'tasks' / str(i)
            folder.mkdir(parents=True, exist_ok=True)
            store = ExperimentStore(folder)
            store.experiment_origin = start
            store.state.update(run_id=uuid.uuid4().hex, starts=[deepcopy(r['program']) for r in selected],
                config=context['config'], capabilities=context['capabilities'], burst=context['burst'])
            run = ExperimentRuntime(175 / 4 if name == 'A' else 175, search_deadline)
            supplier = JointPopulation(rows, context['capabilities'], identity) if name == 'B' else None
            with store.active(run):
                optimize(profile=profile, character=context['character'], capabilities=context['capabilities'],
                    reference=context['native'], destination=folder, runtime=run, config=context['config'],
                    condition_key=digest(dict(experiment=identity, route=name)), store=store,
                    simulation_config=context['simulation_config'], training=True,
                    training_candidate_supplier=supplier)
        except Exception as e:
            detail['error'] = f'{type(e).__name__}: {e}'
        finally:
            if store is not None:
                state = deepcopy(store.state)
                detail['state'] = state
                detail['winner'] = usable_winner(state)
                if name == 'A': detail['coverage'] = len(state.get('archive', [])) >= 2
                else:
                    scored = {r['key'] for r in state.get('archive', [])}
                    proposals = state.get('training_candidate_supplier', {}).get('state', {}).get('proposals', [])
                    detail['coverage'] = state.get('rounds', 0) >= 2 and any(
                        p['key'] in scored and p['crossed'] and len(p['lineage']) > 1 for p in proposals)
                write(folder / 'experiment-state.json', detail)
                store.close()
        if detail['winner'] is not None: winners.append(detail['winner'])
    winner = max(winners, key=lambda r: r['batches'][0]['dps']) if winners else None
    result = dict(winner=winner, coverage=all(p['coverage'] for p in paths), paths=paths,
                  status='usable_output' if winner else 'no_usable_output')
    write(route / 'route.json', result)
    result.update(seconds=time.monotonic() - start, budget_met=time.monotonic() <= deadline)
    write(route / 'route.json', result)
    if time.monotonic() > deadline:
        result.update(budget_met=False, status='arm_deadline_exceeded')
        write(route / 'route.json', result)
    return result

def run_trial(source, output, trial, manifest, deadline):
    from concurrent.futures import ThreadPoolExecutor
    from engine import identity as engine_identity, training_template, reference, prepare_loop
    from seed_training import _training_inputs
    start = time.monotonic()
    deadline = min(deadline, start + 600)
    summary = dict(index=trial['index'], status='running', arms={}, endpoint={}, plan=trial,
                   deadline_monotonic=deadline, identity=digest(manifest))
    write(output / 'experiment.json', summary)
    if sys.platform == 'linux':
        runtime._create_process = CloudProcess
    try:
        prep = ExperimentRuntime(90, deadline)
        prepare_burst_source(source, output)
        engines = {m: engine_identity(m)[1] for m in ('baseline', 'controlled')}
        profile = training_template()
        if hashlib.sha256(profile.read_bytes()).hexdigest() != source['profile_metadata']['sha256']:
            raise ValueError('Training template differs from frozen source')
        inputs = _training_inputs(profile, 5, use_burst=True, max_processes=2, verified_engines=engines,
            search_config=dict(rule_initialization_enabled=False, adaptive_selector_enabled=False))
        condition = source['material_snapshot']['condition']
        if inputs['definition']['definition_id'] != condition['burst_definition_id']:
            raise ValueError('Selected burst identity mismatch')
        native = reference(profile, output / 'prepare/reference', inputs['character'], iterations=100,
                           seed=manifest['reference_seed'], runtime=prep, simulation_config=inputs['simulation_config'])
        character = replace(inputs['character'], spec_id=native['identity']['spec_id'], race=native['identity']['race'])
        _, caps, burst = prepare_loop(native, character, output / 'prepare', prep,
                                     definition=inputs['definition'], interval_ms=200)
        config = config_for(dict(inputs['config'], random_seed=trial['search_seed'], batch_targets=(32,128,256),
            validation_batches=4, max_processes=2, round_candidate_limit=16, reset_events=(),
            diagnostics='off', diagnostic_logging=True, search_observability='off',
            rule_initialization_enabled=False, adaptive_selector_enabled=False), training=True)
        context = dict(native=native, character=character, capabilities=caps, burst=burst,
                       config=config, simulation_config=inputs['simulation_config'])
        summary['effective_config'] = config
        by_id = {r['id']: r for r in source['material_snapshot']['materials']}
        rows = [by_id[k] for k in trial['material_ids']]
        for row in rows:
            if canonicalize_search_program(row['program'], caps)['identity'] != row['behavior_id']:
                raise ValueError('Material behavior identity changed')
        def calibrate(item):
            i, row = item
            scored = native_score(profile, row['program'], output / 'prepare' / str(i), context,
                                  prep, trial['search_seed'], 32)
            return dict(program=row['program'], dps=scored['summary']['dps'], id=row['id'])
        with ThreadPoolExecutor(max_workers=2) as pool: calibration = list(pool.map(calibrate, enumerate(rows)))
        prep.check()
        summary['prepare'] = dict(seconds=prep.elapsed_seconds, calibration=calibration,
                                  engines={m: x['identity_sha256'] for m,x in engines.items()})
        for name in trial['order']:
            if time.monotonic() >= deadline: break
            try: summary['arms'][name] = run_route(name, rows, profile, context, output, deadline, summary['identity'])
            except Exception as e: summary['arms'][name] = dict(status='failed', error=f'{type(e).__name__}: {e}', winner=None)
            write(output / 'experiment.json', summary)
        # Freeze outputs before ANY independent evaluation; these scores never select winners.
        winners = {name: deepcopy(arm['winner']) for name, arm in summary['arms'].items() if arm.get('winner')}
        winners['initial'] = max(calibration, key=lambda r:r['dps'])
        summary['fixed_winners'] = deepcopy(winners)
        write(output / 'experiment.json', summary)
        endpoint = ExperimentRuntime(150, deadline)
        for name, winner in winners.items():
            scores = []
            summary['endpoint'][name] = dict(status='incomplete', scores=scores)
            for offset in (0, 2):
                try:
                    endpoint.check()
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(native_score, profile, winner['program'],
                            output / 'endpoint' / name / str(seed), context, endpoint, seed, 128)
                            for seed in trial['endpoint_seeds'][offset:offset+2]]
                        for seed, future in zip(trial['endpoint_seeds'][offset:offset+2], futures):
                            result = future.result()['summary']
                            if result['samples'] < 2 or not math.isfinite(result['dps']) or result['dps'] <= 0:
                                raise ValueError('Unreliable independent endpoint')
                            scores.append(dict(seed=seed, dps=result['dps'], samples=result['samples']))
                except Exception as e:
                    summary['endpoint'][name]['error'] = f'{type(e).__name__}: {e}'
                    break
            if len(scores) == 4: summary['endpoint'][name]['status'] = 'complete'
            write(output / 'experiment.json', summary)
        complete = all(summary['endpoint'].get(name, {}).get('status') == 'complete'
                       and summary['arms'].get(name, {}).get('budget_met') for name in 'AB')
        summary['status'] = 'complete_pair' if complete else 'incomplete_pair'
        if complete:
            means = {name: statistics.mean(x['dps'] for x in summary['endpoint'][name]['scores']) for name in 'AB'}
            summary.update(mean_dps=means, log_ratio=math.log(means['B']/means['A']))
    except Exception as e:
        summary.update(status='failed', error=f'{type(e).__name__}: {e}')
    finally:
        summary['elapsed_seconds'] = time.monotonic() - start
        if time.monotonic() > deadline: summary['status'] = 'pair_deadline_exceeded'
        write(output / 'experiment.json', summary)
    return summary

def summarize(slots):
    logs = [s['result']['log_ratio'] for s in slots if s.get('exit_code', 0) == 0
            and s.get('result', {}).get('status') == 'complete_pair']
    return dict(planned=8, attempted=sum(s['status'] != 'not_started' for s in slots), complete_pairs=len(logs),
        conditional_log_ratio_mean=statistics.mean(logs) if logs else None,
        conditional_log_ratio_sd=statistics.stdev(logs) if len(logs)>1 else None,
        trial_statuses={str(s['index']): s.get('result', {}).get('status', s['status']) for s in slots},
        coverage_insufficient=[s['index'] for s in slots if any(
            arm.get('coverage') is False for arm in s.get('result', {}).get('arms', {}).values())],
        output_failure=[s['index'] for s in slots if s['status'] != 'not_started' and any(
            not s.get('result', {}).get('arms', {}).get(name, {}).get('winner') for name in 'AB')],
        endpoint_incomplete=[s['index'] for s in slots if s['status'] != 'not_started' and any(
            s.get('result', {}).get('endpoint', {}).get(name, {}).get('status') != 'complete' for name in 'AB')],
        scope='pilot variance/reliability only; conditional on complete outputs, not all-attempt causal benefit',
        slots=slots)

def run_pilot(source, output, manifest):
    deadline = ENTRY + 4800
    slots = [dict(index=i, status='not_started', reason='not reached before global deadline') for i in range(8)]
    write(output / 'manifest.json', manifest)
    write(output / 'summary.json', summarize(slots))
    for i in range(8):
        if time.monotonic() >= deadline - 2: break
        pair_deadline = min(deadline - 1, time.monotonic() + 599)
        folder = output / str(i)
        command = [sys.executable, str(Path(__file__).resolve()), '--materials', str(output / 'materials.json'),
                   '--output', str(folder), '--manifest', str(output / 'manifest.json'),
                   '--trial', str(i), '--deadline', str(pair_deadline)]
        slots[i] = dict(index=i, status='attempted')
        write(output / 'summary.json', summarize(slots))
        try:
            with (output / f'{i}-console.log').open('wb') as log:
                process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
                try: code = process.wait(timeout=max(0, pair_deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    code = process.wait()
                    slots[i]['error'] = 'parent hard deadline killed worker/native process group'
                finally:
                    # Ownership survives worker exit: its native children may still share this group.
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    if process.poll() is None:
                        process.wait()
        except OSError as e:
            code = -1
            slots[i]['error'] = f'Worker launch failed: {e}'
        slots[i]['exit_code'] = code
        try: slots[i]['result'] = json.loads((folder / 'experiment.json').read_text())
        except (OSError, ValueError) as e: slots[i]['error'] = f'No reliable result: {e}'
        slots[i]['status'] = 'finished' if code == 0 else 'failed'
        write(output / 'summary.json', summarize(slots))
    result = summarize(slots)
    result.update(elapsed_seconds=time.monotonic()-ENTRY, budget_met=time.monotonic()<=deadline)
    write(output / 'summary.json', result)
    return result

def self_check(source, output):
    from engine import identity, training_template
    from seed_training import _training_inputs
    manifest = manifest_for(source)
    checks = dict(manifest_valid=True, source_four_materials=len(source['material_snapshot']['materials'])==4,
                  balanced_orders=sum(t['order']=='AB' for t in manifest['trials'])==4)
    isolated = isolate_center(output / 'check')
    checks['isolated_root'] = result_store.DATA_ROOT == isolated / 'data'
    prepare_burst_source(source, output)
    engines = {name: identity(name)[1] for name in ('baseline', 'controlled')}
    inputs = _training_inputs(training_template(), 5, use_burst=True, max_processes=2,
        verified_engines=engines, search_config=dict(rule_initialization_enabled=False,
                                                    adaptive_selector_enabled=False))
    checks['real_preparation_before_native'] = (inputs['definition']['definition_id'] ==
        source['material_snapshot']['condition']['burst_definition_id'])
    checks['template_identity'] = hashlib.sha256(training_template().read_bytes()).hexdigest() == source['profile_metadata']['sha256']
    checks['eight_failure_slots'] = len(summarize([dict(index=i,status='not_started') for i in range(8)])['slots'])==8
    if not all(checks.values()):
        raise ValueError('Preflight identity/isolation checks failed')
    return dict(native_starts=0, manifest=manifest, checks=checks)

THREE_POLICY = 'three-strategy-confirmatory-v2'
THREE_ORDERS = ('ABC', 'BCA', 'CAB') * 4
THREE_ARM_SECONDS = 200
THREE_TOTAL_SECONDS = 7800
THREE_SELECTION_SECONDS = THREE_ENDPOINT_SECONDS = 45

def three_manifest_for(source, evidence_kind='real_native'):
    from engine import identity, training_template
    blocks, slots = [], []
    for index, order in enumerate(THREE_ORDERS):
        seed = 400000000 + index * 1000000
        stages = dict(search=dict(iterations=32, seeds=[seed]),
            feedback=dict(iterations=2, seeds=[seed + 99]),
            selection=dict(iterations=128, seeds=[seed + 100000 + j for j in range(2)]),
            endpoint=dict(iterations=128, seeds=[seed + 300000 + j for j in range(4)]))
        blocks.append(dict(index=index, order=order, search_seed=seed, stages=stages))
        slots.extend(dict(index=index * 3 + j, block=index, strategy=name)
                     for j, name in enumerate(order))
    settings = ROOT / '.local/sim2gse/config.toml'
    profile_sha256 = hashlib.sha256(training_template().read_bytes()).hexdigest()
    if profile_sha256 != source['profile_metadata']['sha256']:
        raise ValueError('Training template differs from frozen source')
    return dict(policy=THREE_POLICY, evidence_kind=evidence_kind, deap_version=version('deap'),
        total_seconds=THREE_TOTAL_SECONDS, arm_seconds=THREE_ARM_SECONDS, search_seconds=100,
        selection_seconds=THREE_SELECTION_SECONDS, endpoint_seconds=THREE_ENDPOINT_SECONDS, closeout_seconds=10, max_processes=2, reference_seed=20260912,
        perturbation_seeds=[202610220 + j for j in range(4)],
        input_seed_offset=500000, blocks=blocks, slots=slots, material_digest=digest(source),
        statistical_plan=dict(pairs=['A-C', 'B-C', 'A-B'], test='two-sided exact paired sign',
            ties='keep in n, no win credited', correction='Holm', alpha=.05, required_complete_arms=36),
        profile_sha256=profile_sha256,
        engines={name: identity(name)[1] for name in ('baseline', 'controlled')},
        local_config_sha256=hashlib.sha256(settings.read_bytes()).hexdigest() if settings.exists() else None,
        sources={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES})

def validate_three_manifest(manifest, source):
    plan = dict(manifest)
    prepared = plan.pop('prepared', None)
    if plan != three_manifest_for(source, manifest.get('evidence_kind')) or version('deap') != '1.4.4':
        raise ValueError('Frozen three-strategy identities/plan changed')
    if prepared is not None and (set(prepared) != {'context_sha256', 'inputs_sha256'}
            or any(not isinstance(value, str) or len(value) != 64 for value in prepared.values())):
        raise ValueError('Frozen preparation receipt is invalid')
    seeds = [seed for block in manifest['blocks'] for stage in block['stages'].values()
             for seed in stage['seeds']]
    if len(seeds) != len(set(seeds)) or set(seeds) & {seed + 500000 for seed in seeds}:
        raise ValueError('Frozen stage/input seeds collide')

def three_preflight(source, evidence_kind='real_native'):
    manifest = three_manifest_for(source, evidence_kind)
    validate_three_manifest(manifest, source)
    if manifest['profile_sha256'] != source['profile_metadata']['sha256']:
        raise ValueError('Training template differs from frozen source')
    return dict(native_starts=0, manifest=manifest, input_freeze='pending_real_preparation',
        scope='Identity/structure only; eight legal distinct inputs freeze after real common preparation')

def freeze_three_inputs(source, capabilities, manifest):
    rows, seen = [], set()
    originals = source['material_snapshot']['materials']
    for material in originals:
        program = deepcopy(material['program'])
        key = canonicalize_search_program(program, capabilities)['identity']
        if key != material['behavior_id'] or key in seen:
            raise ValueError('Original material legality/behavior changed')
        seen.add(key)
        rows.append(dict(id=material['id'], key=key, program=program,
                         lineage=[material['id']], original=True))
    for material, seed in zip(originals, manifest['perturbation_seeds']):
        program = deepcopy(material['program'])
        # Exactly one fixed-seed light edit, never DPS-selected or retried to fill slots.
        position = random.Random(seed).randrange(len(program))
        program.insert(position + 1, deepcopy(program[position]))
        key = canonicalize_search_program(program, capabilities)['identity']
        if key in seen:
            raise ValueError('Single fixed perturbation is not a new legal behavior')
        seen.add(key)
        rows.append(dict(id='derived:' + material['id'], key=key, program=program,
            lineage=[material['id']], original=False, perturbation=dict(seed=seed,
                operation='duplicate_one_block', position=position)))
    return dict(rows=rows, digest=digest(rows), capabilities_sha256=digest(capabilities),
                evidence_kind=manifest['evidence_kind'])

def prepare_three(source, output, manifest, deadline):
    from engine import training_template, reference, prepare_loop
    from seed_training import _training_inputs
    from program import compile_program
    run = ExperimentRuntime(THREE_TOTAL_SECONDS, deadline)
    prepare_burst_source(source, output)
    profile = training_template()
    inputs = _training_inputs(profile, 5, use_burst=True, max_processes=2,
        verified_engines=manifest['engines'], search_config=dict(rule_initialization_enabled=False,
                                                               adaptive_selector_enabled=False))
    native = reference(profile, output / 'prepare/reference', inputs['character'], iterations=100,
        seed=manifest['reference_seed'], runtime=run, simulation_config=inputs['simulation_config'])
    character = replace(inputs['character'], spec_id=native['identity']['spec_id'], race=native['identity']['race'])
    _, caps, burst = prepare_loop(native, character, output / 'prepare', run,
        definition=inputs['definition'], interval_ms=200)
    if (native['identity']['spec_id'] != 252
            or inputs['definition']['definition_id'] != source['material_snapshot']['condition']['burst_definition_id']):
        raise ValueError('Real preparation condition differs from frozen source')
    frozen = freeze_three_inputs(source, caps, manifest)
    for row in frozen['rows']:
        run.check()
        canonical = canonicalize_search_program(row['program'], caps)
        compile_program(canonical['program'], output / 'prepare/initial-exports' / row['key'],
            identity=native['identity'], runtime=run, capabilities=caps)
    run.check()
    context = dict(native=native, capabilities=caps, burst=burst,
        simulation_config=inputs['simulation_config'], inputs_digest=frozen['digest'])
    write(output / 'context.json', context)
    write(output / 'inputs.json', frozen)  # Freeze all eight before ANY arm score.
    return frozen

def three_evolution(name, rows, capabilities, store, run, block, deadline):
    from deap import algorithms, base, tools
    from engine import CandidateError
    class Fitness(base.Fitness):
        weights = (1.0,)
    class Individual(list):
        pass
    state = store.state
    report = dict(strategy=name, evidence_kind=state['evidence_kind'], complete_generations=0,
        partial_generation=False, generations=[], population_slots=[], search_scores=[],
        selection=[], winner=None, endpoint=[], errors=[], search_curve=[], search_cache_hits=0,
        worker_pid=os.getpid(), cache_root=str(result_store.DATA_ROOT), search_seed=block['search_seed'],
        random_source='one worker-local Python random source for selection/variation/mutation',
        curve_scope='first-32 search proxy, not independent DPS', status='running')
    state['three_strategy'] = report
    original = [row for row in rows if row['original']]
    lineage = {row['key']: row['lineage'] for row in rows}
    toolbox = base.Toolbox()
    def clone(member):
        child = deepcopy(member)
        # Clone ancestry is this generation's immediate parent, not stale crossover metadata.
        child.parents, child.crossed = [member.key], False
        child.parent_program = deepcopy(list(member))
        return child
    def mate(left, right):
        parents = sorted(set(left.parents + right.parents))
        ancestry = sorted(set(left.lineage + right.lineage))
        if crossover_blocks(left, right, random):
            for child in (left, right):
                child.parents, child.crossed, child.lineage = parents, True, ancestry
        return left, right
    def mutation(member):
        feedback = None
        if not member.crossed:
            # Native batches are cached below; source positions must bind THIS parent tree.
            feedback = evaluate_feedback(member.parent_program)
        member[:] = mutate(member, capabilities, random, feedback=feedback)
        return member,
    def individual(row):
        member = Individual(deepcopy(row['program']))
        member.fitness = Fitness()
        member.key, member.lineage = row['key'], deepcopy(row['lineage'])
        member.parents, member.crossed = [member.key], False
        member.parent_program = deepcopy(list(member))
        return member
    def evaluate_member(member):
        score = evaluate_score(list(member), 'search', 0)
        member.key = score['candidate_key']
        report['search_cache_hits'] += int(score['cached'])
        lineage[member.key] = deepcopy(member.lineage)
        next(row for row in state['archive'] if row['key'] == member.key)['training_lineage'] = deepcopy(member.lineage)
        if not any(row['candidate_key'] == member.key for row in report['search_scores']):
            report['search_scores'].append(score)
            best = max(row['dps'] for row in report['search_scores'])
            if not report['search_curve'] or report['search_curve'][-1]['dps'] != best:
                report['search_curve'].append(dict(dps=best, seconds=run.elapsed_seconds))
        return score['dps'],
    toolbox.register('clone', clone)
    toolbox.register('mate', mate)
    toolbox.register('mutate', mutation)
    toolbox.register('evaluate', evaluate_member)
    toolbox.register('select', tools.selTournament, tournsize=3) if name == 'A' else toolbox.register('select', tools.selBest)

    def score_repeats(program, stage, count, destination):
        from concurrent.futures import ThreadPoolExecutor
        stopped = None
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(evaluate_score, program, stage, index) for index in range(count)]
            for future in futures:
                try:
                    destination.append(future.result())
                    store.checkpoint()
                except Exception as error:
                    if stopped is None:
                        stopped = error
        if stopped is not None:
            raise stopped  # Consume other reliable completed samples before propagating failure.

    def execute(*, evaluate, feedback):
        nonlocal evaluate_score, evaluate_feedback
        evaluate_score, evaluate_feedback = evaluate, feedback
        population = [individual(row) for row in rows]
        search_deadline = deadline - THREE_SELECTION_SECONDS - THREE_ENDPOINT_SECONDS - 10
        run.deadline = search_deadline
        try:
            for member in population:
                member.fitness.values = toolbox.evaluate(member)
            report['initial_complete'] = True
            report['population_slots'] = [member.key for member in population]
            store.checkpoint()
            custom = JointPopulation(original, capabilities, dict(policy=THREE_POLICY))
            custom_state = {}
            while True:
                run.check()
                proposed = deepcopy(population)
                report['partial_generation'] = True
                if name == 'A':
                    proposed, _ = algorithms.eaSimple(proposed, toolbox, cxpb=.8, mutpb=.8,
                        ngen=1, verbose=False)
                elif name == 'B':
                    proposed, _ = algorithms.eaMuPlusLambda(proposed, toolbox, mu=8, lambda_=16,
                        cxpb=.5, mutpb=.5, ngen=1, verbose=False)
                else:
                    next_state = deepcopy(custom_state)
                    candidates = custom(archive=deepcopy(state['archive']), seen=set(state['seen']),
                        rng=random, state=next_state,
                        feedback_for=lambda parent: evaluate_feedback(parent['program']))
                    for row in candidates:
                        child = individual(dict(row, lineage=row['lineage']))
                        child.parents, child.crossed = row['parents'], row['crossed']
                        child.fitness.values = toolbox.evaluate(child)
                    # C's breeding pool is independently rebuilt from the archive on each generation.
                    # The just-completed pool is recorded, not replaced via old optimizer promotion.
                    by_key = {row['key']: row for row in state['archive']}
                    proposed = [individual(dict(by_key[key], lineage=lineage[key])) for key in next_state['pool']]
                    for member in proposed:
                        member.fitness.values = (by_key[member.key]['batches'][0]['dps'],)
                    custom_state = next_state
                    if not candidates:
                        report['search_stop'] = 'no_unique_children'
                        report['partial_generation'] = False
                        break
                run.check()
                population = proposed
                report['complete_generations'] += 1
                report['partial_generation'] = False
                report['population_slots'] = [member.key for member in population]
                generation = dict(index=report['complete_generations'],
                    population_slots=list(report['population_slots']),
                    parents=[member.parents for member in population],
                    crossed=[member.crossed for member in population])
                if name == 'C':
                    generation.update(reserved_originals=list(custom_state['reserved_originals']),
                                      unique_children=len(candidates))
                    custom_state['proposals'] = []  # Detailed programs live once in the task archive.
                report['generations'].append(generation)
                state['rng'] = random.getstate()
                store.checkpoint()  # Only a full successful generation commits population/RNG state.
        except (runtime.BudgetExceeded, CandidateError, ValueError) as error:
            report['search_stop'] = f'{type(error).__name__}: {error}'
            if not isinstance(error, runtime.BudgetExceeded):
                report['errors'].append(dict(stage='search', error=str(error)))
        report['search_elapsed_seconds'] = run.elapsed_seconds
        # No search score or endpoint participates in this common selection stage twice.
        run.deadline = min(deadline - THREE_ENDPOINT_SECONDS - 10, time.monotonic() + THREE_SELECTION_SECONDS)
        ranked = sorted(report['search_scores'], key=lambda row: (-row['dps'], row['candidate_key']))[:2]
        archive = {row['key']: row for row in state['archive']}
        try:
            if len(ranked) != 2:
                raise ValueError('Two distinct reliable search behaviors are required')
            for ranked_row in ranked:
                choice = dict(key=ranked_row['candidate_key'], scores=[])
                report['selection'].append(choice)
                score_repeats(archive[choice['key']]['program'], 'selection', 2, choice['scores'])
                choice['mean_dps'] = statistics.mean(row['dps'] for row in choice['scores'])
            winner = max(report['selection'], key=lambda row: (row['mean_dps'], row['key']))
            report['winner'] = dict(key=winner['key'], selection_mean_dps=winner['mean_dps'])
            store.checkpoint()  # Unique winner is reliable and frozen before fresh endpoint samples.
            run.deadline = min(deadline - 10, time.monotonic() + THREE_ENDPOINT_SECONDS)
            score_repeats(archive[winner['key']]['program'], 'endpoint', 4, report['endpoint'])
        except (runtime.BudgetExceeded, CandidateError, ValueError) as error:
            report['errors'].append(dict(stage='endpoint' if report['winner'] else 'selection', error=str(error)))
        return report
    evaluate_score = evaluate_feedback = None
    return execute

def run_three_arm(source, output, manifest, slot, deadline):
    from engine import training_template
    from seed_training import template_character
    started = ENTRY
    report = dict(status='failed', strategy=slot['strategy'], complete_generations=0,
        population_slots=[], selection=[], endpoint=[], winner=None, errors=[])
    store = None
    try:
        root = output.parent
        context = json.loads((root / 'context.json').read_text())
        frozen = json.loads((root / 'inputs.json').read_text())
        if (manifest.get('prepared') != dict(context_sha256=digest(context), inputs_sha256=digest(frozen))
                or frozen != freeze_three_inputs(source, context['capabilities'], manifest)
                or context['inputs_digest'] != frozen['digest']):
            raise ValueError('Frozen eight inputs/context changed')
        isolate_center(output)
        folder = output / 'task'
        folder.mkdir(parents=True)
        store = TaskStore(folder)
        block = manifest['blocks'][slot['block']]
        profile = training_template()
        character = replace(template_character(profile.read_text()), spec_id=context['native']['identity']['spec_id'],
                            race=context['native']['identity']['race'])
        config = config_for(dict(random_seed=block['search_seed'], batch_targets=(32,), max_processes=2,
            round_candidate_limit=16, reset_events=(), input_interval_ms=200,
            diagnostics='off', diagnostic_logging=False, search_observability='off',
            rule_initialization_enabled=False, adaptive_selector_enabled=False), training=True)
        store.state.update(run_id=uuid.uuid4().hex, starts=[row['program'] for row in frozen['rows']],
            config=config, capabilities=context['capabilities'], burst=context['burst'],
            evidence_kind=manifest['evidence_kind'])
        run = ExperimentRuntime(THREE_ARM_SECONDS, deadline)
        random.seed(block['search_seed'])  # All official selectors, variation and mutations share ONE source.
        runner = three_evolution(slot['strategy'], frozen['rows'], context['capabilities'], store, run, block, deadline)
        with store.active(run):
            report = optimize(profile=profile, character=character, capabilities=context['capabilities'],
                reference=context['native'], destination=folder, runtime=run, config=config,
                condition_key=digest(dict(manifest=digest(manifest), block=slot['block'], strategy=slot['strategy'])),
                store=store, simulation_config=context['simulation_config'], training=True,
                training_runner=runner, training_stage_plan=block['stages'])
    except Exception as error:
        if store is not None:
            report = store.state.get('three_strategy', report)
        report.setdefault('errors', []).append(dict(stage='arm', error=f'{type(error).__name__}: {error}'))
    finally:
        if store is not None:
            try:
                run.deadline = deadline
                store.checkpoint()
                store.close()
            except Exception as error:
                report.setdefault('errors', []).append(dict(stage='save', error=f'{type(error).__name__}: {error}'))
        report.update(elapsed_seconds=time.monotonic() - started, budget_met=time.monotonic() <= deadline,
                      task_path='task', evidence_kind=manifest['evidence_kind'])
        report['compliant'] = bool(report.get('complete_generations', 0) > 0 and report['budget_met']
            and not report['errors'] and len(report['selection']) == 2
            and all(len(row['scores']) == 2 for row in report['selection']) and len(report['endpoint']) == 4)
        report['status'] = 'complete_arm' if report['compliant'] else 'incomplete_arm'
        write(output / 'arm.json', report)
        report['elapsed_seconds'] = time.monotonic() - started
        if time.monotonic() > deadline:
            report.update(budget_met=False, compliant=False, status='incomplete_arm')
        write(output / 'arm.json', report)
    return report

def summarize_three(slots, manifest):
    complete = [slot for slot in slots if slot.get('compliant') and slot.get('exit_code') == 0]
    planned_blocks = len(manifest['blocks'])
    expected = {(slot['block'], slot['strategy']) for slot in manifest['slots']}
    by_key = {(slot['block'], slot['strategy']): slot for slot in complete}
    all_complete = len(complete) == len(expected) and set(by_key) == expected
    comparisons = []
    for left, right in (('A', 'C'), ('B', 'C'), ('A', 'B')):
        differences = []
        for block in range(planned_blocks):
            first, second = by_key.get((block, left)), by_key.get((block, right))
            differences.append(dict(block=block, difference_dps=(
                first['endpoint_mean_dps'] - second['endpoint_mean_dps'] if first and second else None)))
        values = [row['difference_dps'] for row in differences if row['difference_dps'] is not None]
        wins, losses, ties = sum(value > 0 for value in values), sum(value < 0 for value in values), sum(value == 0 for value in values)
        # Conservative preregistration: ties remain in total n, never credited to either side.
        raw_p = (min(1.0, 2 * sum(math.comb(planned_blocks, count)
            for count in range(max(wins, losses), planned_blocks + 1)) / 2 ** planned_blocks)
            if len(values) == planned_blocks else None)
        comparisons.append(dict(pair=f'{left}-{right}', left=left, right=right, wins=wins,
            losses=losses, ties=ties, planned_n=planned_blocks, observed_n=len(values),
            differences=differences, raw_p=raw_p, holm_p=None, significant=False,
            favored=(left if wins > losses else right if losses > wins else None)))
    if all_complete:
        previous = 0.0
        for index, comparison in enumerate(sorted(comparisons, key=lambda row: row['raw_p'])):
            previous = min(1.0, max(previous, (3 - index) * comparison['raw_p']))
            comparison.update(holm_p=previous, significant=previous <= .05)
    winners = [name for name in 'ABC' if all(
        comparison['significant'] and comparison['favored'] == name
        for comparison in comparisons if name in (comparison['left'], comparison['right']))] if all_complete else []
    return dict(policy=THREE_POLICY, evidence_kind=manifest['evidence_kind'], planned=len(expected),
        attempted=sum(slot['status'] != 'not_started' for slot in slots), compliant_arms=len(complete),
        statistics=dict(status='complete' if all_complete else 'incomplete',
            method='two-sided exact paired sign test with conservative ties and Holm correction',
            alpha=.05, comparisons=comparisons, winner=winners[0] if len(winners) == 1 else None),
        conclusion=('statistical_winner' if len(winners) == 1 else
                    'unable_to_determine_winner' if all_complete else 'confirmation_incomplete'),
        scope='Directional paired win probability in these fixed conditions; not a test of mean DPS or general superiority',
        slots=slots)

def run_three(source, output, manifest, adapter=None):
    deadline = ENTRY + manifest['total_seconds']
    slots = [dict(slot, status='not_started', task_path=f"{slot['index']}/task") for slot in manifest['slots']]
    write(output / 'materials.json', source)
    write(output / 'manifest.json', manifest)
    def save():
        result = summarize_three(slots, manifest)
        result.update(elapsed_seconds=time.monotonic() - ENTRY, budget_met=time.monotonic() <= deadline)
        if not result['budget_met']:
            result['statistics'].update(status='incomplete_budget', winner=None)
            result['conclusion'] = 'confirmation_incomplete'
        write(output / 'summary.json', result)
        finished = time.monotonic()
        if finished > deadline:
            result.update(elapsed_seconds=finished - ENTRY, budget_met=False,
                          budget_failure='summary save completed after batch deadline')
            result['statistics'].update(status='incomplete_budget', winner=None)
            result['conclusion'] = 'confirmation_incomplete'
            write(output / 'summary.json', result)  # One bounded corrective save, never a retry loop.
        return result
    save()
    owned_groups = set()
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    previous_sigterm = signal.signal(signal.SIGTERM, terminate)
    try:
        if sys.platform == 'linux':
            runtime._create_process = CloudProcess
        frozen = prepare_three(source, output, manifest, deadline - 10)
        manifest['prepared'] = dict(context_sha256=digest(json.loads((output / 'context.json').read_text())),
                                    inputs_sha256=digest(frozen))
        write(output / 'manifest.json', manifest)
        for slot in slots:
            if time.monotonic() >= deadline - 2:
                break
            arm_started = time.monotonic()
            arm_deadline = min(arm_started + THREE_ARM_SECONDS, deadline - 1)
            folder = output / str(slot['index'])
            command = [sys.executable, str(Path(__file__).resolve()), '--three-strategy',
                '--materials', str(output / 'materials.json'), '--output', str(folder),
                '--manifest', str(output / 'manifest.json'), '--arm', str(slot['index']),
                '--deadline', str(arm_deadline)]
            if adapter is not None:
                command += ['--constructed-native-adapter', str(adapter)]
            slot['status'] = 'attempted'
            save()
            try:
                with (output / f"{slot['index']}-console.log").open('wb') as log:
                    if sys.platform == 'win32':
                        # Existing runtime owns the worker Job, including all nested native Jobs.
                        # Its redirects must never pre-create the worker's fresh output directory.
                        completed = runtime.run_command(command, ROOT,
                            timeout_seconds=max(0, arm_deadline - time.monotonic()),
                            runtime=ExperimentRuntime(THREE_ARM_SECONDS, arm_deadline),
                            output_dir=output / 'worker-logs' / str(slot['index']))
                        code = completed.returncode
                        log.write(completed.stdout)
                        log.write(completed.stderr)
                    else:
                        process = subprocess.Popen(parent_bound_command(command), stdout=log, stderr=log,
                            start_new_session=True)
                        owned_groups.add(process.pid)
                        try:
                            code = process.wait(timeout=max(0, arm_deadline - time.monotonic()))
                        except subprocess.TimeoutExpired:
                            slot['error'] = 'parent hard deadline killed owned worker/native process group'
                            try: os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError: pass
                            code = process.wait()
                        finally:
                            try: os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError: pass
                            if process.poll() is None:
                                process.wait()
                            owned_groups.discard(process.pid)
                slot['exit_code'] = code
                slot['parent_elapsed_seconds'] = time.monotonic() - arm_started
                arm = json.loads((folder / 'arm.json').read_text())
                slot.update(status='finished' if code == 0 else 'failed', result_path=f"{slot['index']}/arm.json",
                    compliant=arm['compliant'] and code == 0 and time.monotonic() <= arm_deadline,
                    complete_generations=arm['complete_generations'],
                    winner=arm.get('winner'), errors=arm['errors'], budget_met=arm['budget_met'] and time.monotonic() <= arm_deadline)
                if slot['compliant']:
                    slot['endpoint_mean_dps'] = statistics.mean(row['dps'] for row in arm['endpoint'])
            except (OSError, ValueError, KeyError, runtime.ProcessTimeout, runtime.BudgetExceeded) as error:
                slot.update(status='failed', compliant=False, error=f'{type(error).__name__}: {error}')
            save()
    except Exception as error:
        result = save()
        result['preparation_error'] = f'{type(error).__name__}: {error}'
        write(output / 'summary.json', result)
        return result
    finally:
        for group in owned_groups:
            try: os.killpg(group, signal.SIGKILL)
            except ProcessLookupError: pass
        signal.signal(signal.SIGTERM, previous_sigterm)
    return save()

def main():
    sys.path.append(str(ROOT / f'.local/population-mvp/venv/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'))
    parser = argparse.ArgumentParser()
    parser.add_argument('--materials', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--three-strategy', action='store_true')
    parser.add_argument('--arm', type=int, choices=range(36))
    parser.add_argument('--constructed-native-adapter', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--trial', type=int, choices=range(8))
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args()
    if sys.platform == 'win32' and not args.three_strategy:
        parser.error('Windows experiment requires explicit --three-strategy mode')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.local/population-mvp'):
        parser.error('Only ignored isolated experiment output is permitted')
    if output.exists() and not args.check_only: parser.error('Fresh output is mandatory')
    source = load_materials(args.materials)
    if args.constructed_native_adapter is not None:
        import runpy
        from contextlib import nullcontext
        adapter = args.constructed_native_adapter.resolve()
        if not args.three_strategy or adapter != ROOT / 'tests/sim2gse/research/three_strategy_native_adapter.py':
            parser.error('Only the explicit research native test boundary is permitted')
        boundary = runpy.run_path(str(adapter))['boundary'](ROOT, output)
    else:
        from contextlib import nullcontext
        boundary = nullcontext()
    with boundary:
        result = execute_cli(args, source, output, parser)
    if not args.three_strategy or args.arm is None:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))

def execute_cli(args, source, output, parser):
    if args.three_strategy and not args.check_only:
        kind = 'constructed_native_boundary' if args.constructed_native_adapter else 'real_native'
        if sys.platform == 'linux':
            runtime._create_process = CloudProcess
        if args.arm is not None:
            if args.manifest is None or args.deadline is None or not math.isfinite(args.deadline):
                parser.error('Arm worker requires frozen manifest and absolute deadline')
            manifest = json.loads(args.manifest.read_text())
            validate_three_manifest(manifest, source)
            if manifest['evidence_kind'] != kind:
                parser.error('Constructed and real evidence cannot mix')
            output.mkdir(parents=True)
            return run_three_arm(source, output, manifest, manifest['slots'][args.arm], min(args.deadline, ENTRY + THREE_ARM_SECONDS))
        if args.trial is not None or args.manifest is not None or args.deadline is not None:
            parser.error('Only worker accepts deadline/manifest/arm; old trial is not a three-strategy slot')
        manifest = three_manifest_for(source, kind)
        validate_three_manifest(manifest, source)
        output.mkdir(parents=True)
        return run_three(source, output, manifest, args.constructed_native_adapter)
    if args.arm is not None:
        parser.error('Arm requires explicit three-strategy mode')
    if args.check_only:
        runtime._create_process = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('native forbidden'))
        result = three_preflight(source, 'constructed_native_boundary' if args.constructed_native_adapter else 'real_native') if args.three_strategy else self_check(source, output)
    elif args.trial is not None:
        if args.manifest is None or args.deadline is None or not math.isfinite(args.deadline):
            parser.error('Worker requires frozen manifest and absolute deadline')
        manifest = json.loads(args.manifest.read_text())
        validate_manifest(manifest, source)
        output.mkdir(parents=True)
        result = run_trial(source, output, manifest['trials'][args.trial], manifest, min(args.deadline, ENTRY+600))
    else:
        if args.manifest is not None or args.deadline is not None: parser.error('Only worker accepts deadline/manifest')
        manifest = manifest_for(source)
        output.mkdir(parents=True)
        write(output / 'materials.json', source)
        result = run_pilot(source, output, manifest)
    return result

if __name__ == '__main__': main()
