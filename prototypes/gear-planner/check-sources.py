import server
crafted=server.equipment_sources({'id':'237835'});assert crafted['summary']=='制作 · 锻造'
drop=server.equipment_sources({'id':'250245'});assert '虚空之痕竞技场' in drop['summary']
tier=server.equipment_sources({'id':'271474'});assert tier['summary']=='团本 · 烈毒之渊' and tier['details']
assert all('兑换物' not in d and '对应套装成品' not in d for d in tier['details'])
converted=server.equipment_sources(server.gear_fields(server.BASE['gear']['shoulder']));assert converted['summary'].startswith('催化转化')
unknown=server.equipment_sources({'id':'999999999'});assert '来源待确认' in unknown['summary']
result=server.calculate(server.BASE);assert result['complete'] and result['items']['head']['sourceInfo']['details']
print('PASS: dungeon, crafted, raid token, redirected and unknown sources; calculation metadata')

# Cover the whole raid pool, including all classes' token products.
raid_ids=server.GROUPS['raid_direct'] | server.GROUPS['raid_token_products']
for iid in raid_ids:
    info=server.equipment_sources({'id':str(iid)})
    text=' '.join([info['summary'],*info['details']])
    assert '待补' not in text and '待确认' not in text,(iid,info)
    assert any(name in info['summary'] for name in ('潮缚石窟','烈毒之渊')),(iid,info)
for (instance_id,eid),encounter in server.ENCOUNTERS.items():
    if instance_id in (1317,1320) and not encounter.get('trash'):
        assert eid in server.ENCOUNTER_NAMES,(instance_id,eid)
print(f'PASS: {len(raid_ids)} raid items, 2 raid names and 9 encounter names localized')

for iid in server.GROUPS['mplus']:
    info=server.equipment_sources({'id':str(iid)})
    assert info['details']==info['summary'].split(' / '),(iid,info)
print('PASS: all Mythic+ sources show dungeon names only')

all_ids=server.GROUPS['mplus']|server.GROUPS['raid_direct']|server.GROUPS['raid_token_products']
for iid in all_ids:
    text=str(server.equipment_sources({'id':str(iid)}))
    assert '待补' not in text and '待确认' not in text,(iid,text)
assert server.INSTANCE_NAMES[1309]=='夺目谷'
print(f'PASS: all {len(all_ids)} dungeon and raid products have localized source names')
