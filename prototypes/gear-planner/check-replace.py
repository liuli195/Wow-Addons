import copy
import server

def replace(m,slot,iid):
 return server.apply_edit(m,{'slot':slot,'candidate':next(i for i,x in enumerate(server.CATALOG[slot]) if x['id']==iid)})
for slot,iid in [('finger1',158366),('head',251229),('main_hand',237846)]:
 m=replace(server.BASE,slot,iid)
 old=server.gear_fields(server.BASE['gear'][slot]);new=server.gear_fields(m['gear'][slot])
 for key in ('gem_id','enchant_id'):assert new.get(key)==old.get(key)
 r=server.calculate(m);assert r['complete'];assert r['values']['ilevel']==315.75
# Compare dropped vs crafted ring at shared 318 ilvl, preserving socket and unique gem.
m=server.apply_edit(server.BASE,{'slot':'finger1','level':318})
n=replace(m,'finger1',240949)
r=server.calculate(n);assert r['complete'];assert r['items']['finger1']['ilevel']==318
for key in ('gem_id','enchant_id'):assert server.gear_fields(n['gear']['finger1'])[key]==server.gear_fields(m['gear']['finger1'])[key]
# Missing shared level fails atomically; original model remains intact.
original=server.apply_edit(server.BASE,{"slot":"finger1","level":334})
before=copy.deepcopy(original)
try:replace(original,'finger1',240949)
except ValueError as exc:assert '装等' in str(exc)
else:raise AssertionError('unsupported crafted level accepted')
assert original==before
# Same-ID replacement also follows full rules, preserving configured level/gems/enchants.
same=replace(m,'finger1',273792)
assert server.calculate(same)['items']['finger1']['ilevel']==318
for key in ('gem_id','enchant_id'):assert server.gear_fields(same['gear']['finger1']).get(key)==server.gear_fields(m['gear']['finger1']).get(key)
print('PASS: same ilvl/gems/enchants, dropped-to-crafted replacement, same-ID replacement and atomic incompatible-level rejection')
