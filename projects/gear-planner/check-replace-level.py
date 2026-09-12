import copy
import server
m=copy.deepcopy(server.BASE)
i=next(i for i,x in enumerate(server.CATALOG['shoulder']) if x['id']==237835)
try:server.apply_edit(m,{'slot':'shoulder','candidate':i})
except server.ReplacementLevelError as e:assert e.alternative_level==331
else:raise AssertionError('unconfirmed level change')
assert m==server.BASE
changed=server.apply_edit(m,{'slot':'shoulder','candidate':i,'acceptLevelChange':331})
r=server.calculate(changed);assert r['complete'];assert r['items']['shoulder']['ilevel']==331
assert r['items']['shoulder']['fields']['enchant_id']=='7973'
try:server.apply_edit(m,{'slot':'shoulder','candidate':i,'acceptLevelChange':334})
except server.ReplacementLevelError:pass
else:raise AssertionError('invalid level approval')
print('PASS: replacement requires exact fallback approval, 331 crafted shoulder calculates and keeps enchant')
