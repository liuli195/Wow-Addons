"""Versioned data, trusted-addon execution and strict comparison. No model/API service."""
from __future__ import annotations
import copy, gzip, hashlib, json, math, pathlib, re
from .luaexec import evaluate, literal
ROOT=pathlib.Path(__file__).resolve().parents[2]      # 技能根（本文件位于 <技能根>/scripts/wowtestlib/）
ASSETS=ROOT/'assets'                                  # 工具的输入、参考与运行时资产
COMPONENTS=('health','primary','resource')
class ToolError(RuntimeError): pass

def resolve_asset(path):
    """资产名 → 实际文件；大体积资产以压缩容器存放，明文不存在时回退到 .gz。"""
    p=pathlib.Path(path)
    if p.is_file():return p
    packed=p.with_name(p.name+'.gz')
    if packed.is_file():return packed
    return p

def read_asset_bytes(path):
    """读资产的**原始内容**：压缩容器就地解压，保证摘要与明文一致。"""
    p=resolve_asset(path)
    raw=p.read_bytes()
    return gzip.decompress(raw) if p.suffix=='.gz' else raw

def load_json(path):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ToolError(f'duplicate JSON key: {k}')
            out[k]=v
        return out
    try:
        text=read_asset_bytes(path).decode('utf-8-sig')
        return json.loads(text,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ToolError('nonfinite JSON number')))
    except (OSError,ValueError) as exc:raise ToolError(str(exc)) from exc

def write_json(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(p)

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def check_integrity():
    manifest=load_json(ASSETS/'data/manifest.json')
    for name,expected in manifest['sha256'].items():
        p=(ASSETS/name).resolve()
        if not p.is_relative_to(ASSETS.resolve())or not resolve_asset(p).is_file():raise ToolError('manifest file missing or invalid: '+name)
        # 清单摘要按**解压后的原始内容**校验：压缩只是存放方式，不改变被校验的字节
        if hashlib.sha256(read_asset_bytes(p)).hexdigest()!=expected:raise ToolError('基线/参照完整性检查失败: '+name+'；不要通过修改清单掩盖差异')
    return manifest

# ---- 数据检查规则库 ---------------------------------------------------------
# 规则库 ≠ 用例库：这里放的是**针对数据本身**的机械检查，可长期逐条沉淀。
# 第一条只解决一个已看到的形状：**切换步骤没有让被比较的量发生变化**——
# 数值不动，测试就分不出「跟着变了」与「压根没理它」，那条用例的绿不说明任何事。
SWITCH_RULE_CASES=('primary-type-roundtrip','specialization-roundtrip','druid-forms')

def _power_ratio(state,power_type):
    entry=state['powers'].get(str(power_type))
    return None if entry is None else entry['current']/(entry['maximum'] or 1)

def _target_value(snapshot):
    """该检查点上**本次要验证的那个量**：主资源比例。

    这三类用例验证的都是"切换之后主资源还读得对不对"，所以目标量就是主资源比例。
    把生命和职业资源一起打包进来会有两个毛病：生命随便变一点就能把"主资源根本没变"
    掩盖过去（规格明令禁止的"无关组件变化代替"）；而且打包成元组之后 diff() 只做
    整体相等比较，连浮点容差都用不上。
    """
    primary=snapshot['primary']
    return primary['value']/(primary['maximum'] or 1)

def _identity(state):
    i=state['identity']
    return (i.get('class_id'),i.get('spec_index'),i.get('form'))

def discriminating_gaps(cases,baseline):
    """返回无判别力清单。判定一律走正式比较口径 diff，不采用「数值不相等」这种宽判据。"""
    reference={row['id']:row for row in baseline}
    gaps=[]
    for case in cases:
        kind=case['id'].split('.',1)[1]
        if kind not in SWITCH_RULE_CASES:continue
        snapshots=reference[case['id']]['snapshots']
        steps=case['steps']
        for index in range(1,len(steps)):
            before,after=steps[index-1]['state'],steps[index]['state']
            switched=(before['primary']['type']!=after['primary']['type'])or(_identity(before)!=_identity(after))
            if not switched:continue
            # 类型可区分：切换后的同一份输入里，新旧两种类型的比例必须能被正式比较区分
            if before['primary']['type']!=after['primary']['type']:
                old_ratio=_power_ratio(after,before['primary']['type'])
                new_ratio=_power_ratio(after,after['primary']['type'])
                if old_ratio is not None and not diff(old_ratio,new_ratio):
                    gaps.append({'case':case['id'],'step':index+1,'rule':'类型可区分',
                                 'detail':f'新旧类型比例同为 {new_ratio}，固定读某类型的实现无法被区分'})
            # 前后可区分：**本次要验证的那个量**必须相对上一检查点可区分，无关组件的变化不能代替
            if not diff(_target_value(snapshots[index-1]),_target_value(snapshots[index])):
                gaps.append({'case':case['id'],'step':index+1,'rule':'前后可区分',
                             'detail':'切换后被比较的量与上一检查点不可区分，沿用旧读数的实现无法被检出'})
    return gaps

def validate_data(cases,profiles,baseline):
    if len(profiles)!=40 or len({p['spec_id']for p in profiles})!=40:raise ToolError('本版应有 40 个唯一专精')
    pids={p['spec_id']for p in profiles};ids=set()
    for c in cases:
        if not isinstance(c.get('id'),str)or c['id']in ids:raise ToolError('invalid or duplicate case ID')
        ids.add(c['id'])
        if c.get('spec_id')not in pids or not c.get('steps'):raise ToolError('invalid case identity or empty steps')
        last=-math.inf
        for step in c['steps']:
            s=step['state'];t=s['time']
            if not isinstance(t,(int,float))or isinstance(t,bool)or not math.isfinite(t)or t<last:raise ToolError('invalid time')
            last=t
            if not all(k in s for k in ('identity','health','unit','primary','powers','runes','charged_points','resource_kind','stagger')):raise ToolError('missing state fields')
            for k in ('current','maximum'):
                if type(s['health'][k])not in (int,float)or not math.isfinite(s['health'][k])or s['health'][k]<0:raise ToolError('invalid health')
            for r in s['powers'].values():
                for k in ('current','maximum','raw','raw_maximum','display_mod','partial','regen','regen_interrupted'):
                    if k not in r:raise ToolError('power input missing: '+k)
                for k in ('current','maximum','raw','raw_maximum','display_mod','partial'):
                    if type(r[k])not in(int,float)or not math.isfinite(r[k])or r[k]<0:raise ToolError('invalid power '+k)
            if str(s['primary']['type'])not in s['powers']:raise ToolError('primary not configured')
            for k in ('connected','exists','dead','ghost','in_vehicle','in_combat','vehicle_has_combo'):
                if type(s['unit'][k])is not bool:raise ToolError('invalid unit boolean '+k)
            if s['identity']['spec_id']not in pids:raise ToolError('unknown step specialization')
            if len(s['runes'])!=6:raise ToolError('expected six rune inputs')
            for r in s['runes']:
                if type(r.get('ready'))is not bool:raise ToolError('rune ready must be boolean')
                for k in ('start','duration'):
                    if k not in r or(r[k]is not None and type(r[k])not in(int,float)):raise ToolError('invalid rune value')
            if not isinstance(step.get('events'),list):raise ToolError('missing event list')
            for e in step['events']:
                if not e or not isinstance(e[0],str):raise ToolError('invalid event')
            if type(step.get('settle',0))not in(int,float)or step.get('settle',0)<0:raise ToolError('invalid settling time')
    bids=[r['id']for r in baseline]
    if len(bids)!=len(set(bids))or set(bids)!=ids:raise ToolError('baseline IDs mismatch')
    bm={r['id']:r for r in baseline}
    for c in cases:
        rows=bm[c['id']]['snapshots']
        if len(rows)!=len(c['steps']):raise ToolError('baseline checkpoint count mismatch')
        for row in rows:
            if set(row)!=set(COMPONENTS):raise ToolError('baseline must contain three components')
    return {'specs':len(profiles),'cases':len(cases),'checkpoints':sum(len(c['steps'])for c in cases)}

def data():
    manifest=check_integrity()
    p=load_json(ASSETS/'data/profiles.json');c=load_json(ASSETS/'data/cases.json');b=load_json(ASSETS/'data/baselines.json')
    validate_data(c,p,b);return p,c,b,manifest

def selection(cases,profiles,specs='all',case_filter=None):
    if specs=='all':s={p['spec_id']for p in profiles}
    else:
        try:s=set(int(x)for x in (specs.split(',')if isinstance(specs,str)else specs))
        except (ValueError,TypeError)as exc:raise ToolError('specs 必须是 all 或专精 ID 列表')from exc
    known={p['spec_id']for p in profiles}
    if not s or not s<=known:raise ToolError('专精列表为空或包含未知 ID: '+str(s-known))
    result=[c for c in cases if c['spec_id']in s and(not case_filter or case_filter in c['id'])]
    if not result:raise ToolError('没有匹配用例；不能将零用例算为通过')
    return result

def relative_file(root,name):
    if not isinstance(name,str)or not name:raise ToolError('invalid relative file path')
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve())or not p.is_file():raise ToolError('源文件不存在或越出项目目录: '+name)
    return p

def config(path):
    path=pathlib.Path(path).resolve();c=load_json(path)
    if c.get('schema_version')!=1:raise ToolError('config schema_version must be 1')
    root=(path.parent/c.get('project_root','.')).resolve()
    if not root.is_dir():raise ToolError('project root does not exist')
    if not isinstance(c.get('files'),list)or not c['files']or len(set(c['files']))!=len(c['files']):raise ToolError('files 必须列出真实生产文件，不可为空或重复')
    components=c.get('components',list(COMPONENTS))
    if not components or len(set(components))!=len(components)or not set(components)<=set(COMPONENTS):raise ToolError('invalid components')
    if type(c.get('require_cleanup',True))is not bool:raise ToolError('require_cleanup must be boolean')
    sources={n:relative_file(root,n).read_text('utf-8-sig')for n in c['files']}
    ap=relative_file(root,c['adapter'])
    if c['adapter']in sources:raise ToolError('adapter must not be listed as a production file')
    prohibited={'baselines.json','native.lua','manifest.json'}
    if any(pathlib.Path(n).name in prohibited for n in sources):raise ToolError('不得将参考答案加载到被测代码')
    timeout=c.get('timeout_seconds',60)
    if type(timeout)not in(int,float)or timeout<=0 or timeout>600:raise ToolError('timeout must be 0..600 seconds')
    # 项目专属的投影判定：插件实际输出与工具标准输出不同形时，由项目提供这一层。
    # 声明了就必须可用——坏掉时显式失败，**不得静默退回通用比较**（那会得出另一套结论）
    projection=c.get('projection')
    if projection is not None:
        c['projection_path']=str(relative_file(root,projection))
        c['projection_sha256']=hashlib.sha256(pathlib.Path(c['projection_path']).read_bytes()).hexdigest()
    c['components']=components
    return c,root,sources,ap.read_text('utf-8-sig')

def load_projection(cfg):
    """加载配置声明的投影判定模块；未声明返回 None。接口：judge(cases, baseline, actual)。"""
    path=cfg.get('projection_path')
    if not path:return None
    import importlib.util
    name='wowtest_projection_'+hashlib.sha256(path.encode('utf-8')).hexdigest()[:12]
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise ToolError('无法加载投影模块: '+path)
    module=importlib.util.module_from_spec(spec)
    try:spec.loader.exec_module(module)
    except Exception as exc:raise ToolError('投影模块加载失败: '+str(exc))
    if not callable(getattr(module,'judge',None)):
        raise ToolError('投影模块必须提供 judge(cases, baseline, actual)')
    return module

def project_verdict(module,cfg,cases,baseline,actual):
    """用项目投影产出正式判定。结果必须是可用报告，缺 status/summary 即失败。"""
    try:verdict=module.judge(cases,baseline,actual)
    except Exception as exc:raise ToolError('投影判定失败: '+str(exc))
    if not isinstance(verdict,dict)or not isinstance(verdict.get('summary'),dict)or not verdict.get('status'):
        raise ToolError('投影模块必须返回带 status 与 summary 的报告')
    verdict.setdefault('projection_sha256',cfg.get('projection_sha256'))
    return verdict

def run(cases,profiles,config_path):
    cfg,root,sources,adapter=config(config_path)
    stripped=[]
    for c in cases:
        item={k:copy.deepcopy(c[k])for k in ('id','profile','steps')}
        for step in item['steps']:step['state'].pop('resource_kind',None)
        stripped.append(item)
    public_profiles=[{k:p[k]for k in('spec_id','spec_index','spec_name','class_id','class_token','class_name','role')}for p in profiles]
    base=(ASSETS/'runtime/base.lua').read_text('utf-8');driver=(ASSETS/'runtime/consumer.lua').read_text('utf-8')
    source='local M=(function()\n'+base+'\nend)(); local run=(function()\n'+driver+'\nend)();return M.json(run(M,'+','.join(literal(v)for v in(stripped,public_profiles,adapter,sources,cfg.get('addon_name','TestAddon')))+'))'
    actual=evaluate(source,cfg.get('timeout_seconds',60))
    if not isinstance(actual,list):raise ToolError('consumer output must be a list')
    # Verify that actual production files were loaded, not only an adapter that reimplements them.
    for row in actual:
        missing=set(cfg['files'])-set(row.get('loaded',[]))
        if missing:row.setdefault('errors',[]).append({'stage':'production-load','message':'实际未加载: '+','.join(sorted(missing))})
    metadata={'addon_name':cfg.get('addon_name','TestAddon'),'source_sha256':{n:hashlib.sha256(text.encode()).hexdigest()for n,text in sources.items()},'adapter_sha256':hashlib.sha256(adapter.encode()).hexdigest()}
    return actual,cfg,metadata

MISSING='<missing>'
def diff(expected,actual,path='$',atol=1e-8):
    result=[]
    if type(expected)is bool or type(actual)is bool:
        if type(expected)is not type(actual)or expected!=actual:result.append({'path':path,'expected':expected,'actual':actual})
    elif type(expected)in(int,float)and type(actual)in(int,float):
        if not math.isfinite(actual)or not math.isclose(expected,actual,rel_tol=0,abs_tol=atol):result.append({'path':path,'expected':expected,'actual':actual})
    elif isinstance(expected,dict)and isinstance(actual,dict):
        for k in sorted(set(expected)|set(actual)):
            if k not in expected or k not in actual:result.append({'path':path+'.'+str(k),'expected':expected.get(k,MISSING),'actual':actual.get(k,MISSING)})
            else:result.extend(diff(expected[k],actual[k],path+'.'+str(k),atol))
    elif isinstance(expected,list)and isinstance(actual,list):
        if len(expected)!=len(actual):result.append({'path':path+'.length','expected':len(expected),'actual':len(actual)})
        for i,(e,a)in enumerate(zip(expected,actual),1):result.extend(diff(e,a,f'{path}[{i}]',atol))
    elif type(expected)is not type(actual)or expected!=actual:result.append({'path':path,'expected':expected,'actual':actual})
    return result

def compare(cases,baseline,actual,profiles,components=COMPONENTS,require_cleanup=False):
    if not isinstance(actual,list):raise ToolError('actual JSON must be an array')
    ids=[r.get('id')for r in actual if isinstance(r,dict)]
    if len(ids)!=len(actual)or None in ids or len(ids)!=len(set(ids)):raise ToolError('actual output has invalid/duplicate IDs')
    wanted={c['id']for c in cases};extras=set(ids)-wanted
    if extras:raise ToolError('actual output contains unselected cases: '+','.join(sorted(extras)[:5]))
    bm={r['id']:r for r in baseline};am={r['id']:r for r in actual}
    rows=[];passed=differed=errors=0;checks=0;cleanup_failures=0
    for c in cases:
        a=am.get(c['id']);r={'id':c['id'],'spec_id':c['spec_id'],'status':'pass','differences':[],'errors':[],'checkpoints':len(c['steps'])}
        if a is None:r['errors'].append({'stage':'output','message':'missing case output'})
        else:
            ae=a.get('errors',[])
            if not isinstance(ae,list):raise ToolError('errors must be array')
            r['errors'].extend(ae)
            obs=a.get('snapshots')
            if not isinstance(obs,list)or len(obs)!=len(c['steps']):r['errors'].append({'stage':'output','message':'missing or extra checkpoints'})
            else:
                for index,(expected,got)in enumerate(zip(bm[c['id']]['snapshots'],obs),1):
                    if not isinstance(got,dict):r['errors'].append({'stage':'output','step':index,'message':'snapshot is not object'});continue
                    e={k:expected[k]for k in components};g={k:got[k]for k in components if k in got}
                    for d in diff(e,g):d.update(step=index,label=c['steps'][index-1]['label']);r['differences'].append(d)
                    checks+=1
            if require_cleanup:
                clean=a.get('cleanup')
                if not isinstance(clean,dict)or clean!={'event_subscriptions':0,'live_timers':0,'update_scripts':0}:
                    cleanup_failures+=1
                    r['errors'].append({'stage':'cleanup','message':'停止后仍有订阅/定时器，或没有清理报告','actual':clean})
        if r['errors']:r['status']='error';errors+=1
        elif r['differences']:r['status']='difference';differed+=1
        else:passed+=1
        rows.append(r)
    coverage=[]
    for p in profiles:
        selected=[r for r in rows if r['spec_id']==p['spec_id']]
        coverage.append({'spec_id':p['spec_id'],'class_name':p['class_name'],'spec_name':p['spec_name'],'cases':len(selected),'passed':sum(r['status']=='pass'for r in selected),
         'status':'not_selected'if not selected else 'pass'if all(r['status']=='pass'for r in selected)else 'issues',
         'components':list(components)if selected else [],'native_resource_seed':p['resource_seed'],'extra_resource_gaps':p['extra_resource_gaps'],'gameplay_verified':False})
    # 清理检查：**适用性与结果分成两个字段**。
    # 「不适用」不是「通过」——它表示这条断言根本没有执行，不能被算成已满足。
    cleanup={'applicability':'applied' if require_cleanup else 'not_applicable',
     'status':('failed' if cleanup_failures else 'passed') if require_cleanup else 'not_run',
     'reason':'' if require_cleanup else '该插件没有停止生命周期，本项不适用；未执行的断言不计为通过'}
    return {'schema_version':1,'status':'error'if errors else 'difference'if differed else 'pass',
     'cleanup':cleanup,
     'summary':{'cases':len(cases),'passed':passed,'differences':differed,'errors':errors,'compared_checkpoints':checks,'selected_specs':sum(x['cases']>0 for x in coverage)},
     'limits':['普通数值/接口级人工场景；不是实机天赋配置验证','原生参考是已标注方法摘录，不是完整客户端或完整 XML 初始化','未覆盖的额外职业计数见逐专精 gaps；none 只表示本版未选择次级组件','受限值、污染、受保护执行、画面不在本版验收内'],
     'coverage':coverage,'cases':rows}

def markdown(report):
    s=report['summary'];parts=['# 魔兽插件逻辑比较报告',f"\n状态：**{report['status']}**\n",'| 用例 | 通过 | 差异 | 环境/执行错误 | 检查点 | 专精 |','|---:|---:|---:|---:|---:|---:|',f"| {s['cases']} | {s['passed']} | {s['differences']} | {s['errors']} | {s['compared_checkpoints']} | {s['selected_specs']} |",'\n## 差异与错误']
    issues=[r for r in report['cases']if r['status']!='pass']
    if not issues:parts.append('本次选择范围内未发现差异。未选择/未支持范围不计入通过。')
    for r in issues[:50]:
        parts.append('\n### '+r['id'])
        for e in r['errors']:parts.append('```json\n'+json.dumps(e,ensure_ascii=False)+'\n```')
        for d in r['differences'][:20]:
            # 项目投影可以用「组件 · 字段」描述一处差异，不必套用内置比较的 JSON 路径
            where=d.get('path') or ' · '.join(str(x)for x in (d.get('component'),d.get('kind'))if x)
            got=d.get('actual',d.get('observed'))
            step=d.get('step')
            parts.append(f"步骤 {step} · `{where}`：预期 `{d.get('expected')}`，实际 `{got}`。")
    if len(issues)>50:parts.append('更多细节见同名 JSON 完整报告。')
    parts.extend(['\n## 专精覆盖','| 职业/专精 | ID | 用例 | 通过 | 状态 | 额外缺口 |','|---|---:|---:|---:|---|---|'])
    for r in report['coverage']:parts.append(f"| {r['class_name']}/{r['spec_name']} | {r['spec_id']} | {r['cases']} | {r['passed']} | {r['status']} | {'；'.join(r['extra_resource_gaps']) or '—'} |")
    cleanup=report.get('cleanup') or {}
    if cleanup:
        label={'applied':'已适用','not_applicable':'不适用'}.get(cleanup.get('applicability'),cleanup.get('applicability'))
        state={'passed':'通过','failed':'失败','not_run':'未执行（不计为通过）'}.get(cleanup.get('status'),cleanup.get('status'))
        parts.append(f"\n## 清理检查\n\n适用性：**{label}**　结果：**{state}**\n\n{cleanup.get('reason') or ''}")
    parts.extend(['\n## 验证边界']+report['limits'])
    return '\n'.join(parts)+'\n'
