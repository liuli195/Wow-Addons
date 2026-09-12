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

# Every specialization uses its own upstream loot mask; preserve candidate indices.
for spec,spec_id in server.DK_SPECS.items():
 key='deathknight:'+spec
 rows=[x for x in server.CATALOG['main_hand'] if not x['reason'] and not x['fitReasonsBySpec'][key] and not x['conversion']]
 assert rows
 for row in rows:
  item=server.ITEMS[row['id']]
  assert not item.get('specs') or spec_id in item['specs']
 if spec=='frost':assert any(server.ITEMS[x['id']]['inventoryType']!=17 for x in rows)
 else:assert all(server.ITEMS[x['id']]['inventoryType']==17 for x in rows)
print('PASS: three-spec candidate masks and frost one-handed weapons')

for spec in server.CLASS_SPECS['demonhunter']:
 key='demonhunter:'+spec
 rows=[x for x in items.values() if not x['fitReasonsBySpec'][key]]
 assert rows
 assert any(server.ITEMS[x['id']]['itemClass']==2 for x in rows)
 for row in rows:
  item=server.ITEMS[row['id']]
  if item.get('specs'):assert server.SPEC_IDS[key] in item['specs']
  if item['itemClass']==4 and item['inventoryType'] in server.ARMOR_SLOTS:assert item['itemSubClass']==2
  if item['itemClass']==2:
   assert item['itemSubClass'] in (0,7,9,13,15)
   assert not server.RUNE_IDS & {int(e['id']) for e in server.enchant_options(row['fields'],'demonhunter')}
print('PASS: demon hunter three specs, leather, weapons, stat masks and no runeforging')

for spec in server.CLASS_SPECS['rogue']:
 key='rogue:'+spec
 for slot in ('main_hand','off_hand'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec'][key] and not x['conversion']]
  assert rows,(spec,slot)
  types={server.ITEMS[x['id']]['itemSubClass'] for x in rows}
  if spec=='assassination' or (spec=='subtlety' and slot=='main_hand'):assert types=={15},(spec,slot,types)
  if spec=='outlaw' and slot=='main_hand':assert 15 not in types
  if spec=='outlaw' and slot=='off_hand':assert 15 in types
  for row in rows:assert not server.RUNE_IDS & {int(e['id']) for e in server.enchant_options(row['fields'],'rogue')}
 for row in server.CATALOG['chest']:
  if not row['fitReasonsBySpec'][key]:assert server.ITEMS[row['id']]['itemSubClass']==2
print('PASS: rogue leather, three-spec weapons including outlaw off-hand daggers and no runeforging')

for key in [cls+':'+spec for cls in ('warlock','mage') for spec in server.CLASS_SPECS[cls]]:
 cls,spec=key.split(':')
 for slot in ('main_hand','off_hand','chest'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec'][key] and not x['conversion']]
  assert rows,(spec,slot)
  if slot=='main_hand':
   inventory_types={server.ITEMS[x['id']]['inventoryType'] for x in rows}
   assert 17 in inventory_types and inventory_types & {13,21,26}
  for row in rows:
   item=server.ITEMS[row['id']]
   if item.get('specs'):assert server.SPEC_IDS[key] in item['specs']
   if slot=='off_hand':assert item['inventoryType']==23
   if slot=='chest':assert item['itemSubClass']==1
   if slot=='main_hand':assert item['itemSubClass'] in (7,10,15,19)
   assert not server.RUNE_IDS & {int(e['id']) for e in server.enchant_options(row['fields'],cls)}
assert server.equip_reason({'itemClass':4,'inventoryType':14,'itemSubClass':6},'warlock')
assert server.equip_reason({'itemClass':4,'inventoryType':5,'itemSubClass':2},'warlock')
print('PASS: warlock and mage six specs, cloth, intellect loot masks, staff/one-hand/held off-hand and no runeforging')

assert server.CLASS_SPECS['mage']['frost']==64 and server.CLASS_SPECS['deathknight']['frost']==251
for row in server.CATALOG['main_hand']:
 if server.ITEMS[row['id']]['itemSubClass']==10 and not row['fitReasonsBySpec']['mage:frost']:assert row['fitReasonsBySpec']['deathknight:frost']
print('PASS: mage and death knight frost candidates remain separate')

for spec in server.CLASS_SPECS['paladin']:
 key='paladin:'+spec
 for slot in ('chest','main_hand','off_hand'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec'][key] and not x['conversion']]
  if spec=='retribution' and slot=='off_hand':assert not rows;continue
  assert rows,(spec,slot)
  for row in rows:
   item=server.ITEMS[row['id']]
   if slot=='chest':assert item['itemSubClass']==4
   if slot=='off_hand':assert item['inventoryType']==14
   if slot=='main_hand':assert (item['inventoryType']==17)==(spec=='retribution')
   if item.get('specs'):assert server.SPEC_IDS[key] in item['specs']
assert not server.fit_reason(server.ITEMS[237829],'holy','chest','paladin')
# Official data_enums.hh: 72=str/agi, 73=agi/int, 74=str/int.
for stat,holy,agility in ((72,False,True),(73,True,True),(74,True,False),(71,True,True)):
 item={'itemClass':4,'itemSubClass':0,'inventoryType':12,'stats':[{'id':stat}]}
 assert (not server.fit_reason(item,'holy','trinket1','paladin'))==holy
 assert (not server.fit_reason(item,'havoc','trinket1','demonhunter'))==agility
print('PASS: paladin plate, three-spec masks, shields, two-hand and hybrid primary stat enums')

for spec in server.CLASS_SPECS['hunter']:
 key='hunter:'+spec
 for slot in ('chest','main_hand','off_hand'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec'][key] and not x['conversion']]
  if slot=='off_hand' and spec!='survival':assert not rows;continue
  assert rows,(spec,slot)
  for row in rows:
   item=server.ITEMS[row['id']]
   if item.get('specs'):assert server.SPEC_IDS[key] in item['specs']
   if slot=='chest':assert item['itemSubClass']==3
   else:assert (item['itemSubClass'] in (2,3,18))==(spec!='survival')
   assert not server.RUNE_IDS & {int(e['id']) for e in server.enchant_options(row['fields'],'hunter')}
assert not server.equip_reason({'itemClass':2,'itemSubClass':10,'inventoryType':17},'hunter')
for subtype in (4,5,19):assert server.equip_reason({'itemClass':2,'itemSubClass':subtype,'inventoryType':17},'hunter')
for iid in (159637,159643,268200,158370):assert server.occupies_both_hands(server.ITEMS[iid])
for iid in (158714,159136):assert not server.occupies_both_hands(server.ITEMS[iid])
assert not server.occupies_both_hands({'itemClass':2,'itemSubClass':19,'inventoryType':26}) # wand is not a gun
print('PASS: hunter mail, agility, three-spec masks, ranged/melee, two-hand and dual wield candidates')

for spec in server.CLASS_SPECS['shaman']:
 key='shaman:'+spec
 for slot in ('chest','main_hand','off_hand'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec'][key] and not x['conversion']]
  assert rows,(spec,slot)
  for row in rows:
   item=server.ITEMS[row['id']]
   if item.get('specs'):assert server.SPEC_IDS[key] in item['specs']
   if slot=='chest':assert item['itemSubClass']==3
   elif spec=='enhancement':assert item['itemClass']==2 and item['itemSubClass'] in (0,4,13) and item['inventoryType'] in (13,21,22)
   elif slot=='off_hand':assert item['inventoryType'] in (14,23)
   assert not server.RUNE_IDS & {int(e['id']) for e in server.enchant_options(row['fields'],'shaman')}
for subtype in (6,7,8,19):assert server.equip_reason({'itemClass':2,'itemSubClass':subtype,'inventoryType':13},'shaman')
assert server.equip_reason({'itemClass':4,'itemSubClass':4,'inventoryType':5},'shaman')
for iid in (159664,159667):assert not server.equip_reason(server.ITEMS[iid],'shaman')
print('PASS: shaman mail, intellect/agility masks, enhancement dual wield, caster staff/shield/held offhand')

for spec in server.CLASS_SPECS['warrior']:
 for slot in ('main_hand','off_hand','chest'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec']['warrior:'+spec] and not x['conversion']]
  if spec=='arms' and slot=='off_hand':assert not rows;continue
  assert rows,(spec,slot)
  for row in rows:
   item=server.ITEMS[row['id']]
   if slot=='chest':assert item['itemSubClass']==4
   elif spec=='fury':assert item['inventoryType']==17 and item['itemSubClass'] in (1,5,8)
   elif slot=='off_hand':assert item['inventoryType']==14
print('PASS: warrior three specs, plate, fury two-handed offhand, protection shield')

for spec in server.CLASS_SPECS['priest']:
 for slot in ('main_hand','off_hand','chest'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec']['priest:'+spec] and not x['conversion']]
  assert rows,(spec,slot)
  for row in rows:
   i=server.ITEMS[row['id']]
   if slot=='chest':assert i['itemSubClass']==1
   elif slot=='off_hand':assert i['inventoryType']==23
   else:assert i['itemSubClass'] in (4,10,15,19)
print('PASS: priest cloth, intellect, mace/staff/dagger/wand and held offhand')

for spec in server.CLASS_SPECS['druid']:
 for slot in ('chest','main_hand','off_hand'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec']['druid:'+spec] and not x['conversion']]
  if spec in ('feral','guardian') and slot=='off_hand':assert not rows;continue
  assert rows,(spec,slot)
  for row in rows:
   i=server.ITEMS[row['id']]
   if slot=='chest':assert i['itemSubClass']==2
   elif slot=='off_hand':assert i['inventoryType']==23
   else:assert i['itemSubClass'] in (4,5,6,10,13,15)
print('PASS: druid four specs, leather, intellect/agility and no weapon dual wield')

for subtype in (3,4):assert server.equip_reason({'itemClass':4,'itemSubClass':subtype,'inventoryType':5},'druid')

for spec in server.CLASS_SPECS['monk']:
 for slot in ('chest','main_hand','off_hand'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec']['monk:'+spec] and not x['conversion']]
  assert rows,(spec,slot)
  for row in rows:
   i=server.ITEMS[row['id']]
   if slot=='chest':assert i['itemSubClass']==2
   elif slot=='off_hand' and spec=='mistweaver':assert i['inventoryType']==23
   else:assert i['itemClass']==2 and i['itemSubClass'] in (0,4,6,7,10,13)
for subtype in (3,4):assert server.equip_reason({'itemClass':4,'itemSubClass':subtype,'inventoryType':5},'monk')
print('PASS: monk leather, spec masks, caster offhand and physical weapon combinations')

for spec in server.CLASS_SPECS['evoker']:
 for slot in ('chest','main_hand','off_hand'):
  rows=[x for x in server.CATALOG[slot] if not x['fitReasonsBySpec']['evoker:'+spec] and not x['conversion']]
  assert rows,(spec,slot)
  for row in rows:
   i=server.ITEMS[row['id']]
   if slot=='chest':assert i['itemSubClass']==3
   elif slot=='off_hand':assert i['inventoryType']==23
   else:assert i['itemSubClass'] in (0,4,7,10,13,15)
assert server.equip_reason({'itemClass':4,'itemSubClass':4,'inventoryType':5},'evoker')
assert server.equip_reason({'itemClass':4,'itemSubClass':6,'inventoryType':14},'evoker')
print('PASS: evoker mail, intellect, three spec masks, staff/single/held offhand')
