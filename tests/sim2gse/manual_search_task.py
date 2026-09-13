"""同一产品入口的真实角色搜索验收；完整默认预算，不缩短战斗。"""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'projects/sim2gse'))
from task import run_task


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    destination=args.output or ROOT/'.local/tests'/('sim2gse-search-'+uuid.uuid4().hex[:12])
    source=ROOT/'.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc'
    raw=source.read_bytes()
    started=time.monotonic()
    result=run_task(source,destination)
    assert result['status'] in ('completed','validation_incomplete'),result
    assert result['candidate']['text'].startswith('!GSE3!')
    assert (destination/'input.original.simc').read_bytes()==raw
    assert result['candidate']['game_validation']=='not_run'
    assert result['candidate']['simulation']=='passed_native_model'
    assert result['search']['candidate_count']<=1000
    assert len(result['search']['starts'])>=2
    final=result['final']['scenarios']
    if result['independent_validation_complete']:
        assert set(final)=={'nominal','jitter','slow','pause','phase'}
        for scenario in final.values():
            assert scenario['effective_samples']==[1980,1980]
            assert len(scenario['candidate'])==len(scenario['seed'])==20
            assert all(row['samples']==99 for row in scenario['candidate']+scenario['seed'])
    else:
        assert result['status']=='validation_incomplete'
    evidence=dict(status=result['status'],elapsed_seconds=result['elapsed_seconds'],
                  wall_seconds=time.monotonic()-started,candidates=result['search']['candidate_count'],
                  completed_batches=result['completed_batches'],improvement=result['improvement'],
                  independently_tested=result['independent_validation_complete'],
                  scenarios={name:row['comparison'] for name,row in final.items()},game_validation='not_run')
    (destination/'acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
