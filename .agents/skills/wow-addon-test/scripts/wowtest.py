#!/usr/bin/env python3
"""Local WoW logic comparison tool. Run `python wowtest.py --help`."""
from __future__ import annotations
import argparse,json,pathlib,platform,shutil,sys
from wowtestlib import __version__
from wowtestlib import core
from wowtestlib.luaexec import backend,LuaExecutionError
ROOT=pathlib.Path(__file__).resolve().parents[1]   # 技能根：本文件位于 <技能根>/scripts/

# 面向代理的唯一有界出口。
# 预算只约束**展示**：完整报告始终写进 --output 指定的产物位置，不因缩裁而少跑任何用例。
OUTPUT_BUDGET_BYTES=16*1024
TOOL_ERROR_LIMIT=2048
PREVIEW_LIMIT=10
FIELD_LIMIT=512
NESTING_LIMIT=6

# 逐级收紧的口径。裁剪一次**不保证**字节数：字典的键数不受上面那些限制约束，
# 字段一多照样能超出预算，所以必须一级级收到真的装下为止。
BOUND_LEVELS=((PREVIEW_LIMIT,FIELD_LIMIT,NESTING_LIMIT),(4,160,4),(2,64,3),(0,24,2))

def _bound(node,preview,field,nesting,depth=0):
    """把结构压到可安全输出的形状：限条数、限字段长度、限嵌套深度。"""
    if depth>nesting:return '…'
    if isinstance(node,str):
        return node if len(node)<=field else node[:field]+'…'
    if isinstance(node,list):
        head=[_bound(x,preview,field,nesting,depth+1) for x in node[:preview]]
        if len(node)>preview:head.append({'omitted':len(node)-preview})
        return head
    if isinstance(node,dict):
        return {k:_bound(v,preview,field,nesting,depth+1) for k,v in node.items()}
    return node

def _encode(obj):
    return json.dumps(obj,ensure_ascii=False,indent=2)

def _fits(text):
    # 末尾那个换行是 print 真的会写出去的一个字节，也要算进预算
    return len(text.encode('utf-8'))+1<=OUTPUT_BUDGET_BYTES

def emit(obj,args):
    body={'status':obj['status'],**obj['summary']} if (not getattr(args,'json',False) and 'summary'in obj) else obj
    # 条数／字段／嵌套上限**与字节预算无关，一律先执行**：只在超预算时才裁剪的话，
    # "11 条很短的结果"会原样全部输出——上限形同虚设。
    first=_bound(body,PREVIEW_LIMIT,FIELD_LIMIT,NESTING_LIMIT)
    if not isinstance(first,dict):first={'result':first}
    text=_encode(first)
    if _encode(body)==text and _fits(text):
        print(text);return
    for preview,field,nesting in BOUND_LEVELS:
        bounded=_bound(body,preview,field,nesting)
        if not isinstance(bounded,dict):bounded={'result':bounded}
        bounded['details_truncated']=True
        bounded['budget_bytes']=OUTPUT_BUDGET_BYTES
        text=_encode(bounded)
        if _fits(text):
            print(text);return
    # 最后一道：连收紧后的结构都装不下时，只留状态与计数——**预算优先于细节**
    minimal={'status':body.get('status') if isinstance(body,dict) else None,
             'summary':body.get('summary') if isinstance(body,dict) else None,
             'note':'输出超出预算，已只保留状态与计数；完整结果见 --output',
             'details_truncated':True,'budget_bytes':OUTPUT_BUDGET_BYTES}
    text=_encode(minimal)
    while not _fits(text) and minimal.get('summary'):
        minimal['summary']={k:minimal['summary'][k] for k in list(minimal['summary'])[:len(minimal['summary'])//2]}
        text=_encode(minimal)
    print(text if _fits(text) else _encode({'status':minimal.get('status'),'details_truncated':True,
                                            'budget_bytes':OUTPUT_BUDGET_BYTES}))

def install_skill(project,agent):
    project=pathlib.Path(project).resolve()
    if not project.is_dir():raise core.ToolError('project does not exist')
    folder='.agents'if agent=='codex'else '.claude'
    dst=project/folder/'skills'/'wow-addon-test'
    source=ROOT                       # 技能即工具：整份技能目录就是安装源
    for p in source.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            target=dst/p.relative_to(source)
            if target.exists() and target.read_bytes()!=p.read_bytes():raise core.ToolError('拒绝覆盖不同内容: '+str(target))
    dst.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,dst,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    return {'skill_path':str(dst),'shared_source':str(source),'note':'技能自包含：工具随技能分发，无需额外定位文件。'}

def init(project,addon_name):
    project=pathlib.Path(project).resolve()
    if not project.is_dir():raise core.ToolError('project does not exist')
    dest=project/'.wow-test';dest.mkdir(exist_ok=True)
    cfg={'schema_version':1,'project_root':'..','addon_name':addon_name,'adapter':'.wow-test/adapter.lua','files':[], 'specs':'all','components':['health','primary','resource'],'require_cleanup':True,'timeout_seconds':60}
    template=(ROOT/'references/adapter-template.lua').read_text('utf-8')
    for path,content in [(dest/'wowtest.json',json.dumps(cfg,ensure_ascii=False,indent=2)+'\n'),(dest/'adapter.lua',template)]:
        if path.exists():raise core.ToolError('接入文件已存在，拒绝覆盖: '+str(path))
    core.write_json(dest/'wowtest.json',cfg);(dest/'adapter.lua').write_text(template,'utf-8')
    return {'created':[str(dest/'wowtest.json'),str(dest/'adapter.lua')],'status':'requires_ai_integration','next':'AI 必须读取真实插件，填写生产文件和适配；空模板不能通过。'}

def main(argv=None):
    parser=argparse.ArgumentParser(description='魔兽插件纯逻辑测试：本地 CLI（命令行）+ Skill（技能），无服务。')
    parser.add_argument('--version',action='version',version=__version__)
    sub=parser.add_subparsers(dest='cmd',required=True)
    for name in ('doctor','catalog','validate'):
        p=sub.add_parser(name);p.add_argument('--json',action='store_true')
        # 输出预算只约束**屏幕上那一份**；完整内容必须另有去处，否则会被静默截掉拿不回来
        p.add_argument('--output',default=None,help='把完整结果落盘（不受输出预算限制）')
    p=sub.add_parser('selftest');p.add_argument('--json',action='store_true')
    p.add_argument('--output',default=None,help='自测报告落盘路径；默认写系统临时目录，不写技能目录')
    p=sub.add_parser('init');p.add_argument('--project',default='.');p.add_argument('--name',default='MyAddon');p.add_argument('--json',action='store_true')
    p=sub.add_parser('install-skill');p.add_argument('--project',default='.');p.add_argument('--agent',choices=['codex','claude'],required=True);p.add_argument('--json',action='store_true')
    p=sub.add_parser('run');p.add_argument('--config',required=True);p.add_argument('--specs');p.add_argument('--case');p.add_argument('--output',default='.wow-test/report.json');p.add_argument('--save-actual');p.add_argument('--json',action='store_true')
    p=sub.add_parser('compare');p.add_argument('--actual',required=True);p.add_argument('--specs',default='all');p.add_argument('--case');p.add_argument('--components',default='health,primary,resource');p.add_argument('--output',default='.wow-test/report.json');p.add_argument('--json',action='store_true')
    p=sub.add_parser('export');p.add_argument('--output',required=True);p.add_argument('--specs',default='all');p.add_argument('--case');p.add_argument('--inputs-only',action='store_true');p.add_argument('--json',action='store_true')
    p=sub.add_parser('reference-check');p.add_argument('--output',default='.wow-test/reference-check.json',
                                                       help='把完整参考复核结果落盘（屏幕输出仍受预算限制）')
    p.add_argument('--json',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.cmd=='init':emit(init(args.project,args.name),args);return 0
        if args.cmd=='install-skill':emit(install_skill(args.project,args.agent),args);return 0
        profiles,cases,baseline,manifest=core.data()
        if args.cmd=='doctor':
            b=backend();obj={'version':__version__,'python':sys.version.split()[0],'platform':platform.platform(),'data_integrity':'pass','lua':b,'scope':manifest['scope'],'note':'联网只用于可选依赖安装/源码复核；测试不联网。'}
            emit(obj,args);return 0 if b['available']else 2
        if args.cmd=='catalog':
            obj={'version':__version__,'data_summary':core.validate_data(cases,profiles,baseline),'scope':manifest['scope'],'profiles':profiles,'contract':'references/CONTRACT.md','sources':'assets/reference/sources.json'}
            if args.output:core.write_json(args.output,obj)
            emit(obj,args);return 0
        if args.cmd=='validate':
            obj=core.validate_data(cases,profiles,baseline)
            if args.output:core.write_json(args.output,obj)
            emit(obj,args);return 0
        if args.cmd=='selftest':
            from tests.verify import selftest
            obj=selftest(getattr(args,'output',None));emit(obj,args);return 0 if obj['status']=='pass'else 1
        if args.cmd=='reference-check':
            from reference.generate import generate
            actual=generate(cases,profiles)
            r=core.compare(cases,baseline,actual,profiles)
        elif args.cmd=='run':
            cfg,_,_,_=core.config(args.config)
            selected=core.selection(cases,profiles,args.specs or cfg.get('specs','all'),args.case)
            actual,cfg,meta=core.run(selected,profiles,args.config)
            # 配置声明了项目投影就用它出正式判定，否则退回通用比较。
            # 由**工具自己**给出最终结论，而不是工具报一堆差异、再由仓库侧程序另行放行。
            builtin=core.compare(selected,baseline,actual,profiles,cfg['components'],cfg.get('require_cleanup',True))
            projection=core.load_projection(cfg)
            if projection is not None:
                # 判定用项目投影，但执行失败与账目汇总仍归工具：投影只改比较口径，
                # 不能把"缺用例输出/未加载生产文件/清理失败"一并取消掉
                r=core.project_verdict(projection,cfg,selected,baseline,actual)
                for section in ('limits',):
                    if section in builtin:r.setdefault(section,builtin[section])
                r=core.finalize_verdict(r,builtin,selected,profiles,
                                        cfg['components'],cfg.get('require_cleanup',True))
                meta['projection_sha256']=cfg.get('projection_sha256')
                meta['verdict']='project-projection'
            else:
                r=builtin
                meta['verdict']='builtin-comparison'
            r['execution']=meta
            if args.save_actual:core.write_json(args.save_actual,actual)
        elif args.cmd=='compare':
            comp=args.components.split(',')
            if not comp or not set(comp)<=set(core.COMPONENTS):raise core.ToolError('invalid components')
            selected=core.selection(cases,profiles,args.specs,args.case)
            r=core.compare(selected,baseline,core.load_json(args.actual),profiles,comp)
            r['execution']={'kind':'external-observations','note':'compare 不验证外部代码是否真实加载；完整接入使用 run。'}
        elif args.cmd=='export':
            selected=core.selection(cases,profiles,args.specs,args.case);bm={x['id']:x for x in baseline}
            out=[]
            for c in selected:
                v=json.loads(json.dumps(c));v['reference']=manifest['reference'];v['contract_version']=1;v['tool_version']=__version__
                if not args.inputs_only:v['reference_observations']=bm[c['id']]['snapshots']
                else:
                    for step in v['steps']:step['state'].pop('resource_kind',None)
                out.append(v)
            p=pathlib.Path(args.output)
            if p.exists():raise core.ToolError('拒绝覆盖已有导出文件')
            core.write_json(p,out);emit({'exported':len(out),'path':str(p)},args);return 0
        else:raise core.ToolError('unknown command')
        r['reference']=manifest['reference'];r['validation_scope']='synthetic-basic-logic'
        core.write_json(args.output,r)
        pathlib.Path(args.output).with_suffix('.md').write_text(core.markdown(r),'utf-8')
        emit(r,args)
        return 2 if r['status']=='error'else 1 if r['status']=='difference'else 0
    except (core.ToolError,LuaExecutionError,KeyError,TypeError,ValueError,OSError)as exc:
        # 失败也要有上限：Lua 侧的错误信息可以很长，原样打到 stderr 同样会淹掉代理
        raw=str(exc);cut=len(raw)>TOOL_ERROR_LIMIT
        print(json.dumps({'status':'tool_error',
                          'message':raw[:TOOL_ERROR_LIMIT]+('…（已截断）'if cut else''),
                          'details_truncated':cut,'budget_bytes':TOOL_ERROR_LIMIT},
                         ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
