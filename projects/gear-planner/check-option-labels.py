import re
import server
for g in server.GEMS:
 assert not re.search('[a-zA-Z]',g['label']),g['label']
 assert str(g['id']) not in g['label'],g['label']
seen=set()
for item in server.ITEMS.values():
 for option in server.enchant_options({'id':str(item['id'])}):
  seen.add(int(option['id']))
  assert not re.search('[a-zA-Z]',option['label']),option
  assert not option['label'].startswith('附魔'),option
assert seen=={e['id'] for e in server.GEAR_ENCHANTS},seen
print('PASS: all 75 gem labels and 100 enchant labels Chinese; no gem IDs or enchant slot prefixes')
