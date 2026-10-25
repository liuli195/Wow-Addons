"""Manual online/cached tooltip-data replay, not a daily algorithm test.

Preserves the original two-level effect values and all 65 set-item/40-spec
upstream data checks. May contact Wowhead and populate the normal effect cache.
Pure parsing, cache keys and display rules live in test_rules.py/check-summary.js.
"""
import sys
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'projects/gear-planner'))
import server

small=server.item_effects({'itemId':250245,'level':311})
large=server.item_effects({'itemId':250245,'level':321})
assert small['effects'] and large['effects'] and small['effects']!=large['effects']
assert all('<' not in t for t in small['effects'])
assert server.item_effects({'itemId':251229,'level':311})['effects']==[]
try:server.item_effects({'itemId':250245,'level':311,'bonuses':'../secret'})
except ValueError:pass
else:raise AssertionError('invalid input accepted')
print('PASS: localized effects, level-dependent values, plain text, no-effect item and invalid input')

set_item=server.item_effects({'itemId':271474,'level':321})
assert len(set_item['setEffects'])==2 and all('鲜血' in t for t in set_item['setEffects'])
assert '271474|321|' in server.cached_effects()
print('PASS: Blood set descriptions and startup local cache')

expected={62,63,64,65,66,70,71,72,73,102,103,104,105,250,251,252,253,254,255,256,257,258,259,260,261,262,263,264,265,266,267,268,269,270,577,581,1467,1468,1473,1480}
ids=server.GROUPS['raid_token_products'];assert len(ids)==65
specs={}
for iid in ids:
 data=server.item_effects({'itemId':iid,'level':334})
 assert not data.get('error'),(iid,data)
 current=data.get('setEffectsBySpec',{});assert current,(iid,'missing current spec effects')
 for spec,lines in current.items():
  assert len(lines)==2,(iid,spec,lines)
  assert {re.match(r'\((2|4)\)',t)[1] for t in lines}=={'2','4'}
  specs[spec]=lines
assert set(map(int,specs))==expected
for spec,lines in specs.items():
 assert len(lines)==2,(spec,lines)
 assert {re.match(r'\((2|4)\)',t)[1] for t in lines}=={'2','4'}
print('PASS: 65 set items, all 40 specs with both two/four piece effects')
