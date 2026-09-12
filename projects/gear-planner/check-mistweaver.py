"""Run native engine and application checks; these are not independent game snapshots."""
from pathlib import Path
import copy
import hashlib
import json
import math
import subprocess
import tempfile
import server

root = server.ROOT
fixture = Path(__file__).parent / 'fixtures/mistweaver-supported/mistweaver.input.simc'
model = server.parse_import(fixture.read_text(encoding='utf-8'))

def native(text, engine=server.MISTWEAVER_EXE, extra=()):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, out = d/'input.simc', d/'out.json'
        src.write_text(text, encoding='utf-8')
        args = [str(engine), str(src), 'allow_experimental_specializations=1',
                'iterations=1', 'threads=1', 'fixed_time=1', 'max_time=1',
                'optimal_raid=0', 'actions.precombat=snapshot_stats',
                'actions=wait,sec=1', 'food=disabled', 'flask=disabled',
                'potion=disabled', 'augmentation=disabled', 'temporary_enchant=disabled',
                'json2='+str(out), *extra]
        run = subprocess.run(args, cwd=d, capture_output=True, timeout=30)
        assert run.returncode == 0, run.stderr.decode(errors='replace')
        return json.loads(out.read_text())['sim']['players'][0]

text = fixture.read_text(encoding='utf-8')
base_text = '\n'.join(l for l in text.splitlines() if not l.startswith('talents='))
b = native(base_text)
old = native(base_text, root/'.local/gear-planner-mistweaver-research/source/engine/simc-mistweaver-gate.exe')
attrs = lambda a: a['collected_data']['buffed_stats']['attribute']
snapshot = lambda a: a['collected_data']['buffed_stats']
assert attrs(b)['intellect'] > attrs(old)['intellect']
assert attrs(b)['agility'] < attrs(old)['agility']
for slot in ('chest', 'back'):
    removed = native('\n'.join(l for l in base_text.splitlines() if not l.startswith(slot+'=')))
    gain = b['gear'][slot]['agiint' if slot == 'chest' else 'stragiint']
    if slot == 'chest':
        before_leather = attrs(removed)['intellect'] + gain
        assert attrs(b)['intellect'] == math.floor(before_leather*1.05)
    else:
        assert attrs(removed)['intellect'] == math.floor((before_leather-gain)*1.05)
    assert attrs(b)['agility'] == attrs(removed)['agility']
    assert attrs(b)['stamina']-attrs(removed)['stamina'] == b['gear'][slot]['stamina']
jade = native(text)
assert attrs(jade)['stamina'] == math.floor(attrs(b)['stamina']*1.08)
assert snapshot(native(text, extra=('role=heal','target_level=90'))) == snapshot(jade)
for stat in ('crit','haste','mastery','versatility'):
    assert snapshot(b)['stats'][stat+'_rating'] == sum(g.get(stat+'_rating',0) for g in b['gear'].values())

# Physical specializations must be bit-for-bit unchanged on the same source build.
for spec in ('brewmaster','windwalker'):
    source = root/f'projects/gear-planner/fixtures/raidbots-monk/{spec}.input.simc'
    t = source.read_text(encoding='utf-8')
    control = root/'.local/gear-planner-mistweaver-research/source/engine/simc-mistweaver-control.exe'
    assert snapshot(native(t, control)) == snapshot(native(t))

result = server.calculate(model)
assert result['complete'], result
assert 'mistweaver-attributes1' in result['version']
assert result['values']['intellect'] == attrs(jade)['intellect']
assert result['values']['stamina'] == attrs(jade)['stamina']
assert result['values']['ilevel'] == 334*14/16
assert '未计入罗盘' in result['calculationState']
assert result['items']['head']['enchantOptions']
variant = copy.deepcopy(model)
f = server.gear_fields(variant['gear']['neck']); f['gem_id']='240894'
f['bonus_id'] += '/13668'; variant['gear']['neck']=server.encode(f)
gem = server.calculate(variant); assert gem['complete']
assert gem['values'] != result['values']
f = server.gear_fields(variant['gear']['chest']); f['enchant_id']='7987'
variant['gear']['chest']=server.encode(f)
enchanted = server.calculate(variant); assert enchanted['complete']
assert enchanted['values']['intellect'] > gem['values']['intellect']
assert enchanted['values']['agility'] == gem['values']['agility']
candidate=next(i for i,x in enumerate(server.CATALOG['chest']) if not x['fitReasonsBySpec']['monk:mistweaver'] and x['id']!=193764 and not x['conversion'])
swapped=server.apply_edit(variant, {'slot':'chest','candidate':candidate})
swap_result=server.calculate(swapped);assert swap_result['complete']
assert swap_result['items']['chest']['ilevel']==enchanted['items']['chest']['ilevel']
assert server.gear_fields(swapped['gear']['chest'])['enchant_id']=='7987'
restored=json.loads(json.dumps(swapped));server.validate(restored)
assert server.calculate(restored)['values']==swap_result['values']
for race in ('human','blood_elf','gnome','night_elf','highmountain_tauren'):
    race_model=copy.deepcopy(model);race_model['character']['race']=race
    r=server.calculate(race_model);assert r['complete'], (race,r)
    assert r['values']['intellect'] > 0

# Holy stays on its already approved executable and preserves saved reference values.
assert hashlib.sha256(server.HOLY_EXE.read_bytes()).hexdigest() == '7fc6a54acd4fa247fc4e1703619c03da3368ecb4f853a880a427ffdc7a87f6ae'
holy_dir=Path(__file__).parent/'fixtures/holy-paladin-supported'
holy_text=(holy_dir/'holy.input.simc').read_text(encoding='utf-8')
holy_text='\n'.join(l for l in holy_text.splitlines() if l.split('=',1)[0] in {'paladin','level','race','spec','talents',*server.SLOT_KEYS})
h=server.calculate(server.parse_import(holy_text))
assert h['complete'] and 'holy-gate1' in h['version']
ref=json.loads((holy_dir/'manifest.json').read_text())['samples'][0]['snapshot']
for k,v in ref['attribute'].items(): assert h['values'][k] == v
assert h['values']['armor'] == ref['stats']['armor']
print('PASS: mixed intellect, armor specialization, native stamina talent, heal target, rating sums, physical specs, application, gems/enchants, races and holy regression')
