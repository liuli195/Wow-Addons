import collections,json
from pathlib import Path
import server
items={x['id']:x for rows in server.CATALOG.values() for x in rows}
assert len(items)==523
assert len(server.GROUPS['crafted_epic'])==98
assert not items[237829]['fitReason']
for iid in (239655,244570,244578,244609,244613):
 assert items[iid]['fitReason'] and not items[iid]['reason'],iid
assert items[244609]['armorType']=='锁甲'
visible=[x for x in items.values() if not x['fitReason']]
for x in visible:
 item=server.ITEMS[x['id']]
 if item['itemClass']==4 and item['inventoryType'] in server.ARMOR_SLOTS:assert item['itemSubClass']==4
 if item['itemClass']==2:assert item['inventoryType']==17
 if item.get('specs'):assert 250 in item['specs']
assert not items[273781]['fitReason'] and not items[158366]['fitReason']
assert items[158369]['fitReason'] # caster weapon
assert not items[250244]['fitReason'] # statless tank trinket retained
assert not items[250228]['fitReason'] # missing spec list is not exclusion
assert not items[237846]['fitReason'] # crafted two-handed strength weapon
assert len([x for x in server.CATALOG['chest'] if x['crafted'] and not x['fitReason']])==1
report={'all':len(items),'currentCandidates':len(visible),'excludedFromDefault':dict(collections.Counter(x['fitReason'] for x in items.values() if x['fitReason']))}
Path(__file__).with_name('fit-check-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(report)
print('PASS: full pool preserved; armor, weapons, primary stats, loot specialization and missing metadata checked')
