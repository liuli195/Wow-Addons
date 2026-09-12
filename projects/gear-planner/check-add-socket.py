import server
base=server.calculate(server.BASE)
for slot in ('head','wrist','waist'):
 f=server.gear_fields(server.BASE['gear'][slot]);assert server.gem_sockets(f)==['PRISMATIC']
 m=server.apply_edit(server.BASE,{'slot':slot,'gem_id':'240904'})
 r=server.calculate(m);assert r['complete'];assert r['values']['crit']==base['values']['crit']+17
 assert len(server.gem_sockets(server.gear_fields(m['gear'][slot])))==1
 try:server.apply_edit(m,{'slot':slot,'gem_id':'240904','gemIndex':1})
 except ValueError:pass
 else:raise AssertionError('second socket accepted')
 restored=server.calculate(server.apply_edit(m,{'slot':slot,'gem_id':''}));assert restored['values']==base['values']
assert not server.gem_sockets({'id':'45585'})
print('PASS: head/wrist/waist addable sockets, native gem stats, one socket maximum, removal')
