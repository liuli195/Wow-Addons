"""Reproducible synthetic baseline inputs. Does not infer real talent effects."""
from __future__ import annotations
import copy,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]  # 技能根
ASSETS=ROOT/'assets'
# IDs independently checked in TRB Localization.lua; spell/talent combinations are not inferred.
ROWS=[
(1,'WARRIOR','战士',[(71,'武器',1,'none','DAMAGER'),(72,'狂怒',1,'none','DAMAGER'),(73,'防护',1,'none','TANK')]),
(2,'PALADIN','圣骑士',[(65,'神圣',0,'holy','HEALER'),(66,'防护',0,'holy','TANK'),(70,'惩戒',0,'holy','DAMAGER')]),
(3,'HUNTER','猎人',[(253,'野兽控制',2,'none','DAMAGER'),(254,'射击',2,'none','DAMAGER'),(255,'生存',2,'none','DAMAGER')]),
(4,'ROGUE','潜行者',[(259,'奇袭',3,'combo','DAMAGER'),(260,'狂徒',3,'combo','DAMAGER'),(261,'敏锐',3,'combo','DAMAGER')]),
(5,'PRIEST','牧师',[(256,'戒律',0,'none','HEALER'),(257,'神圣',0,'none','HEALER'),(258,'暗影',13,'none','DAMAGER')]),
(6,'DEATHKNIGHT','死亡骑士',[(250,'鲜血',6,'runes','TANK'),(251,'冰霜',6,'runes','DAMAGER'),(252,'邪恶',6,'runes','DAMAGER')]),
(7,'SHAMAN','萨满祭司',[(262,'元素',11,'none','DAMAGER'),(263,'增强',0,'none','DAMAGER'),(264,'恢复',0,'none','HEALER')]),
(8,'MAGE','法师',[(62,'奥术',0,'arcane','DAMAGER'),(63,'火焰',0,'none','DAMAGER'),(64,'冰霜',0,'none','DAMAGER')]),
(9,'WARLOCK','术士',[(265,'痛苦',0,'shards','DAMAGER'),(266,'恶魔学识',0,'shards','DAMAGER'),(267,'毁灭',0,'shards','DAMAGER')]),
(10,'MONK','武僧',[(268,'酒仙',3,'stagger','TANK'),(270,'织雾',0,'none','HEALER'),(269,'踏风',3,'chi','DAMAGER')]),
(11,'DRUID','德鲁伊',[(102,'平衡',8,'none','DAMAGER'),(103,'野性',3,'druid_combo','DAMAGER'),(104,'守护',1,'none','TANK'),(105,'恢复',0,'none','HEALER')]),
(12,'DEMONHUNTER','恶魔猎手',[(577,'浩劫',17,'none','DAMAGER'),(581,'复仇',17,'none','TANK'),(1480,'噬灭',17,'none','DAMAGER')]),
(13,'EVOKER','唤魔师',[(1467,'湮灭',0,'essence','DAMAGER'),(1468,'恩护',0,'essence','HEALER'),(1473,'增辉',0,'essence','DAMAGER')])]
TOKENS={0:'MANA',1:'RAGE',2:'FOCUS',3:'ENERGY',4:'COMBO_POINTS',5:'RUNES',6:'RUNIC_POWER',7:'SOUL_SHARDS',8:'LUNAR_POWER',9:'HOLY_POWER',11:'MAELSTROM',12:'CHI',13:'INSANITY',16:'ARCANE_CHARGES',17:'FURY',19:'ESSENCE'}
PTS={'combo':4,'druid_combo':4,'holy':9,'chi':12,'arcane':16,'shards':7,'essence':19}
GAPS={263:['漩涡武器光环层数：未提供原生参照'],581:['灵魂残片光环计数：未提供原生参照'],1480:['灵魂／虚空形态计数：未提供原生参照'],1473:['黑檀之力剩余时间不属于本版基本资源契约']}

def profiles():
 out=[]
 for cid,token,name,specs in ROWS:
  for index,(sid,sname,pt,fam,role) in enumerate(specs,1):
   out.append({'class_id':cid,'class_token':token,'class_name':name,'spec_id':sid,'spec_index':index,'spec_name':sname,'role':role,
    'primary_seed':pt,'resource_seed':fam,'identity_evidence':'trb-localization-4fd9767','configuration_evidence':'synthetic-api-contract-not-live-profile',
    'extra_resource_gaps':GAPS.get(sid,[]),'scope':'basic-resource-contract','gameplay_verified':False})
 return out

def state(p):
 powers={}
 for pt,token in TOKENS.items():
  mx=1000 if pt==0 else {4:6,5:6,7:5,9:5,12:5,16:4,19:5}.get(pt,100)
  cur=mx//2;mod=10 if pt==7 else 1
  powers[str(pt)]={'current':cur,'maximum':mx,'raw':cur*mod,'raw_maximum':mx*mod,'display_mod':mod,'partial':500,'regen':0.2,'regen_interrupted':0.2}
 i={k:p[k] for k in ('class_id','class_token','class_name','spec_id','spec_index')};i.update(level=90,form=1 if p['spec_id']==103 else 5 if p['spec_id']==104 else 0)
 return {'identity':i,'time':100,'unit':{'exists':True,'connected':True,'dead':False,'ghost':False,'in_vehicle':False,'vehicle_has_combo':False,'in_combat':False},
  'health':{'current':500,'maximum':1000},'primary':{'type':p['primary_seed'],'token':TOKENS[p['primary_seed']]},'powers':powers,
  'resource_kind':p['resource_seed'],'charged_points':[],'runes':[{'start':0,'duration':0,'ready':True} for _ in range(6)],
  'stagger':250,'known_spells':{},'auras':{}}

def setpower(s,pt,current=None,maximum=None):
 r=s['powers'][str(pt)]
 if current is not None:r['current']=current;r['raw']=current*r['display_mod']
 if maximum is not None:r['maximum']=maximum;r['raw_maximum']=maximum*r['display_mod']

def settype(s,pt):
 s['primary']={'type':pt,'token':TOKENS[pt]}
 if s['identity']['class_token']=='DRUID':s['resource_kind']='druid_combo' if pt==3 else 'none'

def cases():
 ps=profiles();out=[]
 def add(p,key,states,tags,events=None,description=''):
  steps=[]
  for idx,s in enumerate(states):
   s=copy.deepcopy(s);s['time']=100+idx
   ev=(events[idx] if events is not None else None) or ([['PLAYER_ENTERING_WORLD']] if idx==0 else [
     ['PLAYER_SPECIALIZATION_CHANGED','player'],['UPDATE_SHAPESHIFT_FORM'],['UNIT_DISPLAYPOWER','player'],['UNIT_MAXHEALTH','player'],['UNIT_HEALTH','player'],['UNIT_MAXPOWER','player',s['primary']['token']],['UNIT_POWER_UPDATE','player',s['primary']['token']],['UNIT_POWER_FREQUENT','player',s['primary']['token']],['RUNE_POWER_UPDATE',1],['PLAYER_TALENT_UPDATE']])
   steps.append({'label':f'{key}/{idx+1}','state':s,'events':ev,'settle':0.0})
  out.append({'id':f"spec-{p['spec_id']}.{key}",'spec_id':p['spec_id'],'profile':{k:p[k]for k in ('class_id','class_token','class_name','spec_id','spec_index','spec_name','role')},
   'tags':tags,'origin':'synthetic','gameplay_verified':False,'description':description or key,'steps':steps})
 for p in ps:
  b=state(p);fam=p['resource_seed'];pt=p['primary_seed']
  for label,n in [('empty',0),('partial',250),('full',1000)]:
   s=copy.deepcopy(b);s['health']['current']=n;add(p,'health-'+label,[s],['health','value'])
  ss=[]
  for mx in (1000,2000,1000):s=copy.deepcopy(b);s['health']['maximum']=mx;ss.append(s)
  add(p,'health-max-roundtrip',ss,['health','maximum','transition'],[[['UNIT_HEALTH','player']],[['UNIT_MAXHEALTH','player']],[['UNIT_MAXHEALTH','player']]])
  s=copy.deepcopy(b);s['health']={'current':0,'maximum':0};add(p,'health-zero-maximum',[s],['health','zero-maximum'])
  s=copy.deepcopy(b);s['unit']['connected']=False;add(p,'disconnect-reconnect',[b,s,b],['health','primary','connection'])
  s=copy.deepcopy(b);s['unit']['dead']=True;s['health']['current']=0;add(p,'death-revive',[b,s,b],['health','lifecycle'])
  mx=b['powers'][str(pt)]['maximum']
  for label,n in [('empty',0),('partial',mx//2),('full',mx)]:
   s=copy.deepcopy(b);setpower(s,pt,n);add(p,'primary-'+label,[s],['primary','value'])
  s=copy.deepcopy(b);setpower(s,pt,maximum=mx*2)
  add(p,'primary-max-roundtrip',[b,s,b],['primary','maximum','transition'],[[['UNIT_POWER_UPDATE','player',TOKENS[pt]]],[['UNIT_MAXPOWER','player',TOKENS[pt]]],[['UNIT_MAXPOWER','player',TOKENS[pt]]]])
  s=copy.deepcopy(b);settype(s,3 if pt!=3 else 0)
  add(p,'primary-type-roundtrip',[b,s,b],['primary','type','synthetic-fault-injection'],description='接口级类型切换；不声称该专精真实具有此形态')
  add(p,'unrelated-events',[b,b,b],['health','primary','resource','filter'],[[['PLAYER_ENTERING_WORLD']],[['UNIT_HEALTH','target'],['UNIT_MAXPOWER','target','MANA']],[['UNIT_POWER_FREQUENT','target','COMBO_POINTS'],['UNIT_HEALTH','pet']]])
  add(p,'duplicate-events',[b,b,b],['health','primary','resource','idempotence'])
  s=copy.deepcopy(b);s['health']['current']=800;setpower(s,pt,min(75,mx))
  add(p,'three-components-together',[b,s,b],['health','primary','resource','cross-component'])
  if fam in PTS:
   rtype=PTS[fam];cap=b['powers'][str(rtype)]['maximum']
   for n in range(cap+1):
    s=copy.deepcopy(b);setpower(s,rtype,n);add(p,f'resource-{n}',[s],['resource',fam,'value'])
   # legal interface bounds, not a statement about which talent changes max.
   if fam in ('combo','druid_combo','chi','essence'):
    s=copy.deepcopy(b);newcap=cap+1;setpower(s,rtype,maximum=newcap)
    add(p,'resource-cap-roundtrip',[b,s,b],['resource',fam,'maximum','transition'],[[['PLAYER_ENTERING_WORLD']],[['UNIT_MAXPOWER','player',TOKENS[rtype]]],[['UNIT_MAXPOWER','player',TOKENS[rtype]]]])
   if fam=='combo':
    s=copy.deepcopy(b);s['charged_points']=[2,4]
    add(p,'charged-roundtrip',[b,s,b],['resource','charged'],[[['PLAYER_ENTERING_WORLD']],[['UNIT_POWER_POINT_CHARGE','player']],[['UNIT_POWER_POINT_CHARGE','player']]])
   if fam=='shards':
    for raw in (1,9,10,19,25,49):
     s=copy.deepcopy(b);s['powers']['7']['raw']=raw;s['powers']['7']['current']=raw//10
     add(p,f'shards-raw-{raw}',[s],['resource','shards','conversion'])
    s=copy.deepcopy(b);s['powers']['7']['display_mod']=0
    add(p,'shards-zero-modifier',[s],['resource','shards','zero-maximum'])
   if fam=='essence':
    for part in (0,250,500,900):
     s=copy.deepcopy(b);s['powers']['19']['partial']=part
     add(p,f'essence-partial-{part}',[s],['resource','essence','partial'])
    for rate in (0,None,.4):
     s=copy.deepcopy(b);s['powers']['19']['regen']=rate
     add(p,'essence-rate-'+str(rate),[s],['resource','essence','regen'])
  elif fam=='runes':
   for depleted in range(7):
    s=copy.deepcopy(b)
    for i in range(depleted):s['runes'][i]={'start':90+i,'duration':12,'ready':False}
    add(p,f'runes-depleted-{depleted}',[s],['resource','runes'])
   s=copy.deepcopy(b);s['runes'][0]={'start':None,'duration':None,'ready':False}
   add(p,'rune-nil-start',[s],['resource','runes','nil'])
   s2=copy.deepcopy(b);s2['runes'][0]={'start':100,'duration':10,'ready':False}
   add(p,'rune-empty-cooldown-ready',[b,s,s2,b],['resource','runes','transition'])
   s=copy.deepcopy(b);s['runes'][0]={'start':0,'duration':10,'ready':False}
   add(p,'rune-zero-start-is-truthy',[s],['resource','runes','zero'])
  elif fam=='stagger':
   for value in (None,0,300,600,1200):
    s=copy.deepcopy(b);s['stagger']=value;add(p,'stagger-'+str(value),[s],['resource','stagger'])
  else:
   add(p,'no-selected-secondary',[b],['resource','none'],description='基本契约未选择额外资源；不证明不存在光环/技能计数')
  if p['class_token']=='DRUID':
   states=[]
   for typ,form in [(p['primary_seed'],b['identity']['form']),(3,1),(1,5),(0,0),(p['primary_seed'],b['identity']['form'])]:
    s=copy.deepcopy(b);settype(s,typ);s['identity']['form']=form;states.append(s)
   add(p,'druid-forms',states,['primary','resource','form','transition'])
  same=[q for q in ps if q['class_id']==p['class_id']]
  q=same[p['spec_index']%len(same)]
  add(p,'specialization-roundtrip',[b,state(q),b],['health','primary','resource','specialization','transition'])
 return ps,out

def main():
 ps,cs=cases()
 for name,data in [('profiles.json',ps),('cases.json',cs)]:
  (ASSETS/'data'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
 print(f'{len(ps)} specs; {len(cs)} cases; {sum(len(c["steps"])for c in cs)} checkpoints')
if __name__=='__main__':main()
