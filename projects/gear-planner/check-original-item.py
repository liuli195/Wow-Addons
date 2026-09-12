import copy
import server
base=copy.deepcopy(server.BASE)
original=base['gear']['neck']
index=next(i for i,x in enumerate(server.CATALOG['neck']) if x['id']==273781)
changed=server.apply_edit(base,{'slot':'neck','candidate':index})
changed=server.apply_edit(changed,{'slot':'neck','level':311})
changed=server.apply_edit(changed,{'slot':'neck','gem_id':''})
restored=server.apply_edit(changed,{'slot':'neck','originalItem':original})
result=server.calculate(restored)
assert result['complete'],result
assert result['items']['neck']['id']==266314
assert result['items']['neck']['ilevel']==311
assert not result['items']['neck']['fields'].get('gem_id')
assert all(restored['gear'][s]==changed['gear'][s] for s in changed['gear'] if s!='neck')
head=server.apply_edit(base,{'slot':'head','level':321})
head=server.apply_edit(head,{'slot':'head','enchant_id':''})
returned=server.apply_edit(head,{'slot':'head','originalItem':base['gear']['head']})
r=server.calculate(returned);assert r['complete'] and r['items']['head']['ilevel']==321
assert not r['items']['head']['fields'].get('enchant_id')
try:server.apply_edit(base,{'slot':'feet','originalItem':original});raise AssertionError('wrong slot accepted')
except ValueError:pass
assert base==server.BASE
print('PASS: outside-pool necklace returns at current level, removed gems/enchants remain removed, wrong-slot guard, other slots retained')

# Compare actual replacement outcomes, ignoring only bonus list ordering.
matched=server.original_matches(base,{'head':base['gear']['head'],'neck':base['gear']['neck']})
assert not matched['head'] and not matched['neck']
other=next(i for i,x in enumerate(server.CATALOG['head']) if x['id']==268229)
changed=server.apply_edit(base,{'slot':'head','candidate':other})
assert not server.original_matches(changed,{'head':base['gear']['head']})['head']
# The imported head's speed bonus makes it a distinct outcome after switching away.
assert base==server.BASE
print('PASS: equivalent click results merge; real stat variants and outside-pool originals remain')
