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
