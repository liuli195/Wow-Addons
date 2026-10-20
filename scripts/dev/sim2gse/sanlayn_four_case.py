"""Temporary four-case experiment: invoke once per case, sequentially; no product changes.

Snapshot manifest: {"files": {"center/relative/path": "sha256"},
"external_files": {"absolute/original/path": "sha256"}, "expected_missing": [...],
"source_main_root": "verified formal worktree", "source_main_commit": "main tip"}.
--center-snapshot contains ONLY reviewed files consulted by the official loaders.
External training evidence stays at its original path (path is part of its identity).
Each invocation copies the same snapshot to a fresh isolated writable center.
Default is preflight only. Never use an existing case output for a second invocation.
For the current two-case MVP use --timeline with both on and route-progress.
It records data only; comparison charts are rendered offline, not by the product.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import inspect
import json
import math
import shutil
import sqlite3
import subprocess
import sys
import time

INPUT_SHA = 'fa1ae07e2f0e6b027b6e67f6063147c60f02d323cabf65431eb60c7bfa3418d1'
BURST_ID = '1ee1ddbee05b3c538b7624a9beef49b6db92df32fd41b14d62b8b9338031a632'
STOP = "if state['no_improvement'] >= no_improvement_limit:"
CONFIG = dict(total_budget_seconds=600, search_budget_seconds=600,
    candidate_limit=1000, round_candidate_limit=16, no_improvement_rounds=5,
    batch_targets=[32, 128, 256], validation_batches=4, final_batches=20,
    iterations=100, final_iterations=100, max_processes=2, random_seed=20260912,
    input_interval_ms=200, diagnostic_logging=True, diagnostics='summary',
    search_observability='off', trace_search=False,
    scenarios=['nominal', 'jitter', 'slow', 'pause', 'phase'], reset_events=[])


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def checked_files(root, files):
    root = Path(root).resolve()
    for relative, expected in files.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or sha(path) != expected:
            raise ValueError('Snapshot file mismatch: ' + str(path))


def experiment_source(source, early_stop, *, observe=False):
    if early_stop not in ('on', 'off', 'route-progress'):
        raise ValueError('Unknown experiment early-stop policy')
    if source.count(STOP) != 1:
        raise ValueError('Expected exactly one original no-improvement condition')
    if early_stop == 'route-progress':
        marker = "                    state['round_improved'] = True\n"
        if source.count(marker) != 1:
            raise ValueError('Expected exactly one original global-improvement update')
        source = source.replace(marker,
            "                if global_promoted or (route_promoted and not work['start']):\n"
            + marker, 1)
    elif early_stop == 'off':
        source = source.replace(STOP, 'if False and ' + STOP[3:], 1)
    if observe:
        replacements = [
            ("                if generation is None:\n                    if all(",
             "                if generation is None:\n"
             "                    _experiment_event('paths', state)\n                    if all("),
            ("            state['seen'].append(key)\n",
             "            if current and (global_promoted or (len(state['archive']) == 1\n"
             "                    and state['best'] == current['key'])):\n"
             "                _experiment_event('best', state, current,\n"
             "                    'global' if global_promoted else 'initial')\n"
             "            state['seen'].append(key)\n"),
            ("            if current and global_promoted:\n                store.checkpoint()\n",
             "            if current and global_promoted:\n                store.checkpoint()\n"
             "                _experiment_event('checkpoint', state)\n"),
            ("            search()\n        except (BudgetExceeded, TaskCancelled) as error:\n",
             "            search()\n            _experiment_event('search_stopped', state)\n"
             "        except (BudgetExceeded, TaskCancelled) as error:\n"),
            ("                                    else 'search_deadline')\n            pending_outcome",
             "                                    else 'search_deadline')\n"
             "            _experiment_event('search_stopped', state)\n            pending_outcome"),
        ]
        for original, replacement in replacements:
            if source.count(original) != 1:
                raise ValueError('Expected exactly one timeline observation site: ' + original.strip())
            source = source.replace(original, replacement, 1)
    return source


class Timeline:
    """One experiment call's in-memory observations, separate from persistence."""

    def __init__(self, policy, *, expected_paths=4, expected_burst_start_ms=None,
                 clock=time.perf_counter):
        self.policy, self.clock = policy, clock
        self.expected_paths, self.expected_burst_start_ms = expected_paths, expected_burst_start_ms
        self.started = clock()
        self.events, self.checkpoints = [], []
        self.search_stop_seconds = self.stop_reason = self.actual_paths = None

    def record(self, kind, state, row=None, reason=None):
        elapsed = self.clock() - self.started
        if kind in ('paths', 'search_stopped'):
            self.actual_paths = len(state['chains'])
        if kind == 'paths':
            if self.actual_paths != self.expected_paths:
                raise ValueError(f'Expected {self.expected_paths} effective paths, got {self.actual_paths}')
            if self.expected_burst_start_ms is not None:
                actual = (state.get('burst') or {}).get('plan', {}).get('start_ms')
                if actual != self.expected_burst_start_ms:
                    raise ValueError(f'Expected burst start {self.expected_burst_start_ms}ms, got {actual}')
        if kind == 'best':
            if row['key'] != state['best'] or not math.isfinite(row['score']) or row['score'] <= 0:
                raise ValueError('Invalid observed global best')
            validation = row.get('global_validation') or row.get('validation') or {}
            self.events.append(dict(wall_seconds=elapsed, kind=reason, candidate_key=row['key'],
                dps=row['score'], samples=sum(batch['samples'] for batch in row['batches']),
                validation_ci95=validation.get('comparison', {}).get('ci95')))
        elif kind == 'checkpoint':
            self.checkpoints.append(dict(wall_seconds=elapsed, candidate_key=state.get('best')))
        elif kind == 'search_stopped':
            self.search_stop_seconds, self.stop_reason = elapsed, state.get('stop_reason')

    def finish(self, status):
        elapsed = self.clock() - self.started
        samples, index, current = [], 0, None
        for second in range(10, 601, 10):
            while index < len(self.events) and self.events[index]['wall_seconds'] <= second:
                current = self.events[index]
                index += 1
            phase = ('stopped' if status == 'completed' else 'incomplete') if second >= elapsed else (
                'finalizing' if self.search_stop_seconds is not None and second >= self.search_stop_seconds
                else 'searching')
            available = current if phase != 'incomplete' else None
            samples.append(dict(seconds=second, dps=available['dps'] if available else None,
                candidate_key=available['candidate_key'] if available else None, status=phase))
        return dict(schema_version=1, policy=self.policy, clock='outer_wall_seconds', status=status,
            events=self.events, checkpoints=self.checkpoints, samples=samples,
            actual_effective_path_count=self.actual_paths, search_stop_seconds=self.search_stop_seconds,
            stop_reason=self.stop_reason, call_seconds=elapsed,
            finalization_seconds=None if self.search_stop_seconds is None else elapsed-self.search_stop_seconds,
            result_saved_seconds=elapsed if status == 'completed' else None,
            note='Stopped samples hold an earlier result; they do not represent continued search.')


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def simulation_for(module):
    values = dict(target_count=1, enable_omnium_talents=True)
    if 'scene' in module.DEFAULT_CONFIG:
        values['scene'] = 'single_target'
    return module.config_for(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'input', 'center-snapshot', 'snapshot-manifest', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--source-manifest', type=Path)
    parser.add_argument('--early-stop', choices=('on', 'off', 'route-progress'), required=True)
    parser.add_argument('--timeline', action='store_true', help='Record MVP wall-clock DPS events and 60 samples')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.early_stop == 'route-progress' and not args.timeline:
        parser.error('route-progress requires --timeline; use it for the paired on case too')
    root, output, snapshot = args.repo.resolve(), args.out.resolve(), args.center_snapshot.resolve()
    project = root / 'projects/sim2gse'
    if output.exists() or output == snapshot or snapshot.is_relative_to(output):
        raise ValueError('A fresh output separate from the snapshot is required')
    if output.is_relative_to(root / 'data') or snapshot == root / 'data':
        raise ValueError('Use a reviewed minimal frozen snapshot, never the live center')
    if sha(args.input) != INPUT_SHA:
        raise ValueError('Input must be the original frozen LF bytes, not checkout CRLF bytes')
    if args.source_manifest:
        source_manifest = read(args.source_manifest)
        if source_manifest['commit'] != args.expected_commit:
            raise ValueError('Source snapshot commit mismatch')
        checked_files(root, source_manifest['files'])
        actual_head = None
        product_tree = None
    else:
        commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        actual_head = commit
        def tree(revision):
            return subprocess.check_output(['git', '-C', str(root), 'rev-parse', revision + ':projects/sim2gse'], text=True).strip()
        product_tree = tree(args.expected_commit)
        if tree(commit) != product_tree:
            raise ValueError('Pinned product tree mismatch; helper/doc commits alone are permitted')
        subprocess.run(['git', '-C', str(root), 'diff', '--exit-code', 'HEAD', '--', 'projects/sim2gse'], check=True)
    frozen = read(args.snapshot_manifest)
    if not frozen.get('source_main_root') or not frozen.get('source_main_commit'):
        raise ValueError('Snapshot must identify the verified formal main worktree and commit')
    formal_data = (Path(frozen['source_main_root']) / 'data').resolve()
    if output.is_relative_to(formal_data) or snapshot == formal_data:
        raise ValueError('Never write into or copy the live formal center directly')
    checked_files(snapshot, frozen['files'])
    if {p.relative_to(snapshot).as_posix() for p in snapshot.rglob('*') if p.is_file()} != set(frozen['files']):
        raise ValueError('Snapshot contains unreviewed files')

    def check_external():
        for path, expected in frozen.get('external_files', {}).items():
            if sha(path) != expected:
                raise ValueError('Original dependency changed: ' + path)
        for path in frozen.get('expected_missing', []):
            if Path(path).exists():
                raise ValueError('Previously missing dependency appeared: ' + path)

    check_external()
    original = (project / 'search.py').read_text(encoding='utf-8')
    effective = experiment_source(original, args.early_stop, observe=args.timeline)
    source_hashes = {p.relative_to(root).as_posix(): sha(p) for p in project.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    output.mkdir(parents=True)
    center = output / 'center'
    shutil.copytree(snapshot, center)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(project))
    spec = importlib.util.spec_from_file_location('search', project / 'search.py')
    search = importlib.util.module_from_spec(spec)
    sys.modules['search'] = search
    exec(compile(effective, str(project / 'search.py'), 'exec'), search.__dict__)
    import task, engine, result_store, simulation_config, runtime, burst, seed_training
    module_names = {p.stem for p in project.glob('*.py')}
    loaded_modules = {name: module.__file__ for name, module in sys.modules.items()
                      if name in module_names and getattr(module, '__file__', None)}
    if any(not Path(path).resolve().is_relative_to(project) for path in loaded_modules.values()):
        raise ValueError('Product imports came from another version')
    if result_store._skill_root().resolve() != (root / '.local/skills/data-store').resolve():
        raise ValueError('Data-store implementation binding belongs to another root')
    result_store.DATA_ROOT = center
    result_store.ensure_available()
    if engine.ROOT.resolve() != root:
        raise ValueError('Engine ROOT was redirected away from the selected version')
    engines = {mode: engine.identity(mode)[1] for mode in ('baseline', 'controlled')}
    config = search.config_for(CONFIG)
    simulation = simulation_for(simulation_config)
    character = task.parse_character(args.input.read_text(encoding='utf-8'))
    definition = burst.select_definition(character)
    if definition['definition_id'] != BURST_ID:
        raise ValueError('Frozen burst identity mismatch')
    selected = result_store.read_records('seed_selected', 'deathknight-unholy-1-burst')
    if not selected:
        raise ValueError('Expected the populated formal center; empty seed table is not this experiment')
    eligible = [row for row in selected if row.get('class_name') == character.class_name
                and row.get('spec') == character.spec and row.get('targets') == 1
                and decoded(row.get('engines')) == engines]
    # No capability invention: compatible rows require a genuine capability preflight.
    if eligible:
        raise ValueError('Compatible selected seeds need an actual capability snapshot; do not run with guessed capabilities')
    _, adaptations = task._seed_programs([], selected, character=character, targets=1,
        engines=engines, capabilities={'actions': []}, runtime=runtime.TaskRuntime(600))
    if adaptations:
        raise ValueError('Unexpected accepted/processed seed with no matching engine identity')
    champion_kwargs = dict(engines=engines, input_interval_ms=200, use_burst=True,
        burst_identity=dict(spec_id=definition['spec_id'], definition_id=BURST_ID))
    if 'rule_snapshot' in inspect.signature(seed_training.training_champion).parameters:
        import rule_config
        champion_kwargs['rule_snapshot'] = rule_config.load()
    # These official loaders are read-only and must not launch simulations.
    real_process = runtime._create_process
    def forbid_process(*values, **kwargs):
        raise RuntimeError('Preflight unexpectedly attempted an external process')
    runtime._create_process = forbid_process
    try:
        champion = seed_training.training_champion(character.class_name, character.spec, simulation,
                                                  **champion_kwargs)
    finally:
        runtime._create_process = real_process
    metadata = dict(commit=args.expected_commit, actual_head=actual_head, product_tree=product_tree, repo=str(root), input_sha256=INPUT_SHA,
        early_stop=args.early_stop, timeline_enabled=args.timeline, loaded_modules=loaded_modules, config=config, simulation_config=simulation, engines=engines,
        original_source_sha256=sha(project / 'search.py'),
        effective_search_sha256=hashlib.sha256(effective.encode()).hexdigest(),
        snapshot_manifest_sha256=sha(args.snapshot_manifest), source_sha256=source_hashes,
        source_main_root=frozen['source_main_root'], source_main_commit=frozen['source_main_commit'],
        frozen_provenance=frozen.get('provenance'),
        burst_definition_id=BURST_ID, original_burst_plan=definition['plan'],
        selected_offered=len(selected), selected_accepted=0,
        selected_exclusions=[dict(candidate_id=row.get('candidate_id'), reason='Official scope or full engine identity mismatch') for row in selected],
        training_champion=champion, cache='fresh per-case scoring cache',
        model_state='not_applicable_original' if not (project / 'selector.py').exists() else 'absent_in_formal_snapshot',
        note='Same real offered inputs, not guaranteed accepted experience, trajectories, burst alignment, or equal DPS.')
    # Fail closed rather than resetting a real model or pretending it was absent.
    if any(p.is_file() for folder in ('search_learners', 'search_learner_controls') for p in (center / folder).rglob('*')):
        raise ValueError('Formal model exists; record and preserve its actual state before running')
    write(output / 'preflight.json', metadata)
    print(json.dumps(dict(preflight='passed', output=str(output), run=args.run)), flush=True)
    if not args.run:
        return
    native = []
    def observed_process(command, cwd, folder):
        process = real_process(command, cwd, folder)
        if Path(command[0]).name.lower() == 'simc.exe':
            native.append(dict(folder=str(folder), command=[str(item) for item in command], at=time.perf_counter()-started))
        return process
    runtime._create_process = observed_process
    write(output / 'run-started.json', dict(started_unix=time.time()))
    timeline = Timeline(args.early_stop, expected_burst_start_ms=5000) if args.timeline else None
    started, result = timeline.started if timeline else time.perf_counter(), None
    if timeline:
        search._experiment_event = timeline.record
    try:
        result = task.run_task(args.input, output / 'task', mode='optimize', search_config=config,
                               simulation_config=simulation, use_burst=True)
    except BaseException as error:
        metadata.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        metadata['wall_seconds_including_finalization'] = time.perf_counter()-started
        runtime._create_process = real_process
        metadata['native_processes'] = native
        metadata['native_process_count'] = len(native)
        timeline_error = None
        if timeline:
            try:
                timeline_data = timeline.finish(result.get('status', 'incomplete') if result else 'incomplete')
                metadata['wall_seconds_including_finalization'] = timeline_data['call_seconds']
                write(output / 'timeline.json', timeline_data)
                metadata['timeline_file'] = 'timeline.json'
            except Exception as error:
                timeline_error = error
                metadata.update(timeline_export_error=str(error),
                    partial_timeline=dict(events=timeline.events, checkpoints=timeline.checkpoints))
        try:
            if result:
                searched = result.get('search') or {}
                metadata.update(status=result.get('status'), search_result=result.get('search_result'),
                    stop_reason=searched.get('stop_reason'), actual_effective_path_count=len(searched.get('chains', [])),
                    no_improvement_round_limit=searched.get('no_improvement_round_limit'),
                    product_candidate_count=searched.get('candidate_count'), product_unique_candidates=searched.get('unique_candidates'),
                    valid_archived_candidates=len({row['key'] for row in searched.get('records', [])
                        if isinstance(row.get('score'), (int, float)) and math.isfinite(row['score']) and row['score'] > 0}),
                    diagnostics=searched.get('diagnostics'), performance=result.get('performance'))
            diagnostic_file = output / 'task/diagnostics.json'
            metadata['final_diagnostics'] = read(diagnostic_file) if diagnostic_file.is_file() else None
            metadata['unavailable_metrics'] = 'Missing native phase costs/write counts are null, never assumed zero.'
            database = output / 'task/task.sqlite3'
            if database.is_file():
                with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
                    state = search.TaskStore.load_state(db)
                    metadata['initialization'] = {key: state.get(key) for key in
                        ('seed_adaptations', 'training_champion_snapshot', 'training_champion_adaptation',
                         'formal_champion_snapshot', 'formal_champion_adaptation', 'burst', 'rule_initialization')}
                    receipts = [json.loads(row[0]) for row in db.execute('SELECT value FROM batches')]
                scored = [r for r in receipts if r.get('status') == 'success' and r.get('request', {}).get('purpose') == 'search'
                          and not (r['request'].get('trace') and r['request'].get('iterations') == 2
                                   and r['request'].get('seed') == config['random_seed'] + 99)]
                metadata['successful_search_batches'] = len(scored)
                metadata['successfully_scored_candidates'] = len({r['request']['behavior_identity'] for r in scored})
        except Exception as error:
            metadata['metrics_export_error'] = str(error)
        metadata['source_unchanged'] = False
        try:
            metadata['source_unchanged'] = all(sha(root / name) == value for name, value in source_hashes.items())
            check_external()
            checked_files(snapshot, frozen['files'])
            metadata['frozen_dependencies_unchanged'] = True
        except (ValueError, OSError) as error:
            metadata.update(frozen_dependencies_unchanged=False, invalid_comparison=str(error))
        finally:
            if timeline_error:
                metadata.update(task_status=metadata.get('status'), status='incomplete')
            write(output / 'run-summary.json', metadata)
        if not metadata['source_unchanged'] or not metadata.get('frozen_dependencies_unchanged'):
            if 'error_type' not in metadata:
                raise ValueError('Source or frozen dependencies changed during experiment')
        if timeline_error and 'error_type' not in metadata:
            raise RuntimeError('Timeline export failed; preserve this run, do not repeat the search') from timeline_error


if __name__ == '__main__':
    main()
