"""Replay all original joint-noise seeds with added activity/storage logging."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'code'),str(ROOT/'code/lift_control')]
from run_paper1_major_revision import summarize
from lift_v2_experiment import run_lift_v2,LiftV2Config
OUT=ROOT/'revisions/machines_major_revision/results'
def run(task):
    seed,joint=task
    return run_lift_v2('observer_hybrid',LiftV2Config(duration_s=1800,seed=seed,position_noise_scale=2 if joint else 1,pressure_noise_scale=2 if joint else 1),trace_interval_s=.1 if seed==4160 else None)
def main():
    tasks=[(s,True) for s in range(4160,4170)]+[(4160,False)]
    (OUT/'original_noise_protocol.json').write_text(json.dumps(dict(tasks=tasks,representative='first original stress seed 4160; no favorable-path selection'),indent=2))
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(run,tasks))
    frozen=json.loads((ROOT/'results/paper1_two_chamber_v2.json').read_text())['stress']['sensor_noise_2x']['rows']
    for a,b in zip(rows[:10],frozen):assert all(a[k]==v for k,v in b.items()),a['seed']
    (OUT/'original_noise_diagnostics.json').write_text(json.dumps(dict(summary=summarize(rows[:10]),joint_rows=rows[:10],nominal_seed4160=rows[-1],original_fields_exact=True),indent=2))
    print(json.dumps(summarize(rows[:10]),indent=2))
if __name__=='__main__':main()
