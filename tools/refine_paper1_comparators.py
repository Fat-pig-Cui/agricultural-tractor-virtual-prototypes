"""Additional 1 ms comparator replay; frozen gains and common revision seeds."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'code'),str(ROOT/'code/lift_control')]
from run_paper1_major_revision import summarize
from lift_v2_experiment import run_lift_v2,LiftV2Config
OUT=ROOT/'revisions/machines_major_revision/results'
def run(task):
    c,s=task
    return c,run_lift_v2(c,LiftV2Config(duration_s=1800,seed=s),integration_substeps=10)
def main():
    tasks=[(c,s) for c in ['pid_lock','smc_lock','pid_accumulator'] for s in range(4300,4305)]
    (OUT/'refined_comparators_protocol.json').write_text(json.dumps(dict(tasks=tasks,plant_step_s=.001,control_period_s=.01,selection='frozen; no retuning'),indent=2))
    groups={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for c,r in pool.map(run,tasks):groups.setdefault(c,[]).append(r)
    results={c:dict(summary=summarize(rr),rows=rr) for c,rr in groups.items()}
    (OUT/'refined_comparators.json').write_text(json.dumps(results,indent=2))
    print(json.dumps({c:v['summary'] for c,v in results.items()},indent=2))
if __name__=='__main__':main()
