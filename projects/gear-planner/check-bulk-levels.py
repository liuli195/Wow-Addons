import copy
import server
base=copy.deepcopy(server.BASE)
initial=server.calculate(base)
assert initial['complete']
for mode in ('minimum','maximum'):
    changed=server.apply_edit(base,{'bulkLevel':mode,'skipUnsupported':True})
    result=server.calculate(changed)
    assert result['complete']
    for slot,x in result['items'].items():
        levels=initial['items'][slot]['levels']
        if levels:assert x['ilevel']==(min if mode=='minimum' else max)(levels),(slot,x['ilevel'],levels)
        for key in ('gem_id','enchant_id','crafted_stats'):
            assert x['fields'].get(key)==initial['items'][slot]['fields'].get(key)
    restored=server.calculate(server.apply_edit(changed,{'bulkLevel':'restore','original':base}))
    assert restored['complete']
    assert restored['values']==initial['values'],(restored['values'],initial['values'])
try:
    server.apply_edit(base,{'bulkLevel':999})
    raise AssertionError('unsupported levels must need approval')
except ValueError:pass
assert server.apply_edit(base,{'bulkLevel':999,'skipUnsupported':True})==base
changed=server.apply_edit(base,{'bulkLevel':334,'skipUnsupported':True})
assert changed['gear']['main_hand']==base['gear']['main_hand']
result=server.calculate(changed);assert result['complete']
for slot,x in initial['items'].items():
    if 334 in x['levels']:assert result['items'][slot]['ilevel']==334
assert base==server.BASE
print('PASS: min/max, exact levels, unsupported confirmation, no partial mutation, restore, gems/enchants retained')

visible={str(x['id']) for rows in server.CATALOG.values() for x in rows if not x['fitReason'] and not x['reason'] and not x['conversion']}
assert visible<=server.FILTER_STATS.keys()
# Restore levels after a separate enchant change, without reverting that change.
changed=server.apply_edit(base,{'bulkLevel':'maximum','skipUnsupported':True})
changed=server.apply_edit(changed,{'slot':'head','enchant_id':''})
restored=server.apply_edit(changed,{'bulkLevel':'restore','original':base})
assert 'enchant_id' not in server.gear_fields(restored['gear']['head'])
print('PASS: native filter coverage and level restore preserves later enchant edits')
