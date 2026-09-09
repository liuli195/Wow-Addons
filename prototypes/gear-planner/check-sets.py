import json,re
from pathlib import Path
import server
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
