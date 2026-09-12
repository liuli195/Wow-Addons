import copy,json
from pathlib import Path
import server
# Every catalog product uses the same source-aware generator and validator.
covered=set(); native=[]
for slot,rows in server.CATALOG.items():
 for index,item in enumerate(rows):
  if item['conversion'] or item['id'] in covered:continue
  covered.add(item['id']);options=server.level_options(server.gear_fields(item['value']))
  assert options,item['id']
  assert len({o['key'] for o in options})==len(options)
  if item['reason']:continue
  try:m=server.apply_edit(server.BASE,{'slot':slot,'candidate':index})
  except server.ReplacementLevelError as exc:
   m=server.apply_edit(server.BASE,{'slot':slot,'candidate':index,'acceptLevelChange':exc.alternative_level})
  for option in options:
   changed=server.apply_edit(m,{'slot':slot,'levelVariant':option['key']})
   f=server.gear_fields(changed['gear'][slot])
   assert server.current_level_key(f,server.level_options(f))==option['key'],(item['id'],option)
  if item['id'] in (273781,158366,268213,271473,237846,240949,250244):
   for option in options:
    r=server.calculate(server.apply_edit(m,{'slot':slot,'levelVariant':option['key']}))
    assert r['complete'],(item['id'],option,r.get('diagnostic'))
    assert r['items'][slot]['ilevel']==option['level'],(item['id'],option,r['items'][slot]['ilevel'])
    native.append((item['id'],option['key'],option['level']))
  try:server.apply_edit(m,{'slot':slot,'levelVariant':'upgrade:12817'})
  except ValueError:pass
  else:raise AssertionError(('unrelated adventurer accepted',item['id']))
assert len(covered)==471
f={'id':'273781','bonus_id':'12854'}
opts=server.level_options(f)
assert {305,308,311} <= {o['level'] for o in opts}
assert len([o for o in opts if o['level']==305])==2
# Source redirects retain the original source's legal levels.
f={'id':'271473','redirected_base_stats':'273776','bonus_id':'12846/13662'}
assert server.level_options(f)==server.level_options({'id':'273776','bonus_id':'12846/13662'})
Path(__file__).with_name('level-check-results.json').write_text(json.dumps({'catalogProducts':len(covered),'nativeCases':native},indent=2),encoding='utf-8')
print('PASS:',len(covered),'catalog products,',len(native),'native variants; duplicate levels retain track; invalid track rejected; redirect preserved')
