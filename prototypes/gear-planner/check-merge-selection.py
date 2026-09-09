import copy
import server
base=copy.deepcopy(server.BASE)
original={'head':base['gear']['head']}
index=next(i for i,x in enumerate(server.CATALOG['head']) if x['id']==251229)
a=server.original_matches(base,original)
assert a['_selected']['head']==['original'],a['_selected']['head']
changed=server.apply_edit(base,{'slot':'head','candidate':index})
b=server.original_matches(changed,original)
assert b['_selected']['head']==[index],b['_selected']['head']
returned=server.apply_edit(changed,{'slot':'head','originalItem':original['head']})
c=server.original_matches(returned,original)
assert c['_selected']['head']==['original']
assert base==server.BASE
print('PASS: distinct same-ID variants only highlight the equivalent equipped entry, in both directions')
