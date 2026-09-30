"""运行和汇总 Sim2GSE 固定 A/B Benchmark（基准测试）。"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,sqlite3,statistics,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];BASELINE="efd9b71a9bf934a5cb990f314651e17ace73e9d1";CONTRACT="search-v1"
PHASE2_BASELINE="cc94eb7253004ba1bff74e029fd6f3a8f23681d2"
PROFILES={"current":ROOT/".local/sim2gse/ui-tasks/tasks/b2a776ffb0aa4c0d815e5beed1a2ede7/input.original.simc","talent-trinket":ROOT/".local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc","equipment":ROOT/".local/sim2gse/ui-tasks/tasks/9d0657821b9b48d2a339db860f709e5b/input.original.simc"}
SEEDS=tuple(range(20260912,20260922));CONFIG={"total_budget_seconds":600,"search_budget_seconds":420,"candidate_limit":1000,"round_candidate_limit":16,"no_improvement_rounds":5,"batch_targets":[32,128,512],"validation_batches":4,"final_batches":20,"iterations":100,"final_iterations":100,"max_processes":2,"scenarios":["nominal","jitter","slow","pause","phase"],"input_interval_ms":200,"reset_events":[]}
def _sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _git(*a):return subprocess.run(["git",*a],cwd=ROOT,check=True,text=True,stdout=subprocess.PIPE).stdout.strip()
def _json(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def materialize(root,commit,label,worktree=False):
 base=root/f"{label}-source";marker=base/"source-manifest.json";source=base/"projects/sim2gse"
 names=(_git("ls-files","--cached","--others","--exclude-standard","--","projects/sim2gse") if worktree else _git("ls-tree","-r","--name-only",commit,"--","projects/sim2gse")).splitlines()
 originals={name:_sha(ROOT/name) for name in names} if worktree else None
 if marker.is_file():
  m=json.loads(marker.read_text());
  if m["commit"]==commit and m.get("worktree_files")==originals and all((base/p).is_file() and _sha(base/p)==h for p,h in m["files"].items()):return source
  raise RuntimeError("源码快照不完整")
 pending=root/f".{label}-{uuid.uuid4().hex}.pending"
 try:
  for name in names:
   p=pending/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes() if worktree else subprocess.run(["git","show",f"{commit}:{name}"],cwd=ROOT,check=True,stdout=subprocess.PIPE).stdout)
   if worktree and _sha(p)!=originals[name]:raise RuntimeError("创建快照时源码已变化")
  replacement=f'ROOT = Path({str(ROOT)!r})'
  for name in ("engine.py","codec.py","macro_interpreter.py","simulation_config.py"):
   p=pending/"projects/sim2gse"/name;p.write_text(p.read_text().replace("ROOT = Path(__file__).resolve().parents[2]",replacement))
  files={p.relative_to(pending).as_posix():_sha(p) for p in sorted((pending/"projects/sim2gse").rglob("*")) if p.is_file()};(pending/"source-manifest.json").write_text(json.dumps({"commit":commit,"files":files,"worktree_files":originals},indent=2))
  try:os.replace(pending,base)
  except FileExistsError:shutil.rmtree(pending)
 finally:
  if pending.exists():shutil.rmtree(pending)
 return materialize(root,commit,label,worktree=worktree)
def behavior_id(c):
 cp=c.get("compiled_program",{});clicks=[[] if x.get("kind")=="EmptyClick" else list(x.get("commands",[])) for x in cp.get("clicks",[])];cast=[]
 for r in cp.get("castsequences",[]):
  reset=r.get("reset") or {};cast.append({"step":r["step"],"members":list(r["members"]),"reset":{"timeout_seconds":reset.get("timeout_seconds"),"flags":sorted(set(reset.get("flags",[])))}})
 return hashlib.sha256(_json({"start_step":1,"sequence_reset":"end","clicks":clicks,"castsequences":cast}).encode()).hexdigest()
def extract(result,out,wall):
 s=result.get("search") or {};records=s.get("records") or [];final=(result.get("final") or {}).get("scenarios") or {};selected="candidate_mean_dps" if result.get("selected_candidate_key")==result.get("locked_candidate_key") else "control_mean_dps";dps=[v.get("comparison",{}).get(selected) for v in final.values()];dps=[v for v in dps if isinstance(v,(int,float))]
 starts=s.get("native_batch_starts");starts=starts if starts is not None else len(list((out/"batches").glob("*/native.json")))
 return {"status":result.get("status","failed"),"evidence_complete":len(dps)==5,"wall_seconds":wall,"final_dps":statistics.median(dps) if dps else None,"candidate_scores":[r["score"] for r in records if isinstance(r.get("score"),(int,float))],"common_unique_candidates":len({behavior_id(r["candidate"]) for r in records if r.get("candidate")}),"native_batch_starts":starts,"batch_requests":s.get("batch_requests"),"batch_cache_hits":s.get("batch_cache_hits"),"canonicalized_duplicates":s.get("canonicalized_duplicates")}
def run(source,profile,out,seed):
 cfg=dict(CONFIG,random_seed=seed);code="import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from task import run_task;run_task(Path(sys.argv[2]),Path(sys.argv[3]),search_config=json.loads(sys.argv[4]))";start=time.monotonic();p=subprocess.Popen([sys.executable,"-c",code,str(source),str(profile),str(out),_json(cfg)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);timeline=[];seen=0;search_wall=None;search_started=None
 while p.poll() is None:
  database=out/"task.sqlite3"
  if database.is_file():
   try:
    with sqlite3.connect(database,timeout=.1) as db: row=db.execute("SELECT value FROM state WHERE id=1").fetchone()
    state=json.loads(row[0]) if row else {};archive=state.get("archive") or []
    if search_started is None and state.get("phase")=="search":search_started=time.monotonic()
    if search_wall is None and search_started is not None and state.get("phase") in ("final","done"):search_wall=time.monotonic()-search_started
    for record in archive[seen:]:timeline.append({"evaluation":len(timeline)+1,"wall_seconds":time.monotonic()-(search_started or start),"score":record.get("score")})
    seen=len(archive)
   except (sqlite3.Error,ValueError,OSError):pass
  time.sleep(.1)
 stdout,stderr=p.communicate();wall=time.monotonic()-start;search_wall=search_wall if search_wall is not None else (time.monotonic()-search_started if search_started is not None else wall)
 if not (out/"result.json").is_file():raise RuntimeError(stderr[-4000:] or "任务没有生成结果")
 row=extract(json.loads((out/"result.json").read_text()),out,wall)
 for score in row["candidate_scores"][len(timeline):]:timeline.append({"evaluation":len(timeline)+1,"wall_seconds":search_wall,"score":score})
 row["candidate_timeline"]=timeline
 try:
  invocations=[json.loads(path.read_text()) for path in out.rglob("invocation.json")];commands=[x["command"] for x in invocations]
  row["simc_total_iterations"]=sum(int(next((x.split("=",1)[1] for x in reversed(command) if x.startswith("iterations=")),"100")) for command in commands)
  row["engine_identities"]=sorted({_json(x["identity"]) for x in invocations})
 except (ValueError,OSError,KeyError,TypeError):row["simc_total_iterations"]=None
 row["search_wall_seconds"]=search_wall;row["evidence_complete"]=row["evidence_complete"] and row.get("simc_total_iterations") is not None and bool(row.get("engine_identities"));row.update(process_returncode=p.returncode,stderr_tail=stderr[-4000:]);return row
def med(rows,key):
 v=[r[key] for r in rows if isinstance(r.get(key),(int,float))];return statistics.median(v) if v else None
def distribution(rows,key,higher_is_better=True):
 v=sorted(r[key] for r in rows if isinstance(r.get(key),(int,float)))
 return {"median":statistics.median(v),"iqr":[statistics.quantiles(v,n=4)[0],statistics.quantiles(v,n=4)[2]],"worst":min(v) if higher_is_better else max(v)} if len(v)>=2 else ({"median":v[0],"iqr":[v[0],v[0]],"worst":v[0]} if v else None)
def summarize_profile(b,c):
 def complete(row):return bool(row.get("evidence_complete")) and isinstance(row.get("simc_total_iterations"),int) and row["simc_total_iterations"]>0 and bool(row.get("engine_identities"))
 complete_baseline=[row for row in b if complete(row)];threshold=med(complete_baseline,"final_dps") if len(complete_baseline)==len(b) else None;threshold=threshold*.95 if threshold is not None else None
 def side(rows):
  final_rows=[row for row in rows if complete(row)];reached=[next((i+1 for i,v in enumerate(r["candidate_scores"]) if v>=threshold),None) for r in final_rows] if threshold is not None else [];raw_times=[next((x["wall_seconds"] for x in r.get("candidate_timeline",[]) if isinstance(x.get("score"),(int,float)) and x["score"]>=threshold),None) for r in final_rows] if threshold is not None else [];times=[value if value is not None else CONFIG["search_budget_seconds"] for value in raw_times];throughput=[r["common_unique_candidates"]/r.get("search_wall_seconds",r["wall_seconds"])*60 for r in final_rows];reached_rows=[{"value":x} for x in reached if x is not None];time_rows=[{"value":x} for x in times];return {"runs":len(rows),"complete_runs":len(final_rows),"final_dps":distribution(final_rows,"final_dps"),"final_dps_median":med(final_rows,"final_dps"),"native_batch_starts":distribution(final_rows,"native_batch_starts",False),"native_batch_starts_median":med(final_rows,"native_batch_starts"),"simc_total_iterations":distribution(final_rows,"simc_total_iterations",False),"new_candidates_per_minute":{"median":statistics.median(throughput),"iqr":[statistics.quantiles(throughput,n=4)[0],statistics.quantiles(throughput,n=4)[2]],"worst":min(throughput)} if throughput else None,"new_candidates_per_minute_median":statistics.median(throughput) if throughput else None,"threshold_evaluations":distribution(reached_rows,"value",False),"threshold_evaluations_median":statistics.median([x for x in reached if x is not None]) if reached and all(x is not None for x in reached) else None,"threshold_wall_seconds":distribution(time_rows,"value",False),"threshold_wall_seconds_median":statistics.median(times) if times else None,"threshold_success_rate":sum(x is not None for x in reached)/len(final_rows) if threshold is not None and final_rows else None}
 bs,cs=side(b),side(c)
 is_complete=complete
 def gain(old,new,inverse=False):return None if old in (None,0) or new is None else ((old-new)/old if inverse else (new-old)/old)
 primary={"final_dps_change":gain(bs["final_dps_median"],cs["final_dps_median"])};efficiency={"threshold_wall_time_gain":gain(bs["threshold_wall_seconds_median"],cs["threshold_wall_seconds_median"],True),"baseline_success_rate":bs["threshold_success_rate"],"current_success_rate":cs["threshold_success_rate"]};metrics={"simc_reduction":gain(bs["native_batch_starts_median"],cs["native_batch_starts_median"],True),"throughput_gain":gain(bs["new_candidates_per_minute_median"],cs["new_candidates_per_minute_median"]),"threshold_evaluation_gain":gain(bs["threshold_evaluations_median"],cs["threshold_evaluations_median"],True)};identities={tuple(r.get("engine_identities",[])) for r in b+c};complete=bs["complete_runs"]==len(b) and cs["complete_runs"]==len(c) and len(identities)==1
 def reached_time(row):
  if threshold is None or not is_complete(row):return None
  return next((point['wall_seconds'] for point in row.get('candidate_timeline',[]) if isinstance(point.get('score'),(int,float)) and point['score']>=threshold),CONFIG['search_budget_seconds'])
 pairs=[]
 for old,new in zip(b,c):
  old_time,new_time=reached_time(old),reached_time(new);paired_complete=is_complete(old) and is_complete(new)
  pairs.append({'complete':paired_complete,'baseline':old,'current':new,'final_dps_change':gain(old.get('final_dps'),new.get('final_dps')) if paired_complete else None,'baseline_threshold_wall_seconds':old_time,'current_threshold_wall_seconds':new_time,'threshold_wall_time_gain':gain(old_time,new_time,True) if paired_complete else None})
 return {"threshold":threshold,"baseline":bs,"current":cs,"primary_result":primary,"efficiency_result":efficiency,"metrics":metrics,"pairs":pairs,"status":"ready_for_human" if complete else "insufficient_evidence"}
def summarize(root,seed_count=5,profiles=None):
 def load(path):return json.loads(path.read_text()) if path.is_file() else {"evidence_complete":False,"final_dps":None,"native_batch_starts":None,"common_unique_candidates":0,"wall_seconds":1,"search_wall_seconds":1,"candidate_scores":[],"candidate_timeline":[],"simc_total_iterations":None,"engine_identities":[]}
 seeds=SEEDS[:seed_count];profiles={p:summarize_profile(*[[load(root/side/p/str(seed)/"summary.json") for seed in seeds] for side in ("baseline","current")]) for p in (PROFILES if profiles is None else profiles)};status="insufficient_evidence" if any(v["status"]=="insufficient_evidence" for v in profiles.values()) else "ready_for_human";result={"contract":CONTRACT,"decision":"human_required","seeds":list(seeds),"profiles":profiles,"status":status};(root/"overview.json").write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
def main():
 p=argparse.ArgumentParser();p.add_argument("--run-id",required=True);p.add_argument("--summarize",action="store_true");p.add_argument("--phase2",action="store_true");p.add_argument("--seed-count",type=int,choices=(5,10),default=5);p.add_argument("--side",choices=("baseline","current"));p.add_argument("--profile",choices=tuple(PROFILES));p.add_argument("--seed",type=int,choices=SEEDS);a=p.parse_args()
 if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}",a.run_id):p.error("run-id 必须是单个小写路径段")
 root=ROOT/".local/sim2gse/benchmarks"/CONTRACT/a.run_id
 if a.summarize:print(json.dumps(summarize(root,3 if a.phase2 else a.seed_count,profiles=("current",) if a.phase2 else None),ensure_ascii=False));return 0
 if a.side is None or a.profile is None or a.seed is None:p.error("单次运行需要 side、profile 和 seed")
 if a.phase2 and (a.profile!="current" or a.seed not in SEEDS[:3]):p.error("第二阶段只运行当前真实配置和前三组配对条件")
 commit=(PHASE2_BASELINE if a.phase2 else BASELINE) if a.side=="baseline" else _git("rev-parse","HEAD");source=materialize(root,commit,a.side,worktree=a.phase2 and a.side=="current");e=root/a.side/a.profile/str(a.seed)
 if e.exists():raise SystemExit(f"证据目录已存在: {e}")
 e.mkdir(parents=True);copy=root/"inputs"/f"{a.profile}.simc";copy.parent.mkdir(parents=True,exist_ok=True)
 if not copy.exists():shutil.copy2(PROFILES[a.profile],copy)
 manifest={"contract":CONTRACT,"side":a.side,"profile":a.profile,"profile_sha256":_sha(copy),"seed":a.seed,"source_commit":commit,"source_manifest_sha256":_sha(source.parents[1]/"source-manifest.json"),"config":dict(CONFIG,random_seed=a.seed)};(e/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2));row=run(source,copy,e/"task",a.seed);(e/"summary.json").write_text(json.dumps(row,ensure_ascii=False,indent=2));print(json.dumps(row,ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
