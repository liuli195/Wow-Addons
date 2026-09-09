"""Research-only probe of an unmodified upstream executable; not a planner engine."""
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[3] / '.local/gear-planner-research'
EXE = ROOT / '.tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe'
UPSTREAM = (ROOT / '.tools/gear-planner-research/upstream-blood.simc').read_text()
TALENTS = next(line for line in UPSTREAM.splitlines() if line.startswith('talents='))
BASE = ('deathknight=research_probe\nlevel=90\nrace=mechagnome\nspec=blood\n' + TALENTS + '\n'
        'potion=disabled\nflask=disabled\nfood=disabled\naugmentation=disabled\ntemporary_enchant=disabled\n')
WEAPON = 'main_hand=,id=268213,ilevel=344,enchant_id=6241\n'
RING = 'finger1=,id=240949,ilevel=331,crafted_stats=32/36'
cases = {
    'weapon-only': WEAPON,
    'crafted-ring': WEAPON + RING + '\n',
    'crafted-gem': WEAPON + RING + ',gem_id=240894\n',
    'crafted-enchant': WEAPON + RING + ',enchant_id=7967\n',
    'crafted-both': WEAPON + RING + ',gem_id=240894,enchant_id=7967\n',
    'crafted-higher-ilvl': WEAPON + RING.replace('ilevel=331', 'ilevel=344') + '\n',
    'crafted-other-stats': WEAPON + RING.replace('32/36', '32/49') + '\n',
    'mplus-ring': WEAPON + 'finger1=,id=158366,ilevel=331\n',
    'raid-neck': WEAPON + 'neck=,id=268252,ilevel=344\n',
    'historical-weapon': 'main_hand=,id=19364\n',
    'unknown-item': WEAPON + 'finger1=,id=999999999\n',
}
results = {}
for name, gear in cases.items():
    profile = HERE / f'{name}.input.simc'
    saved = HERE / f'{name}.saved.simc'
    profile.write_text(BASE + gear, encoding='utf-8')
    started = time.perf_counter()
    result = subprocess.run([str(EXE), str(profile), 'item_db_source=local',
                             f'save={saved}', 'optimal_raid=0'],
                            cwd=HERE, text=True, capture_output=True, timeout=30)
    elapsed = time.perf_counter() - started
    (HERE / f'{name}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    stats = {}
    if result.returncode == 0:
        assert saved.exists(), name
        stats = {key: float(value) for key, value in
                 re.findall(r'^# gear_(\w+)=([\d.]+)$', saved.read_text(), re.M)}
        assert stats, name
    results[name] = {'exit_code': result.returncode, 'seconds': round(elapsed, 4),
                     'gear_summary': stats, 'input': gear.strip()}
assert results['unknown-item']['exit_code'] != 0
assert all(v['exit_code'] == 0 for k, v in results.items() if k != 'unknown-item'), results
assert results['crafted-higher-ilvl']['gear_summary']['stamina'] > results['crafted-ring']['gear_summary']['stamina']
assert results['crafted-both']['gear_summary'] != results['crafted-ring']['gear_summary']
(HERE / 'simc-probe-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))

snapshots = {}
snapshot_inputs = {name: BASE + cases[name] for name in ('crafted-ring', 'crafted-gem', 'crafted-enchant', 'crafted-both', 'weapon-only')}
snapshot_inputs['stoneskin'] = BASE + WEAPON.replace('enchant_id=6241', 'enchant_id=3847')
snapshot_inputs['full-upstream'] = UPSTREAM
for name, body in snapshot_inputs.items():
    source = HERE / f'{name}.snapshot.input.simc'
    output = HERE / f'{name}.snapshot.json'
    source.write_text(body, encoding='utf-8')
    args = [str(EXE), str(source), 'item_db_source=local', 'iterations=1', 'threads=1',
            'fixed_time=1', 'max_time=1', 'vary_combat_length=0', 'optimal_raid=0',
            'potion=disabled', 'flask=disabled', 'food=disabled', 'augmentation=disabled',
            'temporary_enchant=disabled', 'override.allow_potions=0', 'override.allow_food=0',
            'override.allow_flasks=0', 'override.allow_augmentations=0',
            'actions.precombat=snapshot_stats', 'actions=wait,sec=1',
            f'json={output},version=2,pretty_print=1', f'output={HERE / (name + ".snapshot.txt")}']
    started = time.perf_counter()
    run = subprocess.run(args, cwd=HERE, text=True, capture_output=True, timeout=30)
    elapsed = time.perf_counter() - started
    (HERE / f'{name}.snapshot.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    assert run.returncode == 0, (name, run.stdout, run.stderr)
    doc = json.loads(output.read_text())
    actor = doc['sim']['players'][0]
    snapshots[name] = {'seconds': round(elapsed,4), 'git_revision':doc['git_revision'],
                       'snapshot':actor['collected_data']['buffed_stats'],
                       'constant_buffs':actor.get('buffs_constant'),
                       'buffs':actor.get('buffs'), 'gear':actor.get('gear')}
    assert actor['collected_data'].get('dps', {}).get('mean', 0) == 0, name
    assert actor['stats'] == [], name
assert snapshots['crafted-gem']['snapshot']['stats']['haste_rating'] - snapshots['crafted-ring']['snapshot']['stats']['haste_rating'] == 16
(HERE / 'snapshot-probe-results.json').write_text(json.dumps(snapshots, indent=2), encoding='utf-8')
print(json.dumps({name: {'seconds':data['seconds'], 'snapshot':data['snapshot']} for name,data in snapshots.items()}, indent=2))
