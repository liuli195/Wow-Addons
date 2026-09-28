"""运行 Sim2GSE 固定 A/B Benchmark（基准测试）并保存可复核证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
BASELINE = "efd9b71a9bf934a5cb990f314651e17ace73e9d1"
CONTRACT = "search-v1"
PROFILES = {
    "current": ROOT / ".local/sim2gse/ui-tasks/tasks/b2a776ffb0aa4c0d815e5beed1a2ede7/input.original.simc",
    "talent-trinket": ROOT / ".local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc",
    "equipment": ROOT / ".local/sim2gse/ui-tasks/tasks/9d0657821b9b48d2a339db860f709e5b/input.original.simc",
}
SEEDS = tuple(range(20260912, 20260917))
CONFIG = {
    "total_budget_seconds": 600,
    "search_budget_seconds": 420,
    "candidate_limit": 1000,
    "round_candidate_limit": 16,
    "no_improvement_rounds": 5,
    "batch_targets": [32, 128, 512],
    "validation_batches": 4,
    "final_batches": 20,
    "iterations": 100,
    "final_iterations": 100,
    "max_processes": 2,
    "scenarios": ["nominal", "jitter", "slow", "pause", "phase"],
    "input_interval_ms": 200,
    "reset_events": [],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def _materialize_baseline(folder: Path) -> Path:
    source = folder / "baseline-source" / "projects" / "sim2gse"
    if source.exists():
        return source
    names = _git("ls-tree", "-r", "--name-only", BASELINE, "--", "projects/sim2gse").splitlines()
    for name in names:
        target = folder / "baseline-source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.run(
            ["git", "show", f"{BASELINE}:{name}"], cwd=ROOT, check=True,
            stdout=subprocess.PIPE).stdout)
    replacement = f'ROOT = Path({str(ROOT)!r})'
    for name in ("engine.py", "codec.py", "macro_interpreter.py", "simulation_config.py"):
        path = source / name
        text = path.read_text(encoding="utf-8")
        text = text.replace("ROOT = Path(__file__).resolve().parents[2]", replacement)
        path.write_text(text, encoding="utf-8")
    return source


def _run(source_root: Path, profile: Path, output: Path, seed: int) -> dict:
    config = dict(CONFIG, random_seed=seed)
    code = (
        "import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "from task import run_task;"
        "r=run_task(Path(sys.argv[2]),Path(sys.argv[3]),search_config=json.loads(sys.argv[4]));"
        "print(json.dumps({'status':r['status']}))"
    )
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-c", code, str(source_root), str(profile), str(output),
         json.dumps(config, separators=(",", ":"))], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wall = time.monotonic() - started
    if completed.returncode:
        raise RuntimeError(completed.stderr[-4000:])
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    search = result["search"]
    starts = search.get("native_batch_starts")
    if starts is None:
        starts = len(list((output / "batches").glob("*/native.json")))
    final_dps = statistics.median(
        scenario["comparison"]["candidate_mean_dps"]
        for scenario in result["final"]["scenarios"].values())
    return {
        "status": result["status"], "wall_seconds": wall, "final_dps": final_dps,
        "candidate_count": search["candidate_count"],
        "unique_candidates": search["unique_candidates"],
        "native_batch_starts": starts,
        "batch_requests": search.get("batch_requests"),
        "batch_cache_hits": search.get("batch_cache_hits"),
        "canonicalized_duplicates": search.get("canonicalized_duplicates"),
        "result": str((output / "result.json").relative_to(output.parents[2])).replace("\\", "/"),
    }


def _quartiles(values):
    ordered = sorted(values)
    return statistics.median(ordered), statistics.quantiles(ordered, n=4)[0], statistics.quantiles(ordered, n=4)[2]


def summarize(rows: list[dict]) -> dict:
    dps, starts = [r["final_dps"] for r in rows], [r["native_batch_starts"] for r in rows]
    throughput = [r["unique_candidates"] / r["wall_seconds"] * 60 for r in rows]
    return {
        "runs": len(rows), "final_dps_median": statistics.median(dps),
        "final_dps_iqr": list(_quartiles(dps)[1:]), "final_dps_worst": min(dps),
        "native_batch_starts_median": statistics.median(starts),
        "new_candidates_per_minute_median": statistics.median(throughput),
        "success_rate": sum(r["status"] == "completed" for r in rows) / len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--side", choices=("baseline", "current"), required=True)
    parser.add_argument("--profile", choices=tuple(PROFILES), required=True)
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    args = parser.parse_args()
    run_root = ROOT / ".local/sim2gse/benchmarks" / CONTRACT / args.run_id
    evidence = run_root / args.side / args.profile / str(args.seed)
    if evidence.exists():
        raise SystemExit(f"证据目录已存在: {evidence}")
    evidence.mkdir(parents=True)
    copied = run_root / "inputs" / f"{args.profile}.simc"
    copied.parent.mkdir(parents=True, exist_ok=True)
    if not copied.exists():
        shutil.copy2(PROFILES[args.profile], copied)
    source = (_materialize_baseline(run_root) if args.side == "baseline"
              else ROOT / "projects/sim2gse")
    manifest = {
        "contract": CONTRACT, "side": args.side, "profile": args.profile,
        "profile_sha256": _sha256(copied), "seed": args.seed,
        "baseline_commit": BASELINE, "current_commit": _git("rev-parse", "HEAD"),
        "config": dict(CONFIG, random_seed=args.seed),
    }
    (evidence / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    row = _run(source, copied, evidence / "task", args.seed)
    (evidence / "summary.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
