"""同一产品入口的真实角色自然搜索验收，不缩短默认流程。"""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'projects/sim2gse'))
from task import run_task
from formal_search import STOP_POLICY


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    destination=args.output or ROOT/'.local/tests'/('sim2gse-search-'+uuid.uuid4().hex[:12])
    source=ROOT/'.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc'
    raw=source.read_bytes()
    started=time.monotonic()
    result=run_task(source,destination)
    assert result['status']=='completed',result
    assert result['candidate']['text'].startswith('!GSE3!')
    assert (destination/'input.original.simc').read_bytes()==raw
    assert result['candidate']['game_validation']=='not_run'
    assert result['candidate']['simulation']=='passed_native_model'
    assert result['search']['candidate_count']>=1
    assert len(result['search']['starts'])>=1
    assert result['stop_policy']==STOP_POLICY
    assert result['final']['status']=='completed'
    assert set(result['final']['scenarios'])=={'nominal'}
    assert result['independent_validation_complete'] is True
    finalists=result['final']['scenarios']['nominal']['finalists']
    assert finalists
    assert all(len(row['batches'])==3 and row['samples']==381 and
               all(batch['requested_iterations']==128 for batch in row['batches'])
               for row in finalists)
    assert result['improvement']=='search_result'
    score=result['search_result']
    assert score['dps']>0 and score['reference_dps']>0
    assert abs(score['reference_ratio']-score['dps']/score['reference_dps'])<1e-9
    assert any(row['key']==result['selected_candidate_key'] and row['score']==score['dps']
               and row['samples']==score['samples'] for row in finalists)
    evidence=dict(status=result['status'],elapsed_seconds=result['elapsed_seconds'],
                  wall_seconds=time.monotonic()-started,candidates=result['search']['candidate_count'],
                  completed_batches=result['completed_batches'],improvement=result['improvement'],
                  independently_tested=result['independent_validation_complete'],
                  search_result=score,scenarios=result['final']['scenarios'],
                  stop_policy=result['stop_policy'],game_validation='not_run')
    (destination/'acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
