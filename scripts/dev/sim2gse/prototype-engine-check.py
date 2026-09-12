"""Task-8 native engine experiment. No game validation or optimized DPS claim."""
from pathlib import Path
import hashlib
import json
import re
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / '.local/sim2gse/execution-prototype/runs'
PROFILE = ROOT / '.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc'
COMMON = ['item_db_source=local', 'threads=1', 'seed=20260912', 'target_error=0',
          'fixed_time=1', 'vary_combat_length=0', 'fight_style=Patchwerk', 'desired_targets=1',
          'optimal_raid=0', 'potion=disabled', 'flask=disabled', 'food=disabled',
          'augmentation=disabled', 'temporary_enchant=disabled', 'override.allow_potions=0',
          'override.allow_food=0', 'override.allow_flasks=0', 'override.allow_augmentations=0']

def run(name, mode='controlled', actions=None, steps=None, window=0.4,
        trinkets=False, iterations=1, seconds=30, trace=True, expected_error=None):
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    profile = PROFILE.read_text(encoding='utf-8')
    assert hashlib.sha256(PROFILE.read_bytes()).hexdigest() == '27181b0a92bb198a4266762d5f6fb4b6123c06d07786de58e5eae65a8cf5ee59'
    if trinkets:
        # Separate test fixture only. Never overwrite the user's original profile.
        profile = re.sub(r'^trinket1=.*$', 'trinket1=,id=270175,ilevel=311', profile, flags=re.M)
        profile = re.sub(r'^trinket2=.*$', 'trinket2=,id=250225,ilevel=311', profile, flags=re.M)
        if trinkets == 'channel':
            profile = re.sub(r'^trinket1=.*$', 'trinket1=,id=270168,ilevel=311', profile, flags=re.M)
    if actions:
        # Explicit default list prevents the class initializer replacing custom lists.
        # These are also traps: controlled runs must never auto-scan this list.
        profile += '\nactions=outbreak/dark_transformation,use_off_gcd=1\n'
        profile += 'actions.precombat=raise_dead/snapshot_stats\n'
        profile += 'actions.sim2gse=' + '/'.join(actions) + '\n'
    if steps is not None:
        profile += f'sim2gse_steps={steps}\nsim2gse_window={window}\nsim2gse_trace={int(trace)}\n'
    input_file = folder / 'input.simc'
    input_file.write_text(profile, encoding='utf-8')
    exe = ROOT / f'.tools/sim2gse/execution-prototype/{mode}/engine/simc.exe'
    build = json.loads((OUT.parent / mode / 'build.json').read_text())
    assert build['exit_code'] == 0, 'latest build failed; refusing an older binary'
    assert build['binary_sha256'] == hashlib.sha256(exe.read_bytes()).hexdigest()
    if mode == 'controlled':
        assert build['patch_sha256'] == hashlib.sha256((ROOT / 'scripts/dev/sim2gse/prototype-controller.patch').read_bytes()).hexdigest()
    args = [str(exe), str(input_file), *COMMON, f'iterations={iterations}', f'max_time={seconds}',
            f'json2={folder / "result.json"}', f'output={folder / "result.txt"}']
    start = time.perf_counter()
    proc = subprocess.run(args, cwd=folder, capture_output=True, timeout=90)
    elapsed = time.perf_counter() - start
    (folder / 'process.log').write_bytes(proc.stdout + proc.stderr)
    evidence = {'command': args, 'exit_code': proc.returncode, 'seconds': elapsed,
                'binary_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
                'input_sha256': hashlib.sha256(input_file.read_bytes()).hexdigest()}
    (folder / 'run.json').write_text(json.dumps(evidence, indent=2))
    if expected_error:
        assert proc.returncode != 0 and expected_error in (proc.stdout + proc.stderr).decode('utf-8', errors='replace')
        print(f'PASS: rejected {name}', flush=True)
        return None, [], {'name': name, 'rejected': True, 'expected_error': expected_error}
    assert proc.returncode == 0, f'{name}: see process.log'
    report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    lines = (folder / 'result.txt').read_text(encoding='utf-8').splitlines()
    events = []
    for line in lines:
        if 'S2GSE\t' in line:
            t, event, origin, step, action, gcd, rp, health, cooldown = line.split('S2GSE\t', 1)[1].split('\t')
            events.append(dict(ms=float(t), event=event, origin=int(origin), step=int(step),
                               action=action, gcd=float(gcd), rp=float(rp), health=float(health), cooldown_ms=float(cooldown)))
    p = report['sim']['players'][0]
    summary = {'name': name, 'elapsed_seconds': elapsed, 'dps': p['collected_data']['dps']['mean'],
               'events': len(events), 'iterations': iterations, 'combat_seconds': seconds}
    print(json.dumps(summary), flush=True)
    return p, events, summary

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps({'status': 'running', 'client_validated': False}))
    summaries = []
    baseline, _, s = run('native-baseline', mode='baseline', iterations=100, seconds=180, trace=False)
    summaries.append(s)
    disabled, _, s = run('controller-disabled', iterations=100, seconds=180, trace=False)
    summaries.append(s)
    assert baseline == disabled, 'controller-disabled full player report differs'
    cases = [
        ('single', ['outbreak'], '1', 0.4, False),
        ('failed-step', ['outbreak', 'death_coil', 'scourge_strike'], '1/2/3', 0.4, False),
        ('queue-replace', ['outbreak', 'scourge_strike', 'death_coil'], '1/2/3', 0.4, False),
        ('queue-retain', ['outbreak', 'death_coil'], '1/1/1/1/2/1', 0.4, False),
        ('no-queue', ['outbreak', 'scourge_strike'], '1/2', 0, False),
        ('trinket-spell', ['use_item,slot=trinket1', 'outbreak'], '1+2', 0.4, True),
        ('trinkets-13-14', ['use_item,slot=trinket1', 'use_item,slot=trinket2', 'outbreak'], '1+2+3', 0.4, True),
        ('trinkets-14-13', ['use_item,slot=trinket1', 'use_item,slot=trinket2', 'outbreak'], '2+1+3', 0.4, True),
        ('haste-queue', ['outbreak', 'use_item,slot=trinket2'], '1/1/1/1+2', 0.4, True),
    ]
    evidence = {}
    for name, actions, steps, window, trinkets in cases:
        p, events, s = run(name, actions=actions, steps=steps, window=window, trinkets=trinkets)
        summaries.append(s)
        inputs = [e for e in events if e['event'] == 'input']
        assert len(inputs) >= 100 and inputs[0]['ms'] == 0
        assert all(b['ms'] - a['ms'] == 300 for a, b in zip(inputs, inputs[1:]))
        assert all(e['step'] == i % len(steps.split('/')) for i, e in enumerate(inputs))
        native = [e for e in events if e['event'] == 'native_execute']
        assert native, f'{name}: no native execution'
        assert all(any(d['event'] == 'dispatch' and d['action'] == e['action'] and d['ms'] == e['ms']
                       for d in events) for e in native), f'{name}: unrequested native action'
        if name == 'failed-step':
            assert any(e['event'] == 'not_ready' and e['action'] == 'death_coil' and e['ms'] == 300 for e in events)
            assert not any(e['event'] == 'native_execute' and e['action'] == 'scourge_strike' and e['ms'] == 300 for e in events)
            assert any(e['action'] == 'scourge_strike' and e['origin'] == 3 and e['ms'] == 600 for e in events)
        if name == 'queue-replace':
            assert any(e['event'] == 'replace' for e in events)
            for e in (e for e in events if e['event'] == 'replace'):
                assert not any(d['event'] == 'dispatch' and d['origin'] == e['origin'] and d['ms'] >= e['ms'] for d in events)
        if name == 'no-queue':
            assert not any(e['event'] == 'queue' for e in events)
        if name == 'queue-retain':
            assert any(q['event'] == 'queue' and d['event'] == 'dispatch' and q['origin'] == d['origin']
                       and any(f['event'] == 'not_ready' and q['ms'] < f['ms'] < d['ms'] for f in events)
                       for q in events for d in events), 'invalid input retention not exercised'
        if name == 'trinket-spell':
            assert [e['action'] for e in native if e['ms'] == 0] == ['use_item_voracious_heart_of_ulatek', 'outbreak']
        if name.startswith('trinkets-'):
            at_zero = [e['action'] for e in native if e['ms'] == 0]
            expected = 'use_item_voracious_heart_of_ulatek' if name.endswith('13-14') else 'use_item_void_execution_mandate'
            assert at_zero == [expected, 'outbreak'], at_zero
            assert any(e['event'] == 'not_ready' and e['ms'] == 0 and e['action'].startswith('use_item_') and e['action'] != expected for e in events)
            item_exec = [e for e in native if e['action'].startswith('use_item_')]
            assert len({e['action'] for e in item_exec}) == 2, 'second trinket never becomes usable'
            assert all(b['ms'] - a['ms'] >= 20000 for a, b in zip(item_exec, item_exec[1:])), 'shared lockout violated'
        precombat = [e['action'] for e in events if e['event'] == 'explicit_precombat']
        assert precombat == ['raise_dead', 'snapshot_stats'], precombat
        # GCD dispatch must never precede its current native deadline.
        assert all(e['ms'] >= e['gcd'] for e in events if e['event'] == 'dispatch' and not e['action'].startswith('use_item_'))
        evidence[name] = {'event_counts': {k: sum(e['event'] == k for e in events) for k in sorted({e['event'] for e in events})},
                          'first_events': events[:20]}
    actions = ['auto_attack', 'outbreak', 'army_of_the_dead', 'dark_transformation',
               'festering_strike', 'scourge_strike', 'death_coil', 'soul_reaper', 'putrefy']
    steps = '1+2/3/4/5/6/7/8/9/6/7/5/6'
    perf = {}
    fixed_reports = []
    for mode in ('native', 'sequence', 'trace'):
        measured = []
        for repeat in range(3):
            p, events, s = run(f'performance-{mode}-{repeat}', mode='baseline' if mode == 'native' else 'controlled',
                              actions=None if mode == 'native' else actions,
                              steps=None if mode == 'native' else steps, iterations=100, seconds=180,
                              trace=mode == 'trace')
            measured.append(s['elapsed_seconds'])
            summaries.append(s)
            if mode != 'native': fixed_reports.append(p)
            if mode == 'trace' and repeat == 0:
                evidence['fixed-sequence'] = {'event_counts': {k: sum(e['event'] == k for e in events) for k in sorted({e['event'] for e in events})},
                    'health_min': min(e['health'] for e in events),
                    'native_actions': sorted({e['action'] for e in events if e['event'] == 'native_execute'})}
                assert any(e['event'] == 'queue' and e['action'] == 'army_of_the_dead' and e['cooldown_ms'] > 0 for e in events)
                assert all(e['cooldown_ms'] <= 0 for e in events if e['event'] == 'dispatch'), 'cooldown bypassed'
                assert not any(e['event'] == 'dispatch_failed' for e in events), 'unexplained dispatch failure'
                assert p['stats_pets'], 'native pet evidence missing'
                pet = next(stat for stat in p['stats'] if stat['name'] == 'raise_dead')
                assert any(stat.get('actual_amount', {}).get('mean', 0) > 0 for stat in pet['children']), 'ghoul produced no damage'
                replacement = next(stat for stat in p['stats'] if stat['name'] == 'festering_scythe')
                assert replacement['id'] == 458128 and replacement['num_executes']['mean'] > 0
        perf[mode] = {'seconds': measured, 'median_seconds': statistics.median(measured),
                      'requested_iterations_per_second': 100 / statistics.median(measured)}
    assert all(p == fixed_reports[0] for p in fixed_reports), 'trace logging or replay changed the full player result'
    for name, act, seq, error in [
        ('invalid-index', ['outbreak'], '2', 'out of range'),
        ('passive-item', ['use_item,slot=trinket1', 'outbreak'], '1+2', 'action removed'),
        ('apl-condition', ['outbreak,if=0'], '1', 'unsupported sim2gse'),
        ('two-gcd-block', ['outbreak', 'scourge_strike'], '1+2', 'at most one GCD'),
    ]:
        _, _, s = run(name, actions=act, steps=seq, expected_error=error)
        summaries.append(s)
    _, _, s = run('channel-item', actions=['use_item,slot=trinket1', 'outbreak'], steps='1+2', trinkets='channel',
                   expected_error='cast/channel trinket')
    summaries.append(s)
    (OUT / 'summary.json').write_text(json.dumps({'status': 'passed', 'summaries': summaries,
        'cases': evidence, 'performance': perf, 'client_validated': False}, indent=2))
    print('PASS: disabled regression and native input cases; client validation NOT RUN')

if __name__ == '__main__':
    main()
