from __future__ import annotations
import copy,json,pathlib,platform,shutil,sys,tempfile,time
from wowtestlib import core
from wowtestlib.luaexec import backend,evaluate,LuaExecutionError,literal
ROOT=core.ROOT
ASSETS=core.ASSETS

def selftest(report_path=None):
    began=time.perf_counter();checks=[]
    def check(name,fn):
        try:
            details=fn();checks.append({'name':name,'status':'pass','details':details})
        except Exception as exc:checks.append({'name':name,'status':'fail','message':str(exc)})
    profiles,cases,baseline,manifest=core.data()
    def yes(value,message='assertion failed'):
        if not value:raise AssertionError(message)
    def raises(fn,typ=Exception):
        try:fn()
        except typ:return True
        raise AssertionError('expected exception')
    check('data_integrity_and_40_spec_ids',lambda:core.validate_data(cases,profiles,baseline))
    # 压缩资产不得带生成时刻：带时间戳的容器每次重生成字节都不同，摘要会对不上，
    # 版本管理里产生假差异，也毁掉「重生成可复现」这条承诺。
    def gzip_assets_are_timestamp_free():
        stamped=[]
        for asset in sorted(ASSETS.glob('data/*.gz')):
            head=asset.read_bytes()[:10]
            yes(head[:2]==b'\x1f\x8b','不是 gzip 容器：'+asset.name)
            mtime=int.from_bytes(head[4:8],'little')
            if mtime!=0:stamped.append(f'{asset.name} 的头部时间戳={mtime}')
        yes(not stamped,'压缩资产带生成时刻：'+'; '.join(stamped))
        return {'assets':len(list(ASSETS.glob('data/*.gz')))}
    check('gzip_assets_are_timestamp_free',gzip_assets_are_timestamp_free)
    # 数据检查规则库第一条：切换步骤必须让**被比较的量**可区分。
    # 判据走正式比较口径 diff，不采用「数值不相等」这种宽判据。
    def discriminating():
        gaps=core.discriminating_gaps(cases,baseline)
        yes(not gaps,'无判别力的用例：'+json.dumps(gaps[:3],ensure_ascii=False))
        return {'covered_case_types':list(core.SWITCH_RULE_CASES)}
    check('data_rule_switching_cases_are_discriminating',discriminating)
    def rule_regressions():
        """反面回归：把比例改回相同，规则必须失败——否则它就是个摆设。"""
        fired=[]
        # ① 类型可区分：让切换后的新旧类型比例相同
        cases_a=copy.deepcopy(cases)
        target=next(c for c in cases_a if c['id'].endswith('.primary-type-roundtrip'))
        step=target['steps'][1]['state'];previous=target['steps'][0]['state']
        step['powers'][str(previous['primary']['type'])]['current']=step['powers'][str(step['primary']['type'])]['current']
        fired.append(('类型可区分',bool(core.discriminating_gaps([target],baseline))))
        # ② 前后可区分：让切换后的被比较量与上一检查点完全相同
        cases_b=copy.deepcopy(cases);baseline_b=copy.deepcopy(baseline)
        target=next(c for c in cases_b if c['id'].endswith('.specialization-roundtrip'))
        reference=next(r for r in baseline_b if r['id']==target['id'])
        # 被比较的量取自**参考快照**（health/primary/resource 三个组件都在那里）
        for key in reference['snapshots'][0]:
            reference['snapshots'][1][key]=copy.deepcopy(reference['snapshots'][0][key])
        for key in ('health','primary'):
            target['steps'][1]['state'][key]=copy.deepcopy(target['steps'][0]['state'][key])
        fired.append(('前后可区分',bool(core.discriminating_gaps([target],baseline_b))))
        yes(all(hit for _,hit in fired),'反面回归没有触发：'+json.dumps(fired,ensure_ascii=False))
        return {'regressions_fired':[name for name,_ in fired]}
    check('data_rule_regressions_fire',rule_regressions)
    def timing_contract():
        """把「观测时刻口径」钉成可断言的形状，防止将来被悄悄改动。"""
        driver=(core.ASSETS/'runtime/consumer.lua').read_text('utf-8')
        install=driver.index('ctx.set_state');advance=driver.index('ctx.advance')
        read=driver.index('adapter.snapshot()')   # 取调用点；类型校验里的 adapter.snapshot 不算
        yes(install<advance<read,'执行顺序必须是「安装该步输入 → 推进到该步时间 → 再读观测」')
        yes('ctx.advance(step.settle or 0)'in driver,'约定等待必须显式推进，不得省略或改写')
        # settle 只让实际侧追上**已经定义好的**观测时刻，不得借它移动参考侧的时刻
        bound=1.0
        over=[c['id']for c in cases if any((s.get('settle')or 0)>bound for s in c['steps'])]
        yes(not over,'约定等待超出声明上限：'+','.join(over[:3]))
        # 排空一轮零延迟回调后不得再推进时间（否则参考侧与实际侧观测的不是同一时刻）
        # 顺序是：推进到该步时间 → 投递事件 → 推进约定等待 → 排空零延迟 → **再**读观测
        yes(driver.index('ctx.advance(0)',advance)<read,'读观测前必须先排空零延迟回调')
        return {'order':'set_state → advance → emit → settle → advance(0) → snapshot',
                'settle_bound_seconds':bound}
    check('timing_observation_instant_contract',timing_contract)
    check('boolean_not_equal_to_number',lambda:yes(core.diff(True,1)))
    check('missing_fields_detected',lambda:yes(core.diff({'x':0},{})))
    check('list_length_detected',lambda:yes(core.diff([1],[1,2])))
    check('absolute_float_tolerance',lambda:yes(not core.diff(.3,.1+.2)))
    check('nonfinite_numbers_rejected',lambda:yes(core.diff(1,float('nan'))))
    check('unknown_spec_not_zero_pass',lambda:raises(lambda:core.selection(cases,profiles,'999999'),core.ToolError))
    check('empty_case_selection_not_pass',lambda:raises(lambda:core.selection(cases,profiles,'all','no-such-case'),core.ToolError))
    check('missing_actual_case_not_pass',lambda:yes(core.compare(cases[:1],baseline,[],profiles)['status']=='error'))
    check('duplicate_actual_ids_rejected',lambda:raises(lambda:core.compare(cases[:1],baseline,[baseline[0],baseline[0]],profiles),core.ToolError))
    check('syntax_error_reported',lambda:raises(lambda:evaluate('this is not valid lua!'),LuaExecutionError))
    check('infinite_loop_terminated',lambda:raises(lambda:evaluate('while true do end',.3),LuaExecutionError))
    base=(core.ASSETS/'runtime/base.lua').read_text('utf-8')
    minimal=cases[0]
    def env_test(body):
        return evaluate('local M=(function()\n'+base+'\nend)();local ctx=M.context('+literal(minimal['steps'][0]['state'])+','+literal(minimal['profile'])+',{},{});'+body)
    check('unconfigured_api_input_fails',lambda:yes(env_test("local ok=pcall(function() ctx.env.UnitPower('player',999) end); return M.json({ok=not ok})")['ok']))
    check('unit_event_filter',lambda:yes(env_test("local n=0;local f=ctx.env.CreateFrame('Frame'); f:RegisterUnitEvent('UNIT_HEALTH','player');f:SetScript('OnEvent',function()n=n+1 end);ctx.emit('UNIT_HEALTH','target');ctx.emit('UNIT_HEALTH','player');return M.json({n=n})")['n']==1))
    check('timers_order_and_cancellation',lambda:yes(env_test("local a={};ctx.env.C_Timer.NewTimer(1,function()a[#a+1]=1 end);local t=ctx.env.C_Timer.NewTimer(1,function()a[#a+1]=2 end);t:Cancel();ctx.env.C_Timer.NewTimer(1,function()a[#a+1]=3 end);ctx.advance(1);return M.json(a)")==[1,3]))
    check('nil_rune_tuple_preserved',lambda:yes(env_test("ctx.state.runes[1]={ready=false};local a,b,c=ctx.env.GetRuneCooldown(1);return M.json({ok=a==nil and b==nil and c==false})")['ok']))
    def good_example(name):
        actual,cfg,meta=core.run(cases,profiles,ASSETS/f'examples/{name}/wowtest.json')
        r=core.compare(cases,baseline,actual,profiles,cfg['components'],True)
        yes(r['status']=='pass',str(r['summary']))
        return r['summary']
    check('event_addon_full_matrix',lambda:good_example('event-hud'))
    check('poll_addon_full_matrix',lambda:good_example('poll-hud'))
    subset=core.selection(cases,profiles,'259,267,250,1467,103')
    def determinism():
        a,_,_=core.run(subset,profiles,ASSETS/'examples/event-hud/wowtest.json');b,_,_=core.run(subset,profiles,ASSETS/'examples/event-hud/wowtest.json')
        yes(a==b,'outputs differ');return {'cases':len(a)}
    check('deterministic_repeat',determinism)
    eventsource=(ASSETS/'examples/event-hud/addon.lua').read_text('utf-8')
    def mutation(name,before,after,specs):
        yes(before in eventsource,'mutation marker absent')
        with tempfile.TemporaryDirectory(prefix='wowtest-mutation-')as tmp:
            t=pathlib.Path(tmp)
            for p in(ASSETS/'examples/event-hud').iterdir():
                if p.is_file():shutil.copy2(p,t/p.name)
            (t/'addon.lua').write_text(eventsource.replace(before,after,1),'utf-8')
            selected=core.selection(cases,profiles,specs)
            actual,cfg,_=core.run(selected,profiles,t/'wowtest.json')
            r=core.compare(selected,baseline,actual,profiles,cfg['components'],True)
            yes(r['status']=='difference','mutation was not detected as difference: '+str(r['summary']))
            fail=next(x for x in r['cases']if x['status']=='difference')
            return {'detected_cases':r['summary']['differences'],'first_case':fail['id'],'first_diff':fail['differences'][0]}
    check('mutation_frozen_resource_capacity',lambda:mutation('capacity',"local max=UnitPowerMax('player',t);", "local max=UnitPowerMax('player',t); model.firstCapacity=model.firstCapacity or max; max=model.firstCapacity;",'259'))
    check('mutation_stale_primary_type',lambda:mutation('type',"local pt,token=UnitPowerType('player');", "local pt,token=UnitPowerType('player'); model.firstType=model.firstType or pt;pt=model.firstType;",'259'))
    check('mutation_double_shard_conversion',lambda:mutation('conversion',"UnitPower('player',7,true)/mod", "UnitPower('player',7,true)/mod/mod",'267'))
    check('mutation_missing_sixth_rune',lambda:mutation('runes','r.nodes={};for i=1,6 do','r.nodes={};for i=1,5 do','250'))
    check('mutation_missing_maxpower_event',lambda:mutation('event',"frame:RegisterEvent(event)","if event~='UNIT_MAXPOWER'then frame:RegisterEvent(event) end ",'259'))
    def leaked_timer():
        with tempfile.TemporaryDirectory(prefix='wowtest-leak-')as tmp:
            t=pathlib.Path(tmp)
            for p in(ASSETS/'examples/event-hud').iterdir():
                if p.is_file():shutil.copy2(p,t/p.name)
            (t/'addon.lua').write_text(eventsource.replace('function ns.Start()',"function ns.Start() C_Timer.NewTicker(100,function()end)"),'utf-8')
            actual,cfg,_=core.run(cases[:1],profiles,t/'wowtest.json');r=core.compare(cases[:1],baseline,actual,profiles,require_cleanup=True)
            yes(r['status']=='error');yes(any(x['stage']=='cleanup'for x in r['cases'][0]['errors']))
            return 'live timer detected before forced environment disposal'
    check('cleanup_does_not_hide_timer_leak',leaked_timer)
    def path_check():
        with tempfile.TemporaryDirectory()as tmp:
            return raises(lambda:core.relative_file(pathlib.Path(tmp),'../escape.lua'),core.ToolError)
    check('project_path_escape_rejected',path_check)
    def init_tests():
        import wowtest
        with tempfile.TemporaryDirectory(prefix='wowtest-project-')as tmp:
            wowtest.init(tmp,'Example')
            raises(lambda:wowtest.init(tmp,'Again'),core.ToolError)
            wowtest.install_skill(tmp,'codex');wowtest.install_skill(tmp,'codex')
            p=pathlib.Path(tmp)/'.agents/skills/wow-addon-test/SKILL.md';p.write_text('user changes','utf-8')
            raises(lambda:wowtest.install_skill(tmp,'codex'),core.ToolError)
        return 'init and skill do not overwrite user edits'
    check('non_destructive_init_and_skill_install',init_tests)
    def no_answers():
        import inspect
        yes("pop('resource_kind'"in inspect.getsource(core.run))
        raw=core.load_json(core.ASSETS/'data/cases.json')
        yes(all('reference_observations'not in c for c in raw))
        return 'input artifacts and oracle artifacts are separate; not an adversarial sandbox'
    check('input_answer_separation',no_answers)
    def unicode_project():
        with tempfile.TemporaryDirectory(prefix='wowtest-')as tmp:
            dest=pathlib.Path(tmp)/'项目 路径';shutil.copytree(ASSETS/'examples/event-hud',dest)
            selected=core.selection(cases,profiles,'250,259','roundtrip')
            actual,cfg,_=core.run(selected,profiles,dest/'wowtest.json')
            report=core.compare(selected,baseline,actual,profiles,cfg['components'],True)
            yes(report['status']=='pass');return report['summary']
    check('unicode_and_space_project_path',unicode_project)
    def installed_entry():
        import wowtest,subprocess
        with tempfile.TemporaryDirectory()as tmp:
            d=wowtest.install_skill(tmp,'claude')
            script=pathlib.Path(d['skill_path'])/'scripts/wowtest.py'
            p=subprocess.run([sys.executable,str(script),'validate','--json'],cwd=tmp,capture_output=True,text=True,timeout=20)
            yes(p.returncode==0,p.stderr);yes(json.loads(p.stdout)['specs']==40)
        return 'installed skill resolves shared tool from another working directory'
    check('installed_skill_entry_works',installed_entry)
    def lexer():
        from reference.verify_upstream import tokens,contains
        yes(tokens("local x='-- end'; -- comment\n return x")==['local','x','=','\'-- end\'',';','return','x'])
        yes(contains(tokens('function X() return 0 end'),tokens('return 0')))
        yes(not contains(tokens('function X() return 1 end'),tokens('return 0')))
        return 'strings/comments and token matching checked; network fetch not executed'
    check('source_audit_lexer',lexer)
    from reference.generate import generate
    def native_again():
        out=generate(cases,profiles);yes(out==baseline,'native regeneration mismatch');return {'cases':len(out)}
    check('native_method_regeneration_exact',native_again)
    result={'status':'pass'if all(c['status']=='pass'for c in checks)else'fail','checks':len(checks),'passed':sum(c['status']=='pass'for c in checks),'results':checks,
      'environment':{'platform':platform.platform(),'python':sys.version.split()[0],'lua':backend()},'duration_seconds':round(time.perf_counter()-began,3),
      'not_executed':['Windows installation/runtime','Actual MYUI integration','Real WoW client/talents/Secret Values','Codex or Claude end-to-end autonomous onboarding']}
    # 落盘目标由调用方决定：默认写到系统临时目录，**不往技能目录里写受跟踪资产**
    target=pathlib.Path(report_path) if report_path else pathlib.Path(tempfile.gettempdir())/'wowtest-selftest.json'
    core.write_json(target,result)
    return result
if __name__=='__main__':print(json.dumps(selftest(),ensure_ascii=False,indent=2))
