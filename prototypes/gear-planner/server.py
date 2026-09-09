"""Throwaway, loopback-only Gear Planner prototype. No game or account access."""
import copy
from functools import lru_cache
import hashlib
import html
import urllib.request
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit, urlencode, parse_qs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / '.tools/gear-planner-research'
RESEARCH = HERE / 'fixtures'
EXE = DATA / 'simc-1210.01.c1935b9-win64/simc.exe'
VERSION = '12.1.0.69587 · c1935b9'
PORT = 8765
TOKEN = secrets.token_urlsafe(24)
LOCK = threading.Lock()
SLOTS = [('head','头部'),('neck','颈部'),('shoulder','肩部'),('back','背部'),('chest','胸部'),('wrist','手腕'),('hands','手部'),('waist','腰部'),('legs','腿部'),('feet','脚部'),('finger1','戒指一'),('finger2','戒指二'),('trinket1','饰品一'),('trinket2','饰品二'),('main_hand','主手'),('off_hand','副手')]
SLOT_KEYS = {s for s,_ in SLOTS} | {'shirt','tabard'}
ALIASES = {'shoulders':'shoulder','wrists':'wrist'}
FIELDS = {'id','bonus_id','ilevel','enchant_id','gem_id','gem_bonus_id','crafted_stats','crafting_quality','content_tuning','redirected_base_stats','drop_level'}
ITEMS = {x['id']:x for x in json.loads((DATA/'equippable-items.json').read_text())}
BONUSES = json.loads((DATA/'bonuses.json').read_text())
NAMES = dict(zip([251229,266314,271472,272226,273787,237834,155970,159418,271473,273777,273792,159459,250245,250228,237846,240949,158366],['掠食者面甲','新手争斗者的项链','灾厄墓骑绞架肩铠','雾猎者罩衫','陈旧的交织鳞甲','破法者的护腕','孤立护手','致命净化束腰','灾厄墓骑护腿','防毒踏靴','阿曼尼督军的指环','仪式束缚者之戒','虫群之瘤','共鸣咆哮石','血骑士的战剑','精工辛多雷指环','充能沙石指环']))

# User-confirmed names take precedence over public localization cache.
if (HERE/'names-zhCN.json').exists():
    for iid,record in json.loads((HERE/'names-zhCN.json').read_text(encoding='utf-8'))['items'].items():
        if record.get('name') and (re.search('[\u4e00-\u9fff]',record['name']) or (iid=='268477' and record['name']=='P.O.W. x3')):NAMES.setdefault(int(iid),record['name'])

ALL_GEMS={str(g['id']):g for g in json.loads((DATA/'gems.json').read_text())}
ENCHANTS={e['id']:e for e in json.loads((DATA/'enchantments-all.json').read_text())}
GEM_STATS={'crit':'暴击','haste':'急速','mastery':'精通','vers':'全能','stragiint':'主属性','stamina':'耐力'}
GEMS=[]
for gid,g in ALL_GEMS.items():
    e=ENCHANTS.get(g['enchantId'],{})
    if e.get('expansion')!=11:continue
    name=NAMES.get(int(gid),g['name']);quality=e.get('craftingQuality')
    stats=' / '.join(str(v['amount'])+' '+GEM_STATS.get(v['type'],v['type']) for v in e.get('stats',[]))
    label=name+((' · 品质 '+str(quality)) if quality else ' · 对战')+' · '+stats
    GEMS.append({**g,'name':name,'english':g['name'],'label':label})
GEM_IDS={str(g['id']) for g in GEMS}

# Reuse upstream applicability masks; exclude engineering bot schematics (not scrolls).
RUNE_IDS={3368,3370,3847,6241,6242,6243,6244,6245}
GEAR_ENCHANTS=[e for e in ENCHANTS.values() if (e.get('expansion')==11 and e.get('equipRequirements',{}).get('itemClass') in (2,4) and e.get('categoryName')!='Bots') or e['id'] in RUNE_IDS]
ENCHANT_NAMES=json.loads((HERE/'enchant-names-zhCN.json').read_text(encoding='utf-8')) if (HERE/'enchant-names-zhCN.json').exists() else {}
STAT_NAMES={**GEM_STATS,'str':'力量','agi':'敏捷','int':'智力','sta':'耐力','leech':'吸血','speed':'加速','avoidance':'闪避','armor':'护甲','runspeed':'加速','stragi':'力量 / 敏捷'}

def enchant_options(f):
    item=ITEMS.get(int(f['id']),{});options=[]
    for e in GEAR_ENCHANTS:
        req=e['equipRequirements']
        if item.get('itemClass')!=req['itemClass']:continue
        if any(req.get(mask,0) and not req[mask] & (1<<item.get(key,0)) for mask,key in [('itemSubClassMask','itemSubClass'),('invTypeMask','inventoryType')]):continue
        name=ENCHANT_NAMES.get(str(e['id']),{}).get('name',e.get('itemName',e['displayName']))
        name=re.sub(r'^附魔[^-—–]+\s*[-—–]\s*','',name)
        stats=' / '.join(str(v['amount'])+' '+STAT_NAMES.get(v['type'],v['type']) for v in e.get('stats',[]))
        label=name+(' · 品质 '+str(e['craftingQuality']) if e.get('craftingQuality') else ' · 符文熔铸')
        if stats:label+=' · '+stats
        options.append({'id':str(e['id']),'label':label,'english':e.get('itemName',e['displayName'])})
    current=f.get('enchant_id')
    if current and not any(o['id']==current for o in options):options.append({'id':current,'label':'保留原导入附魔 · '+current})
    return options


def can_add_socket(f):
    item=ITEMS.get(int(f['id']),{})
    current=any(int(f['id']) in ids for ids in GROUPS.values()) or any(BONUSES.get(b,{}).get('upgrade',{}).get('seasonId')==37 for b in f.get('bonus_id','').split('/'))
    return current and item.get('inventoryType') in (1,6,9)

def gem_sockets(f, include_addable=True):
    item=ITEMS.get(int(f['id']),{})
    sockets=[v['type'] for v in item.get('socketInfo',{}).get('sockets',[])]
    for b in f.get('bonus_id','').split('/'):
        sockets+=['PRISMATIC']*int(BONUSES.get(b,{}).get('socket',0))
    current=f.get('gem_id','').split('/') if f.get('gem_id') else []
    # Existing imported gems prove occupied sockets even when sparse metadata omits them.
    while len(sockets)<len(current):sockets.append(ALL_GEMS.get(current[len(sockets)],{}).get('socket','PRISMATIC'))
    if not sockets and include_addable and can_add_socket(f):sockets=['PRISMATIC']
    return sockets

def check_unique_gems(model):
    counts={}
    for raw in model['gear'].values():
        for gid in gear_fields(raw).get('gem_id','').split('/'):
            g=ALL_GEMS.get(gid,{})
            limit=g.get('itemLimit')
            if not limit and g.get('unique'):limit={'category':g['unique'],'quantity':1}
            if limit:
                key=limit['category'];counts[key]=counts.get(key,0)+1
                if counts[key]>limit['quantity']:raise ValueError('此类唯一宝石已达到整套装备数量上限，请先移除其他插槽中的同类宝石')

def gear_fields(value):
    if not isinstance(value,str) or len(value)>3000: raise ValueError('装备字段格式不正确')
    result={}
    for part in value.split(','):
        if '=' not in part:
            if part and not re.fullmatch(r'[\w .\-\u0080-\uffff]+',part): raise ValueError('装备名称格式不正确')
            continue
        key,val=part.split('=',1)
        if key not in FIELDS or not re.fullmatch(r'\d+(?:/\d+)*',val): raise ValueError('未支持的装备字段：'+key)
        if key in result: raise ValueError('重复装备字段：'+key)
        result[key]=val
    if not result.get('id'): raise ValueError('装备缺少物品编号')
    return result

def encode(fields):
    return ','+','.join(k+'='+v for k,v in fields.items())

def parse_import(text):
    if not isinstance(text,str) or len(text)>131072: raise ValueError('导入文本过长')
    model={'name':'导入方案','character':{},'gear':{}}
    for raw in text.replace('\\_','_').splitlines():
        line=raw.strip()
        if not line or line.startswith('#'): continue
        if '=' not in line: raise ValueError('无法识别的导入行')
        key,value=line.split('=',1); key=ALIASES.get(key,key)
        if key=='deathknight': model['character']['class']='deathknight'
        elif key in ('level','race','spec','talents','omnium_talents'): model['character'][key]=value
        elif key in SLOT_KEYS:
            if key in model['gear']: raise ValueError('重复装备槽位')
            model['gear'][key]=encode(gear_fields(value))
        elif key in ('region','server','role','professions'): continue
        else: raise ValueError('暂不支持导入字段：'+key)
    validate(model)
    return model

def validate(model):
    if not isinstance(model,dict): raise ValueError('方案格式不正确')
    c=model.get('character',{})
    if c.get('class')!='deathknight' or str(c.get('level'))!='90' or c.get('spec')!='blood': raise ValueError('当前计算仅支持 90 级鲜血死亡骑士')
    if not re.fullmatch(r'[a-z_]{2,40}',str(c.get('race',''))): raise ValueError('缺少有效种族')
    if not re.fullmatch(r'[A-Za-z0-9+/=]{20,600}',str(c.get('talents',''))): raise ValueError('缺少有效天赋，无法完整计算')
    if c.get('omnium_talents') and not re.fullmatch(r'\d+:\d+(?:/\d+:\d+)*',str(c['omnium_talents'])): raise ValueError('额外系统配置格式不正确')
    if not isinstance(model.get('gear'),dict) or any(s not in SLOT_KEYS for s in model['gear']): raise ValueError('装备槽位无效')
    for value in model['gear'].values(): gear_fields(value)

def item_info(value):
    f=gear_fields(value); iid=int(f['id']); item=ITEMS.get(iid,{})
    return {'id':iid,'icon':item.get('icon',''),'name':NAMES.get(iid,item.get('name','未知装备')),'english':item.get('name',''), 'missingName':iid not in NAMES,'crafted':bool(item.get('profession')),'fields':f}

BASE=parse_import((RESEARCH/'cn-user-20260908.input.simc').read_text(encoding='utf-8'))
BASE['name']='当前装备'
# Reuse the previously audited inventory; do not maintain another drop table.
INVENTORY=json.loads((RESEARCH/'epic-catalog-results.json').read_text())
GROUPS={k:set(v) for k,v in INVENTORY['groups'].items()}
CONVERSIONS=json.loads((DATA/'item-conversions.json').read_text())['13']
ITEMS.update({x['id']:x for x in CONVERSIONS['items']})
SLOT_MAP={1:['head'],2:['neck'],3:['shoulder'],5:['chest'],6:['waist'],7:['legs'],8:['feet'],9:['wrist'],10:['hands'],11:['finger1','finger2'],12:['trinket1','trinket2'],13:['main_hand','off_hand'],14:['off_hand'],15:['main_hand'],16:['back'],17:['main_hand'],20:['chest'],21:['main_hand'],22:['off_hand'],23:['off_hand'],25:['main_hand'],26:['main_hand']}
CRAFT_PAIRS={'/'.join(map(str,BONUSES[str(b)]['craftedStats'])):str(b) for b in range(8790,8796)}

def equip_reason(item):
    if item.get('inventoryType') in (14,23):return '死亡骑士无法装备盾牌或副手物品'
    if item.get('allowableClasses') and 6 not in item['allowableClasses']: return '其他职业专属'
    if item['itemClass']==4 and item.get('itemSubClass') not in (0,1,2,3,4): return '死亡骑士无法装备'
    if item['itemClass']==2 and item.get('itemSubClass') not in (0,1,4,5,6,7,8): return '死亡骑士无法装备'
    return ''

ARMOR_NAMES={1:'布甲',2:'皮甲',3:'锁甲',4:'板甲'}
ARMOR_SLOTS={1,3,5,6,7,8,9,10,20}

def fit_reason(item):
    # Candidate relevance is not an equip prohibition or a performance ranking.
    hard=equip_reason(item)
    if hard:return hard
    if item['itemClass']==4 and item.get('inventoryType') in ARMOR_SLOTS and item.get('itemSubClass')!=4:
        return ARMOR_NAMES.get(item.get('itemSubClass'),'其他护甲')+' · 不符合当前职业板甲专精'
    if item['itemClass']==2 and item.get('inventoryType')!=17:
        return '非鲜血常规双手武器配置'
    primary={s['id'] for s in item.get('stats',[])} & {3,4,5,71,72,73,74}
    if primary and not primary & {4,71,72,74}:
        return '主属性不提供力量'
    if item.get('specs') and 250 not in item['specs']:
        return '掉落专精不含鲜血 · 可在全部装备中查看'
    return ''

def catalog_fields(iid):
    item=ITEMS[iid]; f={'id':str(iid)}; bonuses=list(map(str,item.get('bonusLists',[])))
    if iid in GROUPS['crafted_epic']:
        bonuses += ['13751','13836','12497']
        f['crafting_quality']='5'
        if any(x['id'] in (24,25) for x in item.get('stats',[])):
            bonuses.append('8790'); f['crafted_stats']='32/36'
    elif iid in GROUPS['non_set_conversion_forms']:
        pass  # The original equipped item must supply the level and redirected stats.
    elif any(x.get('instanceId')==1320 and x.get('encounterId') in (2883,2895) for x in item.get('sources',[])):
        f['ilevel']='344'  # Fixed final-boss endpoint, not the ordinary upgrade track.
    else:
        bonuses.append('12854')
    if bonuses:f['bonus_id']='/'.join(dict.fromkeys(bonuses))
    return f

CATALOG={s:[] for s,_ in SLOTS}
SOURCE_LABELS={'mplus':'大秘境','raid_direct':'团本','raid_token_products':'团本套装成品','crafted_epic':'制作','non_set_conversion_forms':'同源转化形态'}
for group,ids in GROUPS.items():
    for iid in sorted(ids):
        item=ITEMS[iid]; value=encode(catalog_fields(iid))
        record={'label':SOURCE_LABELS[group],'value':value,**item_info(value),'reason':equip_reason(item),'fitReason':fit_reason(item),'armorType':ARMOR_NAMES.get(item.get('itemSubClass'),'') if item['itemClass']==4 and item.get('inventoryType') in ARMOR_SLOTS else '', 'conversion':group=='non_set_conversion_forms'}
        for slot in SLOT_MAP.get(item['inventoryType'],[]):CATALOG[slot].append(record)
# Imported items outside the search scope stay in the model, never expand this catalog.
CATALOG_COUNT=len({x['id'] for rows in CATALOG.values() for x in rows})
assert CATALOG_COUNT==523
FILTER_STATS=json.loads((HERE/'filter-stats.json').read_text(encoding='utf-8')) if (HERE/'filter-stats.json').exists() else {}
for rows in CATALOG.values():
    for row in rows:
        row['filterStats']=FILTER_STATS.get(str(row['id']),[])
        row['customFilter']=row['crafted'] and any(s['id'] in (24,25) for s in ITEMS[row['id']].get('stats',[]))

# Shared option generation drives both the UI and server-side validation.
TRACK_NAMES={'Adventurer':'冒险者','Veteran':'老兵','Champion':'勇士','Hero':'英雄','Myth':'神话'}
TRACKS={g:sorted([v['upgrade'] for v in BONUSES.values() if v.get('upgrade',{}).get('seasonId')==37 and v['upgrade']['group']==g],key=lambda t:t['level']) for g in (614,615,616,617,618)}
ENCOUNTERS={(i['id'],e['id']):e for i in json.loads((DATA/'instances.json').read_text()) for e in i.get('encounters',[])}
CRAFTING=json.loads((DATA/'crafting.json').read_text())

INSTANCE_NAMES={1041:'诸王之眠',1202:'红玉新生法池',1030:'塞塔里斯神庙',1313:'虚空之痕竞技场',1311:'纳洛拉克的洞穴',1304:'密谋小径',1322:'毒牙祭坛'}
# Public source names not yet localized retain their upstream names explicitly.
# zhCN encounter names: Wowhead zone 16915 and Tidebound Grotto guide (2026-09-08).
INSTANCE_NAMES.update({1309:'夺目谷',1317:'潮缚石窟',1320:'烈毒之渊'})
ENCOUNTER_NAMES={2849:'尼姆瑞莎·唤波者',2888:'盘魂者内克扎莉',2874:'陵寝哨兵',2894:'迷失的探险者',2882:'万毒邪祟者瓦什尼克',2871:'斯索拉克',2887:'双子毒牙',2883:'盘卷祭坛',2895:'乌拉特克'}
PROFESSION_NAMES={164:'锻造',165:'制皮',171:'炼金术',197:'裁缝',202:'工程学',333:'附魔',755:'珠宝加工',773:'铭文'}
INSTANCES={i['id']:i for i in json.loads((DATA/'instances.json').read_text())}

def equipment_sources(f):
    iid=int(f['id']);item=ITEMS.get(iid,{})
    profession=item.get('profession',{}).get('id')
    if profession:
        name=PROFESSION_NAMES.get(profession,'专业 '+str(profession))
        return {'summary':'制作 · '+name,'details':['制作专业：'+name]}
    actual_id=int(f.get('redirected_base_stats',iid));source_item=ITEMS.get(actual_id,item)
    sources=list(source_item.get('sources',[]));details=[]
    tier=iid in GROUPS['raid_token_products']
    if tier and actual_id==iid:
        sources=[]
        for token in INVENTORY['excluded_raid_tokens']:
            record=ITEMS[token]
            if iid in record.get('contains',[]):
                for src in record.get('sources',[]):sources.append(src)
    summaries=[]
    for src in sources:
        instance=INSTANCES.get(src.get('instanceId'))
        if not instance or instance['id']<=0:continue
        name=INSTANCE_NAMES.get(instance['id'],instance['name']+'（副本中文名待补）')
        kind='团本' if instance.get('type')=='raid' else '大秘境' if actual_id in GROUPS['mplus'] else '地下城'
        prefix=kind+' · '+name
        if prefix not in summaries:summaries.append(prefix)
        encounter=ENCOUNTERS.get((instance['id'],src.get('encounterId')), {})
        boss='非首领掉落' if encounter.get('trash') else ENCOUNTER_NAMES.get(src.get('encounterId'),encounter.get('name','来源首领待确认'))
        if encounter and not encounter.get('trash') and src.get('encounterId') not in ENCOUNTER_NAMES:boss+='（首领中文名待补）'
        text=prefix if kind=='大秘境' else prefix+' · '+boss
        if text not in details:details.append(text)
    if actual_id!=iid:details.insert(0,'催化转化：原装备 '+NAMES.get(actual_id,str(actual_id))+'（'+str(actual_id)+'）')
    return {'summary':('催化转化 · ' if actual_id!=iid else '')+(' / '.join(summaries) if summaries else '导入装备 · 来源待确认'),'details':details or ['现有数据未提供可确认的具体来源；导入与计算仍保留。']}

def level_options(f,seen=None):
    iid=int(f['id']); seen=set() if seen is None else seen
    if iid in seen:return []
    seen=seen|{iid}; item=ITEMS.get(iid,{})
    if f.get('redirected_base_stats') and int(f['redirected_base_stats'])!=iid:
        source={**f,'id':f['redirected_base_stats']};source.pop('redirected_base_stats',None)
        return level_options(source,seen)
    if iid in GROUPS['crafted_epic']:
        allowed={n for slot in item['profession']['optionalCraftingSlots'] for n in CRAFTING['slots'][str(slot['id'])]['reagentIds']}
        tiers=[('13751','潮汐火花',274476),('13835','英雄纹章',3445),('13836','神话纹章',3446)]
        options=[]
        for base,label,reagent in tiers:
            if reagent not in allowed:continue
            for q in range(5):
                qb=str(12493+q);level=BONUSES[base]['itemLevel']['amount']+BONUSES[qb]['levelOffset']['amount']
                options.append({'key':f'craft:{base}:{qb}','level':level,'label':f'{level} · {label} · 品质 {q+1}','bonuses':['13751']+([] if base=='13751' else [base])+[qb],'quality':q+1})
        return options
    starts={}; fixed=set()
    if iid in GROUPS['mplus']:
        starts.update({616:2,617:1,618:1})
    sources=list(item.get('sources',[]))
    if iid in GROUPS['raid_token_products']:
        sources=[]
        slot=SLOT_MAP[item['inventoryType']][0]
        for token in INVENTORY['excluded_raid_tokens']:
            record=ITEMS[token]
            if iid in record.get('contains',[]):
                sources.extend({**src,'sequenceOffset':record.get('slotItemSequenceOffsets',{}).get(slot,0)} for src in record.get('sources',[]))
    for src in sources:
        if src.get('instanceId') not in (1317,1320):continue
        boss=ENCOUNTERS.get((src['instanceId'],src['encounterId']),{})
        rank=max(1,boss.get('itemSequenceLevel',1)+src.get('sequenceOffset',0))
        for group in (615,616,617,618):
            if group==618 and rank>=4 and src['instanceId']==1320:
                fixed.add(344);continue
            starts[group]=min(starts.get(group,6),rank)
    if not starts and not fixed:
        for b in f.get('bonus_id','').split('/'):
            t=BONUSES.get(b,{}).get('upgrade',{})
            if t.get('seasonId')==37:starts[t['group']]=1
    options=[]
    for group,start in starts.items():
        for t in TRACKS[group]:
            if t['level']>=start:options.append({'key':'upgrade:'+str(t['bonusId']),'level':t['itemLevel'],'label':str(t['itemLevel'])+' · '+TRACK_NAMES[t['name']]+' '+str(t['level'])+'/'+str(t['max']),'bonuses':[str(t['bonusId'])]})
    options.extend({'key':'fixed:'+str(n),'level':n,'label':str(n)+' · 神话特殊掉落','bonuses':[],'explicit':n} for n in fixed)
    return sorted(options,key=lambda o:(o['level'],o['key']))

def current_level_key(f,options):
    bonuses=set(f.get('bonus_id','').split('/'))
    for o in options:
        if o.get('explicit') and f.get('ilevel')==str(o['explicit']):return o['key']
        if o['bonuses'] and set(o['bonuses'])<=bonuses:
            if o['key'].startswith('craft:13751:') and bonuses & {'13835','13836'}:continue
            return o['key']
    return ''

class ReplacementLevelError(ValueError):
    def __init__(self,old_level,new_level,name):
        super().__init__(name+'不支持原来的 '+str(old_level)+' 装等，可改用 '+str(new_level)+' 装等。')
        self.alternative_level=new_level

def level_bonus(b):
    record=BONUSES.get(b,{})
    return bool(record.get('upgrade') or b in ('13751','13835','13836','13849','13850') or 'craftingQuality' in record.get('levelOffset',{}))

def apply_bulk_levels(model, edit):
    validate(model)
    target=edit['bulkLevel']; original=edit.get('original')
    if target not in ('minimum','maximum','restore') and (type(target) is not int or not 1<=target<=999):raise ValueError('无效统一装等')
    reference={}
    if target=='restore':
        validate(original)
        reference=calculate(original)
        if not reference['complete']:raise ValueError('已保存方案的装等无法确认，未修改装备')
    updated=copy.deepcopy(model); unsupported=[]
    for slot,label in SLOTS:
        if slot not in model['gear']:continue
        f=gear_fields(model['gear'][slot]);options=level_options(f)
        if target=='restore':
            saved=reference['items'].get(slot)
            if not saved or saved['ilevel'] is None:
                unsupported.append(label);continue
            old=saved['fields']
            if all(f.get(k)==old.get(k) for k in ('id','redirected_base_stats')):
                bonuses=[b for b in f.get('bonus_id','').split('/') if b and not level_bonus(b)]
                bonuses.extend(b for b in old.get('bonus_id','').split('/') if b and level_bonus(b))
                for key in ('ilevel','crafting_quality'):
                    f.pop(key,None)
                    if key in old:f[key]=old[key]
                if bonuses:f['bonus_id']='/'.join(dict.fromkeys(bonuses))
                else:f.pop('bonus_id',None)
                updated['gear'][slot]=encode(f);continue
            wanted=saved['ilevel']
        elif target in ('minimum','maximum'):
            if not options:unsupported.append(label);continue
            wanted=(min if target=='minimum' else max)(o['level'] for o in options)
        else:wanted=target
        if not any(o['level']==wanted for o in options):unsupported.append(label);continue
        updated=apply_edit(updated,{'slot':slot,'level':wanted})
    if unsupported and edit.get('skipUnsupported') is not True:
        raise ValueError('以下装备无此等级或缺少可确认的装等资料：'+ '、'.join(unsupported)+'。请确认后保留这些装备的等级。')
    return updated

def apply_edit(model, edit):
    if 'bulkLevel' in edit:return apply_bulk_levels(model,edit)
    model=copy.deepcopy(model); slot=edit.get('slot')
    if slot not in dict(SLOTS): raise ValueError('无效编辑槽位')
    if edit.get('remove'):
        model['gear'].pop(slot,None); return model
    if 'candidate' in edit or 'originalItem' in edit:
        if 'originalItem' in edit:
            fields=gear_fields(edit['originalItem']);item=ITEMS.get(int(fields['id']))
            if not item or slot not in SLOT_MAP.get(item['inventoryType'],[]):raise ValueError('方案原装备不适用于此槽位')
            for key in ('gem_id','gem_bonus_id','enchant_id'):fields.pop(key,None)
            value=encode(fields)
            candidate={**item_info(value),'value':value,'reason':equip_reason(item),'conversion':False}
        else:
            candidates=CATALOG.get(slot,[]); index=edit['candidate']
            if not isinstance(index,int) or index<0 or index>=len(candidates): raise ValueError('无效装备选择')
            candidate=candidates[index]
        if candidate['reason']: raise ValueError(candidate['reason'])
        if candidate['conversion']:
            if slot not in model['gear']:raise ValueError('先装备一件可转化的同槽位装备')
            original=gear_fields(model['gear'][slot]); source=ITEMS.get(int(original['id']),{})
            target=ITEMS[candidate['id']]
            if '13662' not in original.get('bonus_id','').split('/') or source.get('itemSubClass')!=target.get('itemSubClass'):
                raise ValueError('当前装备未确认可转化为该形态；请先导入含转化标记的原装备')
            original['redirected_base_stats']=original.get('redirected_base_stats',original['id'])
            original['id']=str(candidate['id']); model['gear'][slot]=encode(original)
        else:
            previous=model['gear'].get(slot)
            original=gear_fields(previous) if previous else None
            if original:
                old_options=level_options(original)
                old_key=current_level_key(original,old_options)
                old_level=int(original['ilevel']) if original.get('ilevel') else next((o['level'] for o in old_options if o['key']==old_key),None)
                if old_level is None:
                    snapshot=calculate(model)
                    old_level=snapshot.get('items',{}).get(slot,{}).get('ilevel')
                if old_level is None:raise ValueError('无法确认原装备装等，已保留原装备；请先确认其装等再替换')
            model['gear'][slot]=candidate['value']
            if original:
                options=level_options(gear_fields(candidate['value']))
                matches=[o for o in options if o['level']==old_level]
                if not matches:
                    if not options:
                        target=calculate(model).get('items',{}).get(slot,{})
                        if target.get('ilevel')==old_level:matches=[{'key':None}]
                        else:raise ValueError('原装备不支持当前装等或缺少可确认的等级资料，已保留当前装备')
                    if not matches:
                        alternative=min(options,key=lambda o:(abs(o['level']-old_level),o['level']))['level']
                        if edit.get('acceptLevelChange')!=alternative:raise ReplacementLevelError(old_level,alternative,candidate['name'])
                        matches=[o for o in options if o['level']==alternative]
                chosen=next((o for o in matches if o['key']==old_key),matches[-1])
                if chosen['key'] is not None:model=apply_edit(model,{'slot':slot,'levelVariant':chosen['key']})
                replacement=gear_fields(model['gear'][slot])
                # Only socket bonuses transfer; source and upgrade bonuses belong to the new item.
                socket_bonuses=[b for b in original.get('bonus_id','').split('/') if BONUSES.get(b,{}).get('socket') and set(BONUSES[b])<={'id','socket'}]
                new_bonuses=[b for b in replacement.get('bonus_id','').split('/') if not BONUSES.get(b,{}).get('socket')]
                if socket_bonuses:replacement['bonus_id']='/'.join(new_bonuses+socket_bonuses)
                if original.get('enchant_id'):
                    if original['enchant_id'] not in {o['id'] for o in enchant_options(replacement)}:raise ValueError('原附魔不适用于新装备，已保留原装备；请先移除或更换附魔')
                    replacement['enchant_id']=original['enchant_id']
                if original.get('gem_id'):
                    gems=original['gem_id'].split('/');sockets=gem_sockets(replacement)
                    if any(g!='0' and (i>=len(sockets) or ALL_GEMS.get(g,{}).get('socket')!=sockets[i]) for i,g in enumerate(gems)):raise ValueError('新装备无法保留原宝石插槽，已保留原装备；请先移除不兼容的宝石')
                    if not gem_sockets(replacement,False) and can_add_socket(replacement):replacement['bonus_id']='/'.join(filter(None,[replacement.get('bonus_id',''),'13668']))
                    replacement['gem_id']=original['gem_id']
                    if original.get('gem_bonus_id'):replacement['gem_bonus_id']=original['gem_bonus_id']
                model['gear'][slot]=encode(replacement)
    if slot not in model['gear']: raise ValueError('先选择装备')
    f=gear_fields(model['gear'][slot]); bonuses=f.get('bonus_id','').split('/') if f.get('bonus_id') else []
    if 'level' in edit or 'levelVariant' in edit:
        options=level_options(f)
        if 'levelVariant' in edit:
            chosen=next((o for o in options if o['key']==edit['levelVariant']),None)
        else:
            matches=[o for o in options if o['level']==int(edit['level'])]
            current=current_level_key(f,options)
            track=BONUSES.get(current.partition(':')[2],{}).get('upgrade',{}).get('group')
            chosen=next((o for o in matches if BONUSES.get(o['key'].partition(':')[2],{}).get('upgrade',{}).get('group')==track),matches[-1] if matches else None)
        if not chosen:raise ValueError('该装等或轨道不适用于当前装备来源')
        bonuses=[b for b in bonuses if not BONUSES.get(b,{}).get('upgrade')]
        if chosen.get('quality'):
            bonuses=[b for b in bonuses if b not in ('13751','13835','13836','13849','13850') and 'craftingQuality' not in BONUSES.get(b,{}).get('levelOffset',{})]
            f['crafting_quality']=str(chosen['quality'])
        bonuses=list(dict.fromkeys(bonuses+chosen['bonuses']))
        f.pop('ilevel',None)
        if chosen.get('explicit'):f['ilevel']=str(chosen['explicit'])
    if 'crafted' in edit:
        pair=edit['crafted']
        mapping=CRAFT_PAIRS
        if pair not in mapping or not item_info(model['gear'][slot])['crafted'] or not any(x['id'] in (24,25) for x in ITEMS[int(f['id'])].get('stats',[])): raise ValueError('不支持此制作属性')
        bonuses=[b for b in bonuses if not BONUSES.get(b,{}).get('craftedStats')]+[mapping[pair]]
        f['crafted_stats']=pair
    enchants={o['id'] for o in enchant_options(f)} | {''}
    if 'gem_id' in edit:
        gid=str(edit['gem_id']);index=edit.get('gemIndex',0);sockets=gem_sockets(f)
        if not isinstance(index,int) or not 0<=index<len(sockets):raise ValueError('当前装备没有这个可用插槽')
        if gid and not gem_sockets(f,False) and can_add_socket(f):bonuses.append('13668')
        if gid and (gid not in GEM_IDS or ALL_GEMS[gid]['socket']!=sockets[index]):raise ValueError('该宝石不适用于当前插槽')
        gems=f.get('gem_id','').split('/') if f.get('gem_id') else []
        gems+=['0']*(len(sockets)-len(gems));gems[index]=gid or '0'
        while gems and gems[-1]=='0':gems.pop()
        if gems:f['gem_id']='/'.join(gems)
        else:f.pop('gem_id',None)
    if 'enchant_id' in edit:
        val=str(edit['enchant_id'])
        if val not in enchants:raise ValueError('该附魔选项未接入')
        if val:f['enchant_id']=val
        else:f.pop('enchant_id',None)
    if bonuses: f['bonus_id']='/'.join(bonuses)
    else:f.pop('bonus_id',None)
    model['gear'][slot]=encode(f)
    if 'gem_id' in edit:check_unique_gems(model)
    return model

@lru_cache(maxsize=2048)
def replacement_signature(slot,value):
    # Cache item-only evidence; native gear stats exclude character and set multipliers.
    probe=copy.deepcopy(BASE);probe['gear'][slot]=value
    result=calculate(probe)
    if not result['complete']:raise ValueError('无法确认换装结果')
    item=result['items'][slot];f=item['fields']
    effects=item_effects({'itemId':item['id'],'level':item['ilevel'],'bonuses':f.get('bonus_id','')})
    if effects.get('error'):raise ValueError('无法确认装备特效')
    raw={k:v for k,v in item['raw'].items() if k!='encoded_item'}
    return {'raw':raw,'effects':effects['effects'],'sets':effects.get('setEffectsBySpec') or effects.get('setEffects') or [],
            'id':item['id'],'redirected':f.get('redirected_base_stats'),
            'gems':f.get('gem_id',''),'gemBonuses':f.get('gem_bonus_id',''),
            'enchant':f.get('enchant_id',''),'sockets':item['gemSlots']}

def original_matches(model, originals):
    validate(model)
    if not isinstance(originals,dict) or any(slot not in dict(SLOTS) for slot in originals):raise ValueError('无效原装备列表')
    def outcome(slot,patch):
        confirmation=None
        try:changed=apply_edit(model,{'slot':slot,**patch})
        except ReplacementLevelError as exc:
            confirmation=exc.alternative_level
            changed=apply_edit(model,{'slot':slot,**patch,'acceptLevelChange':confirmation})
        fields=gear_fields(changed['gear'][slot])
        if fields.get('bonus_id'):fields['bonus_id']='/'.join(sorted(set(fields['bonus_id'].split('/')),key=int))
        return confirmation,replacement_signature(slot,encode(fields))
    matches={'_selected':{}}
    for slot in set(originals)|{s for s in model['gear'] if s in dict(SLOTS)}:
        value=originals.get(slot);matches[slot]=[];matches['_selected'][slot]=[]
        iid=int(gear_fields(value)['id']) if value else None
        current_value=model['gear'].get(slot)
        current_id=int(gear_fields(current_value)['id']) if current_value else None
        try:
            fields=gear_fields(current_value)
            if fields.get('bonus_id'):fields['bonus_id']='/'.join(sorted(set(fields['bonus_id'].split('/')),key=int))
            current=(None,replacement_signature(slot,encode(fields)))
        except (ValueError,KeyError,TypeError):current=None
        try:original=outcome(slot,{'originalItem':value}) if value else None
        except (ValueError,KeyError,TypeError):original=None
        if original is not None and current is not None and original==current:matches['_selected'][slot].append('original')
        for index,item in enumerate(CATALOG[slot]):
            if item['id'] not in (iid,current_id) or item['reason'] or item['fitReason'] or item['conversion']:continue
            try:
                candidate=outcome(slot,{'candidate':index})
                if original is not None and candidate==original:matches[slot].append(index)
                if current is not None and candidate==current:matches['_selected'][slot].append(index)
            except (ValueError,KeyError,TypeError):pass
    return matches

def calculate(model):
    validate(model); started=time.perf_counter(); c=model['character']
    lines=['deathknight=prototype','level=90','spec=blood','race='+c['race'],'talents='+c['talents']]
    if c.get('omnium_talents'): lines.append('omnium_talents='+c['omnium_talents'])
    lines += [s+'='+encode(gear_fields(v)) for s,v in model['gear'].items()]
    with LOCK, tempfile.TemporaryDirectory(prefix='calc-',dir=HERE) as tmp:
        tmp=Path(tmp); src=tmp/'input.simc'; out=tmp/'result.json'; src.write_text('\n'.join(lines),encoding='utf-8')
        args=[str(EXE),str(src),'item_db_source=local','iterations=1','threads=1','fixed_time=1','max_time=1','vary_combat_length=0','optimal_raid=0','potion=disabled','flask=disabled','food=disabled','augmentation=disabled','temporary_enchant=disabled','override.allow_potions=0','override.allow_food=0','override.allow_flasks=0','override.allow_augmentations=0','actions.precombat=snapshot_stats','actions=wait,sec=1',f'json={out},version=2',f'output={tmp / "report.txt"}']
        run=subprocess.run(args,cwd=tmp,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=12)
        if run.returncode or not out.exists():
            diagnostic=(run.stderr+'\n'+run.stdout).strip()[-1400:]
            return {'model':model,'complete':False,'error':'这份配置未能完整计算，原始方案已保留。','diagnostic':diagnostic,'version':VERSION}
        actor=json.loads(out.read_text())['sim']['players'][0]
    snap=actor['collected_data']['buffed_stats']; stats=snap['stats']; attrs=snap['attribute']
    # Only missing numeric leaves in a successful, complete native snapshot are zero-valued.
    values={k:attrs.get(k,0) for k in ('strength','agility','intellect','stamina')}
    values['armor']=stats.get('armor',0)
    for key in ('crit','haste','mastery','versatility'):
        values[key]=stats.get(key+'_rating',0); values[key+'_pct']=stats.get(key+'_pct',0)*100
    gear={ALIASES.get(k,k):v for k,v in actor['gear'].items()}
    # Upstream gear_to_json deliberately skips !has_stats() items. Retain known
    # statless items for average ilvl, using the selected explicit/upgrade level.
    for slot,value in model['gear'].items():
        if slot in gear or slot not in dict(SLOTS):continue
        f=gear_fields(value); item=ITEMS.get(int(f['id']))
        if item and not item.get('stats'):
            level=int(f['ilevel']) if f.get('ilevel') else next((BONUSES[b]['upgrade']['itemLevel'] for b in f.get('bonus_id','').split('/') if BONUSES.get(b,{}).get('upgrade',{}).get('seasonId')==37),None)
            if level:gear[slot]={'name':item['name'],'ilevel':level}
    mh=gear_fields(model['gear']['main_hand']) if model['gear'].get('main_hand') else {}
    twohand=ITEMS.get(int(mh.get('id',0)),{}).get('inventoryType')==17
    values['ilevel']=(sum(v['ilevel'] for v in gear.values())+gear['main_hand']['ilevel'])/16 if twohand and len(gear)==15 and 'off_hand' not in gear else None
    metadata={}
    for slot,value in model['gear'].items():
        if slot not in dict(SLOTS): continue
        info=item_info(value); f=info['fields']
        info['sourceInfo']=equipment_sources(f)
        info['levelOptions']=level_options(f)
        info['selectedLevel']=current_level_key(f,info['levelOptions'])
        info['levels']=sorted({o['level'] for o in info['levelOptions']})
        info['customStats']=info['crafted'] and any(x['id'] in (24,25) for x in ITEMS.get(info['id'],{}).get('stats',[]))
        info['ilevel']=gear.get(slot,{}).get('ilevel'); info['raw']=gear.get(slot,{})
        info['gemSlots']=gem_sockets(f)
        info['addableSocket']=not gem_sockets(f,False) and can_add_socket(f)
        info['gemEditable']=bool(info['gemSlots'])
        info['enchantOptions']=enchant_options(f)
        info['effectiveCrafted']=next(('/'.join(map(str,BONUSES[b]['craftedStats'])) for b in f.get('bonus_id','').split('/') if BONUSES.get(b,{}).get('craftedStats')),f.get('crafted_stats',''))
        metadata[slot]=info
    return {'model':model,'complete':True,'values':values,'items':metadata,'version':VERSION,'seconds':round(time.perf_counter()-started,3),'baseline':model['gear']==BASE['gear'] and model['character']==BASE['character'],'note':'属性由原版模拟器计算；额外系统部分触发效果仍有上游未验证提示。'}


def item_effects(data):
    iid=data.get('itemId');level=data.get('level');bonuses=data.get('bonuses','')
    if type(iid) is not int or not 0<iid<10000000 or type(level) is not int or not 0<level<1000:raise ValueError('无效物品或装等')
    if not isinstance(bonuses,str) or len(bonuses)>3000 or (bonuses and not re.fullmatch(r'\d+(?:/\d+)*',bonuses)):raise ValueError('无效装备变体')
    query=urlencode({'dataEnv':1,'locale':4,'ilvl':level,'bonus':bonuses.replace('/',':')})
    url=f'https://nether.wowhead.com/tooltip/item/{iid}?{query}'
    cache=HERE/'effect-cache-v2';cache.mkdir(exist_ok=True)
    path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if path.exists():
        cached=json.loads(path.read_text(encoding='utf-8'))
        if not cached.get('setName') or 'setEffectsBySpec' in cached:return cached
    try:
        with urllib.request.urlopen(url,timeout=8) as response:tooltip=json.load(response).get('tooltip','')
        reported=re.search(r'<!--ilvl-->(\d+)',tooltip)
        if not reported or int(reported[1])!=level:return {'effects':[],'error':'资料装等不匹配，暂不显示特效数值'}
        effects=[]
        for block in re.findall(r'<!--useText:0:\d+-->(.*?)<!--useText:1-->',tooltip,re.S):
            text=html.unescape(re.sub(r'<[^>]*>','',block)).strip()
            if text and text not in effects:effects.append(text)
        set_name=re.search(r'<a[^>]+item-set=\d+[^>]*>(.*?)</a>',tooltip)
        by_spec={}
        for spec,block in re.findall(r'<!--itemeffectspec(\d+):0-->(.*?)<!--itemeffectspec-->',tooltip,re.S):
            text=html.unescape(re.sub(r'<[^>]*>','',block)).strip().replace('of Attack Power','攻击强度')
            if text and text not in by_spec.setdefault(spec,[]):by_spec[spec].append(text)
        result={'effects':effects,'setName':html.unescape(re.sub(r'<[^>]*>','',set_name[1])) if set_name else '', 'setEffects':by_spec.get('250',[]),'setEffectsBySpec':by_spec,'source':url,'level':level}
        path.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        return result
    except (OSError,ValueError):return {'effects':[],'error':'特效资料暂时无法获取，请稍后重试'}

def cached_effects():
    records={}
    for path in (HERE/'effect-cache-v2').glob('*.json'):
        try:
            r=json.loads(path.read_text(encoding='utf-8'));url=urlsplit(r['source']);q=parse_qs(url.query)
            key=url.path.rsplit('/',1)[-1]+'|'+str(r['level'])+'|'+q.get('bonus',[''])[0].replace(':','/')
            records[key]=r
        except (OSError,ValueError,KeyError):continue
    return records

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,obj,kind='application/json; charset=utf-8'):
        body=json.dumps(obj,ensure_ascii=False).encode() if isinstance(obj,(dict,list)) else obj
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(body))); self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass
    def do_GET(self):
        if self.headers.get('Host')!=f'127.0.0.1:{PORT}': self.reply(403,{'error':'只允许本机访问'}); return
        path=urlsplit(self.path).path
        if path=='/': self.reply(200,(HERE/'index.html').read_bytes(),'text/html; charset=utf-8')
        elif path=='/api/bootstrap': self.reply(200,{'token':TOKEN,'catalog':CATALOG,'slots':SLOTS,'version':VERSION,'catalogCount':CATALOG_COUNT,'gems':GEMS,'effectCache':cached_effects()})
        else: self.reply(404,{'error':'页面不存在'})
    def do_POST(self):
        if self.headers.get('Host')!=f'127.0.0.1:{PORT}' or self.headers.get('X-Prototype-Token')!=TOKEN or self.headers.get('Origin',f'http://127.0.0.1:{PORT}')!=f'http://127.0.0.1:{PORT}': self.reply(403,{'error':'请求来源不匹配'}); return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=262144: raise ValueError('请求过大或为空')
            data=json.loads(self.rfile.read(size))
            if self.path=='/api/stop':
                self.reply(200,{'stopped':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start(); return
            if self.path=='/api/original-matches': result=original_matches(data.get('model'),data.get('originals'))
            elif self.path=='/api/effects': result=item_effects(data)
            elif self.path=='/api/import': result=calculate(parse_import(data.get('text')))
            elif self.path=='/api/calculate':
                model=data.get('model'); validate(model)
                if data.get('edit'): model=apply_edit(model,data['edit'])
                result=calculate(model)
            else: self.reply(404,{'error':'接口不存在'}); return
            self.reply(200,result)
        except ReplacementLevelError as exc:self.reply(422,{'error':str(exc),'alternativeLevel':exc.alternative_level})
        except (ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc: self.reply(422,{'error':str(exc) if not isinstance(exc,subprocess.TimeoutExpired) else '计算超时，配置已保留'})

if __name__=='__main__':
    print(f'PROTOTYPE http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
