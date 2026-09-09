"""Bounded native-engine checks; edited cases are not game-panel observations."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parents[3] / '.local/gear-planner-research'
ROOT = HERE.parents[1]
EXE = ROOT / '.tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe'
BASE = (HERE / 'cn-user-20260908.input.simc').read_text(encoding='utf-8')

def edit(slot, old, new):
    lines = BASE.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(slot + '='))
    assert old in lines[index]
    lines[index] = lines[index].replace(old, new)
    return '\n'.join(lines) + '\n'

cases = {
    'baseline': BASE,
    'remove-neck-gem': edit('neck', ',gem_id=240894', ''),
    'remove-ring-enchant': edit('finger1', ',enchant_id=7967', ''),
    'crafted-field-only-conflict': edit('main_hand', 'crafted_stats=36/49', 'crafted_stats=36/32'),
    'crafted-secondaries': edit('main_hand', 'crafted_stats=36/49', 'crafted_stats=32/36').replace('/8791/', '/8790/'),
    'lower-shoulder-rank': edit('shoulder', '12854', '12853'),
    'empty-shoulder': '\n'.join(line for line in BASE.splitlines() if not line.startswith('shoulder=')) + '\n',
}
results = {}
for name, body in cases.items():
    source = HERE / f'cn-edit-{name}.simc'
    output = HERE / f'cn-edit-{name}.json'
    source.write_text(body, encoding='utf-8')
    args = [str(EXE), str(source), 'item_db_source=local', 'iterations=1', 'threads=1',
            'fixed_time=1', 'max_time=1', 'vary_combat_length=0', 'optimal_raid=0',
            'potion=disabled', 'flask=disabled', 'food=disabled', 'augmentation=disabled',
            'temporary_enchant=disabled', 'override.allow_potions=0', 'override.allow_food=0',
            'override.allow_flasks=0', 'override.allow_augmentations=0',
            'actions.precombat=snapshot_stats', 'actions=wait,sec=1',
            f'json={output},version=2,pretty_print=1', f'output={HERE / ("cn-edit-" + name + ".txt")}']
    run = subprocess.run(args, cwd=HERE, capture_output=True, text=True, timeout=20)
    (HERE / f'cn-edit-{name}.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    assert run.returncode == 0, (name, run.stdout, run.stderr)
    actor = json.loads(output.read_text())['sim']['players'][0]
    assert actor['stats'] == [], name
    results[name] = {'snapshot': actor['collected_data']['buffed_stats'], 'gear': actor['gear']}
base = results['baseline']['snapshot']
gem = results['remove-neck-gem']['snapshot']
assert base['stats']['haste_rating'] - gem['stats']['haste_rating'] == 16
assert base['stats']['versatility_rating'] - gem['stats']['versatility_rating'] == 7
assert results['lower-shoulder-rank']['gear']['shoulders']['ilevel'] == 331
assert results['lower-shoulder-rank']['snapshot']['attribute']['stamina'] < base['attribute']['stamina']
assert results['crafted-secondaries']['snapshot']['stats'] != base['stats']
assert results['crafted-field-only-conflict']['snapshot'] == base
assert results['crafted-secondaries']['gear']['main_hand']['haste_rating'] == 99
assert 'mastery_rating' not in results['crafted-secondaries']['gear']['main_hand']
assert 'shoulders' not in results['empty-shoulder']['gear']
assert base == json.loads((HERE / 'cn-user-20260908.snapshot.json').read_text())['sim']['players'][0]['collected_data']['buffed_stats']
(HERE / 'cn-edit-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print('PASS: seven native snapshots; baseline, gem delta, rank, crafted-field conflict and normalized change checked')
