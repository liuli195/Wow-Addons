"""从同一任务入口核对真实原生参考和离线导出。仅本机角色冒烟。"""
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "projects/sim2gse"))
from task import run_task

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="序列验证 ") as folder:
    result = run_task(ROOT / ".local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc",
                      Path(folder) / "任务", mode="single")
    assert result["status"] == "offline_ready", result["status"]
    assert result["native_reference"]["dps"] > 0
    assert result["native_reference"]["samples"] == 99
    assert result["candidate"]["text"].startswith("!GSE3!")
    assert result["candidate"]["game_validation"] == "not_run"
    assert result["candidate"]["simulation"] == "passed_native_model"

    player = result['controlled_simulation']['report']['sim']['players'][0]
    assert player['stats_pets'], '缺少原生宠物结果'
    exercise = [['auto_attack', 'outbreak'], ['army_of_the_dead'], ['dark_transformation'], ['festering_strike'],
                ['scourge_strike'], ['death_coil'], ['soul_reaper'], ['putrefy'], ['scourge_strike'],
                ['death_coil'], ['festering_strike'], ['scourge_strike']]
    result = run_task(ROOT / '.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc',
                      Path(folder) / '替换路径', program=exercise, mode="single")
    player = result['controlled_simulation']['report']['sim']['players'][0]
    scythe = next(stat for stat in player['stats'] if stat['name'] == 'festering_scythe')
    assert scythe['id'] == 458128 and scythe['num_executes']['mean'] > 0, '替换技能未实际执行'
