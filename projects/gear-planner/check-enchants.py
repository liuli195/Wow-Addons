import copy,json,re
from pathlib import Path
import server
m=copy.deepcopy(server.BASE)
for slot,raw in list(m['gear'].items()):
 f=server.gear_fields(raw);f.pop('enchant_id',None);m['gear'][slot]=server.encode(f)
base=server.calculate(m);assert base['complete']
checked=[]
for slot,raw in m['gear'].items():
 for option in server.enchant_options(server.gear_fields(raw)):
  eid=int(option['id'])
  if eid in checked:continue
  assert re.search('[\u4e00-\u9fff]',option['label']),option
  r=server.calculate(server.apply_edit(m,{'slot':slot,'enchant_id':str(eid)}))
  assert r['complete'],(eid,r.get('diagnostic'))
  expected={v['type']:v['amount'] for v in server.ENCHANTS[eid].get('stats',[])}
  for stat in ('crit','haste','mastery','versatility'):
   assert r['values'][stat]-base['values'][stat]==expected.get('vers' if stat=='versatility' else stat,0),(eid,stat,r['values'][stat]-base['values'][stat],expected)
  checked.append(eid)
for slot,eid in [('neck','7967'),('chest','7973'),('main_hand','8612'),('head','8702')]:
 try:server.apply_edit(m,{'slot':slot,'enchant_id':eid})
 except ValueError:pass
 else:raise AssertionError((slot,eid,'incompatible accepted'))
changed=server.apply_edit(m,{'slot':'finger1','enchant_id':'7967'})
restored=server.apply_edit(changed,{'slot':'finger1','enchant_id':''})
assert restored==m
assert len(server.GEAR_ENCHANTS)==100
Path(__file__).with_name('enchant-check-results.json').write_text(json.dumps({'passed':checked,'count':len(checked)},indent=2),encoding='utf-8')
print('PASS',len(checked),'native enchant calculations, rating deltas, Chinese names, remove and invalid slot/weapon rejection')
