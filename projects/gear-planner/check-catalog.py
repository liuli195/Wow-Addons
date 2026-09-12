import json
import server
from pathlib import Path
assert server.CATALOG_COUNT==523
seen=set(); results=[]
base=server.calculate(server.BASE)
for slot,rows in server.CATALOG.items():
 for index,x in enumerate(rows):
  if x['id'] in seen or x['reason'] or x['conversion']:continue
  seen.add(x['id'])
  try:
   expected=base['items'].get(slot,{}).get('ilevel')
   try:model=server.apply_edit(server.BASE,{'slot':slot,'candidate':index})
   except server.ReplacementLevelError as exc:
    expected=exc.alternative_level
    model=server.apply_edit(server.BASE,{'slot':slot,'candidate':index,'acceptLevelChange':expected})
   # Two-handed baseline must be removed when testing a legal off-hand-only item.
   if slot=='off_hand':model['gear'].pop('main_hand',None)
   r=server.calculate(model)
   actual=r.get('items',{}).get(slot,{}).get('ilevel')
   results.append({'id':x['id'],'slot':slot,'ok':r['complete'] and actual==expected,'level':actual,'expected':expected,'error':r.get('diagnostic','')})
  except Exception as e:results.append({'id':x['id'],'ok':False,'error':str(e)})
Path(__file__).with_name('catalog-check-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
bad=[r for r in results if not r['ok']]
print(json.dumps({'catalog':523,'tested':len(results),'failed':bad},ensure_ascii=False),flush=True)
assert not bad
neck=next(i for i,x in enumerate(server.CATALOG['neck']) if x['id']==273781)
m=server.apply_edit(server.BASE,{'slot':'neck','candidate':neck});r=server.calculate(m)
assert r['items']['neck']['ilevel']==base['items']['neck']['ilevel']
r=server.calculate(server.apply_edit(m,{'slot':'neck','level':331}));assert r['items']['neck']['ilevel']==331
print('PASS: requested neck 273781 search, equip and level change')
