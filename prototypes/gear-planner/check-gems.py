import copy,json,re
from pathlib import Path
import server
assert len(server.GEMS)==75
assert all(re.search('[\u4e00-\u9fff]',g['name']) for g in server.GEMS)
m=copy.deepcopy(server.BASE)
for slot,raw in list(m['gear'].items()):
 f=server.gear_fields(raw);f.pop('gem_id',None);m['gear'][slot]=server.encode(f)
base=server.calculate(m);assert base['complete']
results=[]
for g in server.GEMS:
 changed=server.apply_edit(m,{'slot':'neck','gem_id':str(g['id'])})
 r=server.calculate(changed);assert r['complete'],(g['id'],r.get('diagnostic'))
 e=server.ENCHANTS[g['enchantId']]
 expected={x['type']:x['amount'] for x in e.get('stats',[])}
 for stat in ('crit','haste','mastery','versatility'):
  delta=r['values'][stat]-base['values'][stat]
  assert delta==expected.get('vers' if stat=='versatility' else stat,0),(g['id'],stat,delta,expected)
 results.append(g['id'])
# Shared uniqueness across distinct diamond IDs and slots; failed edit never mutates original.
m1=server.apply_edit(m,{'slot':'neck','gem_id':'240983'})
try:server.apply_edit(m1,{'slot':'finger1','gem_id':'240967'})
except ValueError:pass
else:raise AssertionError('duplicate unique diamond accepted')
assert '240967' not in m1['gear']['finger1']
# Two existing prismatic sockets, remove first without shifting the second.
m2=copy.deepcopy(m);f=server.gear_fields(m2['gear']['neck']);f['bonus_id']+='/13750';m2['gear']['neck']=server.encode(f)
m2=server.apply_edit(m2,{'slot':'neck','gem_id':'240894','gemIndex':1})
assert server.gear_fields(m2['gear']['neck'])['gem_id']=='0/240894'
r=server.calculate(m2);assert r['complete'];assert r['values']['haste']-base['values']['haste']==16
try:server.apply_edit(m,{'slot':'chest','gem_id':'240894'})
except ValueError:pass
else:raise AssertionError('socketless item accepted gem')
try:server.apply_edit(m,{'slot':'neck','gem_id':'34220'})
except ValueError:pass
else:raise AssertionError('meta gem accepted')
Path(__file__).with_name('gem-check-results.json').write_text(json.dumps({'passed':results,'count':len(results)},indent=2),encoding='utf-8')
print('PASS: 75 gems with Chinese names and native rating deltas; shared unique limits, multi-socket empty positions, socketless and incompatible rejection')
