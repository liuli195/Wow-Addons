"""Derive research inventory from existing data, cross-check KeystoneLoot without copying its tables."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parents[3] / '.local/gear-planner-research'
DATA = HERE.parents[1] / '.tools/gear-planner-research'
def read(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))
items = {x['id']: x for x in read('equippable-items.json')}
previous = json.loads((HERE / 'data-source-results.json').read_text())
rotation = set(previous['rotation_ids'])
raids = set(previous['raid_ids'])
def combat(item):
    return item.get('itemClass') in (2, 4) and item.get('inventoryType', 0) > 0 and not item.get('cosmetic')
mplus = {i for i, x in items.items() if combat(x) and any(s.get('instanceId') == -1 and s.get('encounterId') in rotation for s in x.get('sources', []))}
raid_raw = {i for i, x in items.items() if any(s.get('instanceId') in raids for s in x.get('sources', []))}
raid_direct = {i for i in raid_raw if combat(items[i])}
tokens = {i for i in raid_raw if items[i].get('contains')}
tier = {n for i in tokens for n in items[i]['contains'] if n in items and combat(items[n])}
crafted = {i for i, x in items.items() if combat(x) and x.get('quality') == 4 and x.get('profession') and x.get('expansion') == 11 and any(s.get('instanceId') == -88 for s in x.get('sources', []))}
conversions = read('item-conversions.json')['13']['items']
conversion_ids = {x['id'] for x in conversions if combat(x)}
conversion_extra = conversion_ids - tier
base = mplus | raid_direct | tier | crafted
kl = DATA / 'keystoneloot/data'
kl_mplus = {int(n) for group in re.findall(r'lootTable = \{ ([\d, ]+) \}', (kl / 'dungeons.lua').read_text()) for n in re.findall(r'\d+', group)}
kl_raid = {int(n) for group in re.findall(r'\[(?:14|15|16|17)\] = \{ ([\d, ]+) \}', (kl / 'raids.lua').read_text()) for n in re.findall(r'\d+', group)}
assert mplus == {i for i in kl_mplus if i in items and combat(items[i])}
kl_tier = {int(n) for n in re.findall(r'^    \[(\d+)\]', (kl / 'catalyst.lua').read_text(), re.M)}
assert tier == kl_tier == {x['id'] for x in conversions if x.get('itemSetId')}
assert len(mplus) == 207 and len(raid_direct) == 101 and len(tier) == 65 and len(crafted) == 98
assert len(base) == 471 and len(conversion_extra) == 52
bonuses = read('bonuses.json')
assert bonuses['12854']['quality'] == 4 and bonuses['12854']['upgrade']['seasonId'] == 37
assert bonuses['12854']['itemLevel']['amount'] == 334
crafting = read('crafting.json')
for i in crafted:
    slots = [crafting['slots'][str(s['id'])] for s in items[i]['profession']['optionalCraftingSlots']]
    assert any(274476 in s['reagentIds'] for s in slots), i
    assert any(3446 in s['reagentIds'] for s in slots), i
crest = next(x for x in crafting['reagents'] if x['id'] == 3446 and x['reagentType'] == 'currency')
assert crest['craftingBonusIds'] == [13836] and crest['craftingPrereqs'][0]['itemId'] == 274476
assert bonuses['13836']['itemLevel']['amount'] + bonuses['12497']['levelOffset']['amount'] == 331
groups = {'mplus': mplus, 'raid_direct': raid_direct, 'raid_token_products': tier, 'crafted_epic': crafted, 'non_set_conversion_forms': conversion_extra}
result = {'wow_build': '12.1.0.69587', 'keystoneloot_commit': 'ea786c41a1834fbc5d5bdffc849d85416ca81477',
          'counts': {k: len(v) for k,v in groups.items()}, 'base_product_count': len(base),
          'all_product_and_conversion_count': len(base | conversion_extra),
          'raid_non_boss_products': sorted(raid_direct - kl_raid),
          'excluded_raid_tokens': sorted(tokens),
          'groups': {k: sorted(v) for k,v in groups.items()},
          'records': [{key: items[i][key] for key in ('id','name','itemClass','itemSubClass','inventoryType','allowableClasses') if key in items[i]} for i in sorted(base | conversion_extra)],
          'hashes': {f: hashlib.sha256((DATA / f).read_bytes()).hexdigest() for f in ['equippable-items.json','bonuses.json','crafting.json','item-conversions.json','bonus-upgrade-sets.json']},
          'limits': ['No complete Chinese name verification', 'No all-item in-game acquisition verification', 'Upgrade track and catalyst eligibility must be retained per variant']}
(HERE / 'epic-catalog-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k in ('counts','base_product_count','all_product_and_conversion_count','raid_non_boss_products')},indent=2))
