import copy
import server

def replace(model,patch):
    try:return server.apply_edit(model,patch)
    except server.ReplacementLevelError as e:return server.apply_edit(model,{**patch,'acceptLevelChange':e.alternative_level})

checked=[]
for slot,_ in server.SLOTS:
    rows=[(i,x) for i,x in enumerate(server.CATALOG[slot]) if not x['reason'] and not x['fitReason'] and not x['conversion']]
    if len(rows)<2:continue
    index,item=rows[0]
    m=copy.deepcopy(server.BASE)
    f=server.gear_fields(item['value']);f['bonus_id']='/'.join(filter(None,[f.get('bonus_id',''),'6652']))
    original=server.encode(f);m['gear'][slot]=original
    assert index in server.original_matches(m,{slot:original})[slot],(slot,'initial')
    other_index=next(i for i,x in rows if x['id']!=item['id'])
    changed=replace(m,{'slot':slot,'candidate':other_index})
    assert index in server.original_matches(changed,{slot:original})[slot],(slot,'after replacement')
    checked.append(slot);print('PASS',slot,flush=True)
# Real tertiary-stat variants must stay separate both before and after switching.
base=copy.deepcopy(server.BASE);value=base['gear']['head']
assert not server.original_matches(base,{'head':value})['head']
i=next(i for i,x in enumerate(server.CATALOG['head']) if x['id']==239050)
changed=replace(base,{'slot':'head','candidate':i})
assert not server.original_matches(changed,{'head':value})['head']
print('PASS: stable equivalent merges across',len(checked),'supported slots; real speed variant stays distinct')
