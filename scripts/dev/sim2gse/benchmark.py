"""运行和汇总 Sim2GSE 固定 A/B Benchmark（基准测试）。"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,sqlite3,statistics,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];BASELINE="efd9b71a9bf934a5cb990f314651e17ace73e9d1";CONTRACT="search-v1"
PROFILES={"current":ROOT/".local/sim2gse/ui-tasks/tasks/b2a776ffb0aa4c0d815e5beed1a2ede7/input.original.simc","talent-trinket":ROOT/".local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc","equipment":ROOT/".local/sim2gse/ui-tasks/tasks/9d0657821b9b48d2a339db860f709e5b/input.original.simc"}
SEEDS=tuple(range(20260912,20260922));CONFIG={"total_budget_seconds":600,"search_budget_seconds":420,"candidate_limit":1000,"round_candidate_limit":16,"no_improvement_rounds":5,"batch_targets":[32,128,512],"validation_batches":4,"final_batches":20,"iterations":100,"final_iterations":100,"max_processes":2,"scenarios":["nominal","jitter","slow","pause","phase"],"input_interval_ms":200,"reset_events":[]}
def _sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _git(*a):return subprocess.run(["git",*a],cwd=ROOT,check=True,text=True,stdout=subprocess.PIPE).stdout.strip()
def _json(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def materialize(root,commit,label):
 base=root/f"{label}-source";marker=base/"source-manifest.json";source=base/"projects/sim2gse"
 if marker.is_file():
  m=json.loads(marker.read_text());
  if m["commit"]==commit and all((base/p).is_file() and _sha(base/p)==h for p,h in m["files"].items()):return source
  raise RuntimeError("源码快照不完整")
 pending=root/f".{label}-{uuid.uuid4().hex}.pending";names=_git("ls-tree","-r","--name-only",commit,"--","projects/sim2gse").splitlines()
 try:
  for name in names:
   p=pending/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(subprocess.run(["git","show",f"{commit}:{name}"],cwd=ROOT,check=True,stdout=subprocess.PIPE).stdout)
  replacement=f'ROOT = Path({str(ROOT)!r})'
  for name in ("engine.py","codec.py","macro_interpreter.py","simulation_config.py"):
   p=pending/"projects/sim2gse"/name;p.write_text(p.read_text().replace("ROOT = Path(__file__).resolve().parents[2]",replacement))
  files={p.relative_to(pending).as_posix():_sha(p) for p in sorted((pending/"projects/sim2gse").rglob("*")) if p.is_file()};(pending/"source-manifest.json").write_text(json.dumps({"commit":commit,"files":files},indent=2))
  try:os.replace(pending,base)
  except FileExistsError:shutil.rmtree(pending)
 finally:
  if pending.exists():shutil.rmtree(pending)
 return materialize(root,commit,label)
def behavior_id(c):
 cp=c.get("compiled_program",{});clicks=[[] if x.get("kind")=="EmptyClick" else list(x.get("commands",[])) for x in cp.get("clicks",[])];cast=[]
 for r in cp.get("castsequences",[]):
  reset=r.get("reset") or {};cast.append({"step":r["step"],"members":list(r["members"]),"reset":{"timeout":reset.get("timeout"),"flags":sorted(set(reset.get("flags",[])))}})
 return hashlib.sha256(_json({"start_step":1,"sequence_reset":"end","clicks":clicks,"castsequences":cast}).encode()).hexdigest()
def extract(result,out,wall):
 s=result.get("search") or {};records=s.get("records") or [];final=(result.get("final") or {}).get("scenarios") or {};selected="candidate_mean_dps" if result.get("selected_candidate_key")==result.get("locked_candidate_key") else "control_mean_dps";dps=[v.get("comparison",{}).get(selected) for v in final.values()];dps=[v for v in dps if isinstance(v,(int,float))]
 starts=s.get("native_batch_starts");starts=starts if starts is not None else len(list((out/"batches").glob("*/native.json")))
 return {"status":result.get("status","failed"),"evidence_complete":len(dps)==5,"wall_seconds":wall,"final_dps":statistics.median(dps) if dps else None,"candidate_scores":[r["score"] for r in records if isinstance(r.get("score"),(int,float))],"common_unique_candidates":len({behavior_id(r["candidate"]) for r in records if r.get("candidate")}),"native_batch_starts":starts,"batch_requests":s.get("batch_requests"),"batch_cache_hits":s.get("batch_cache_hits"),"canonicalized_duplicates":s.get("canonicalized_duplicates")}
def run(source,profile,out,seed):
 cfg=dict(CONFIG,random_seed=seed);code="import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from task import run_task;run_task(Path(sys.argv[2]),Path(sys.argv[3]),search_config=json.loads(sys.argv[4]))";start=time.monotonic();p=subprocess.Popen([sys.executable,"-c",code,str(source),str(profile),str(out),_json(cfg)],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);timeline=[];seen=0
 while p.poll() is None:
  database=out/"task.sqlite3"
  if database.is_file():
   try:
    with sqlite3.connect(database,timeout=.1) as db: row=db.execute("SELECT value FROM state WHERE id=1").fetchone()
    archive=(json.loads(row[0]).get("archive") or []) if row else []
    for record in archive[seen:]:timeline.append({"evaluation":len(timeline)+1,"wall_seconds":time.monotonic()-start,"score":record.get("score")})
    seen=len(archive)
   except (sqlite3.Error,ValueError,OSError):pass
  time.sleep(.1)
 stdout,stderr=p.communicate();wall=time.monotonic()-start;search_wall=max([x["wall_seconds"] for x in timeline],default=wall)
 if not (out/"result.json").is_file():raise RuntimeError(stderr[-4000:] or "任务没有生成结果")
 row=extract(json.loads((out/"result.json").read_text()),out,wall)
 for score in row["candidate_scores"][len(timeline):]:timeline.append({"evaluation":len(timeline)+1,"wall_seconds":wall,"score":score})
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
 threshold=med(b,"final_dps");threshold=threshold*.95 if threshold is not None else None
 def side(rows):
  reached=[next((i+1 for i,v in enumerate(r["candidate_scores"]) if threshold is not None and v>=threshold),None) for r in rows];times=[next((x["wall_seconds"] for x in r.get("candidate_timeline",[]) if threshold is not None and isinstance(x.get("score"),(int,float)) and x["score"]>=threshold),None) for r in rows];throughput=[r["common_unique_candidates"]/r.get("search_wall_seconds",r["wall_seconds"])*60 for r in rows];reached_rows=[{"value":x} for x in reached if x is not None];time_rows=[{"value":x} for x in times if x is not None];return {"runs":len(rows),"complete_runs":sum(r["evidence_complete"] for r in rows),"final_dps":distribution(rows,"final_dps"),"final_dps_median":med(rows,"final_dps"),"native_batch_starts":distribution(rows,"native_batch_starts",False),"native_batch_starts_median":med(rows,"native_batch_starts"),"simc_total_iterations":distribution(rows,"simc_total_iterations",False),"new_candidates_per_minute":{"median":statistics.median(throughput),"iqr":[statistics.quantiles(throughput,n=4)[0],statistics.quantiles(throughput,n=4)[2]],"worst":min(throughput)},"new_candidates_per_minute_median":statistics.median(throughput),"threshold_evaluations":distribution(reached_rows,"value",False),"threshold_evaluations_median":statistics.median([x for x in reached if x is not None]) if all(x is not None for x in reached) else None,"threshold_wall_seconds":distribution(time_rows,"value",False),"threshold_wall_seconds_median":statistics.median([x for x in times if x is not None]) if all(x is not None for x in times) else None,"threshold_success_rate":sum(x is not None for x in reached)/len(rows)}
 bs,cs=side(b),side(c)
 def gain(old,new,inverse=False):return None if old in (None,0) or new is None else ((old-new)/old if inverse else (new-old)/old)
 m={"dps_change":gain(bs["final_dps_median"],cs["final_dps_median"]),"simc_reduction":gain(bs["native_batch_starts_median"],cs["native_batch_starts_median"],True),"throughput_gain":gain(bs["new_candidates_per_minute_median"],cs["new_candidates_per_minute_median"]),"threshold_evaluation_gain":gain(bs["threshold_evaluations_median"],cs["threshold_evaluations_median"],True),"threshold_wall_time_gain":gain(bs["threshold_wall_seconds_median"],cs["threshold_wall_seconds_median"],True)};identities={tuple(r.get("engine_identities",[])) for r in b+c};complete=bs["complete_runs"]==len(b) and cs["complete_runs"]==len(c) and len(identities)==1;passed=complete and m["dps_change"] is not None and m["dps_change"]>=-.005 and m["simc_reduction"] is not None and m["simc_reduction"]>=.20 and m["throughput_gain"] is not None and m["throughput_gain"]>=.10
 return {"threshold":threshold,"baseline":bs,"current":cs,"metrics":m,"status":"passed" if passed else ("failed" if complete else "insufficient_evidence")}
def summarize(root):
 def build(seeds):return {p:summarize_profile(*[[json.loads((root/side/p/str(seed)/"summary.json").read_text()) for seed in seeds] for side in ("baseline","current")]) for p in PROFILES}
 first=build(SEEDS[:5]);reasons=[]
 for name,value in first.items():
  m=value["metrics"];primary=max(m.get("threshold_evaluation_gain") or -1,m.get("threshold_evaluation_gain") or -1)
  if value["status"]=="insufficient_evidence":reasons.append(name+": evidence")
  if abs(primary-.15)<=.02:reasons.append(name+": primary boundary")
  if m.get("dps_change") is not None and abs(m["dps_change"]+.005)<=.002:reasons.append(name+": dps boundary")
  if (m.get("threshold_evaluation_gain") or 0)*(m.get("threshold_wall_time_gain") or 0)<0:reasons.append(name+": metric direction")
 needs=bool(reasons);extra_ready=all((root/side/p/str(seed)/"summary.json").is_file() for side in ("baseline","current") for p in PROFILES for seed in SEEDS[5:]);seeds=SEEDS if needs and extra_ready else SEEDS[:5];profiles=build(seeds);primary=sum(max(v["metrics"].get("threshold_evaluation_gain") or -1,v["metrics"].get("threshold_evaluation_gain") or -1)>=.15 for v in profiles.values());status="insufficient_evidence" if needs and not extra_ready else ("failed" if any(v["status"]=="failed" for v in profiles.values()) else ("insufficient_evidence" if any(v["status"]=="insufficient_evidence" for v in profiles.values()) or primary<2 else "passed"));result={"contract":CONTRACT,"seeds":list(seeds),"needs_expansion":needs,"expansion_reasons":reasons,"extra_seeds_ready":extra_ready,"profiles":profiles,"primary_gain_profiles":primary,"status":status};(root/"overview.json").write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
def main():
 p=argparse.ArgumentParser();p.add_argument("--run-id",required=True);p.add_argument("--summarize",action="store_true");p.add_argument("--side",choices=("baseline","current"));p.add_argument("--profile",choices=tuple(PROFILES));p.add_argument("--seed",type=int,choices=SEEDS);a=p.parse_args()
 if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}",a.run_id):p.error("run-id 必须是单个小写路径段")
 root=ROOT/".local/sim2gse/benchmarks"/CONTRACT/a.run_id
 if a.summarize:print(json.dumps(summarize(root),ensure_ascii=False));return 0
 if a.side is None or a.profile is None or a.seed is None:p.error("单次运行需要 side、profile 和 seed")
 commit=BASELINE if a.side=="baseline" else _git("rev-parse","HEAD");source=materialize(root,commit,a.side);e=root/a.side/a.profile/str(a.seed)
 if e.exists():raise SystemExit(f"证据目录已存在: {e}")
 e.mkdir(parents=True);copy=root/"inputs"/f"{a.profile}.simc";copy.parent.mkdir(parents=True,exist_ok=True)
 if not copy.exists():shutil.copy2(PROFILES[a.profile],copy)
 manifest={"contract":CONTRACT,"side":a.side,"profile":a.profile,"profile_sha256":_sha(copy),"seed":a.seed,"source_commit":commit,"source_manifest_sha256":_sha(source.parents[1]/"source-manifest.json"),"config":dict(CONFIG,random_seed=a.seed)};(e/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2));row=run(source,copy,e/"task",a.seed);(e/"summary.json").write_text(json.dumps(row,ensure_ascii=False,indent=2));print(json.dumps(row,ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
