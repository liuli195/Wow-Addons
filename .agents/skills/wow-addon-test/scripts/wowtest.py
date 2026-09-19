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
PREVIEW_LIMIT=10
FIELD_LIMIT=512
NESTING_LIMIT=6

def _bound(node,depth=0):
    """把结构压到可安全输出的形状：限条数、限字段长度、限嵌套深度。"""
    if depth>NESTING_LIMIT:return '…'
    if isinstance(node,str):
        return node if len(node)<=FIELD_LIMIT else node[:FIELD_LIMIT]+'…'
    if isinstance(node,list):
        head=[_bound(x,depth+1) for x in node[:PREVIEW_LIMIT]]
        if len(node)>PREVIEW_LIMIT:head.append({'omitted':len(node)-PREVIEW_LIMIT})
        return head
    if isinstance(node,dict):
        return {k:_bound(v,depth+1) for k,v in node.items()}
    return node

def _encode(obj):
    return json.dumps(obj,ensure_ascii=False,indent=2)

def emit(obj,args):
    body={'status':obj['status'],**obj['summary']} if (not getattr(args,'json',False) and 'summary'in obj) else obj
    text=_encode(body)
    if len(text.encode('utf-8'))>OUTPUT_BUDGET_BYTES:
        bounded=_bound(body)
        if not isinstance(bounded,dict):bounded={'result':bounded}
        bounded['details_truncated']=True
        bounded['budget_bytes']=OUTPUT_BUDGET_BYTES
        text=_encode(bounded)
    print(text)

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
    p=sub.add_parser('reference-check');p.add_argument('--json',action='store_true')
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
            r=core.compare(cases,baseline,actual,profiles);emit(r,args);return 0 if r['status']=='pass'else 1
        if args.cmd=='run':
            cfg,_,_,_=core.config(args.config)
            selected=core.selection(cases,profiles,args.specs or cfg.get('specs','all'),args.case)
            actual,cfg,meta=core.run(selected,profiles,args.config)
            r=core.compare(selected,baseline,actual,profiles,cfg['components'],cfg.get('require_cleanup',True));r['execution']=meta
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
        print(json.dumps({'status':'tool_error','message':str(exc)},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
