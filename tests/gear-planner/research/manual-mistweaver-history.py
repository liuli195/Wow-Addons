import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "projects/gear-planner"))
"""Manual historical same-source replay. Requires the original .local control engines.

Daily regression is test_real.py; these old/fixed-engine comparisons are not
independent game snapshots and are intentionally outside the 60-second suite.
"""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import tempfile
import server

root = server.ROOT
fixture = server.HERE / 'fixtures/mistweaver-supported/mistweaver.input.simc'

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

# Holy stays on its already approved executable and preserves saved reference values.
assert hashlib.sha256(server.HOLY_EXE.read_bytes()).hexdigest() == '7fc6a54acd4fa247fc4e1703619c03da3368ecb4f853a880a427ffdc7a87f6ae'
holy_dir=server.HERE/'fixtures/holy-paladin-supported'
holy_text=(holy_dir/'holy.input.simc').read_text(encoding='utf-8')
holy_text='\n'.join(l for l in holy_text.splitlines() if l.split('=',1)[0] in {'paladin','level','race','spec','talents',*server.SLOT_KEYS})
h=server.calculate(server.parse_import(holy_text))
assert h['complete'] and 'holy-gate1' in h['version']
ref=json.loads((holy_dir/'manifest.json').read_text())['samples'][0]['snapshot']
for k,v in ref['attribute'].items(): assert h['values'][k] == v
assert h['values']['armor'] == ref['stats']['armor']
print('PASS: historical mixed intellect, armor specialization, native stamina talent, heal target, rating sums, physical-spec and holy comparison')
