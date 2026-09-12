"""Minimal checks for the prototype's real adapter and input trust boundary."""
import copy
import json
import server

base=server.calculate(server.BASE)
assert base['complete'] and base['values']['strength']==2341 and base['values']['ilevel']==315.75
gem_model=server.apply_edit(server.BASE,{'slot':'neck','gem_id':''})
gem=server.calculate(gem_model)
assert base['values']['haste']-gem['values']['haste']==16
restored=server.calculate(server.apply_edit(gem_model,{'slot':'neck','gem_id':'240894'}))
assert restored['values']==base['values']
crafted=server.calculate(server.apply_edit(server.BASE,{'slot':'main_hand','crafted':'32/36'}))
assert crafted['values']['haste']-base['values']['haste']==99
assert base['values']['mastery']-crafted['values']['mastery']==99
rank=server.calculate(server.apply_edit(server.BASE,{'slot':'shoulder','level':331}))
assert rank['items']['shoulder']['ilevel']==331
other=server.calculate(server.apply_edit(server.BASE,{'slot':'finger1','candidate':next(i for i,x in enumerate(server.CATALOG['finger1']) if x['id']==158366)}))
assert other['complete'] and other['items']['finger1']['id']==158366
bad=copy.deepcopy(server.BASE); bad['gear']['neck']=',id=999999999'
assert not server.calculate(bad)['complete']
for text in ['deathknight=x\ninput=private.txt','deathknight=x\nhead=,id=1,foo=1','deathknight=x\nhead=,id=1\nhead=,id=2']:
    try: server.parse_import(text)
    except ValueError: pass
    else: raise AssertionError('unsafe or unsupported input accepted')
print('PASS: baseline, edit/restore, crafted normalization, rank, alternate gear, unknown item and unsafe inputs')

exported=json.loads(json.dumps({'format':'gear-planner-prototype/1','model':server.BASE}))
assert server.calculate(exported['model'])['values']==base['values']
print('PASS: JSON configuration round trip')
