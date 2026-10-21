"""Exploration only: do not use these paths as independent verification."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code/lift_control'))
from lift_reserve_experiment import LiftV2Config,run_lift_v2
OUT=ROOT/'revisions/machines_major_revision/results/reserve_pilot'
CHAINS=('observer_hybrid','pid_accumulator','smc_accumulator','reserve_supervisor')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(t):
    return dict(task=t,row=run_lift_v2(t['chain'],LiftV2Config(**t['config']),
        integration_substeps=10,integration_scheme='rk4',baseline_dwell_s=8.,
        trace_interval_s=.5))
def main():
    OUT.mkdir(exist_ok=True)
    tasks=[]
    for chain in CHAINS:
        for arm in ['normal','isolated','isolated_disabled']:
            conf=dict(duration_s=300.,seed=5200,leakage_scale=5.,
                tracking_gain_scale=1.3,accumulator_gain_scale=.5,
                hold_main_valve_limit=.10,accumulator_enabled=arm!='isolated_disabled',
                main_isolation_intervals=[] if arm=='normal' else [[100.,240.]])
            tasks.append(dict(id=chain+'_'+arm,chain=chain,arm=arm,config=conf))
    spec=dict(tasks=tasks,role='exploration; not verification or independent tuning evidence',
              source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'code/lift_control/lift_reserve_experiment.py',ROOT/'code/lift_control/hydraulic_v2.py']})
    target=OUT/'protocol.json'
    if target.exists():assert json.loads(target.read_text())==spec
    else:target.write_text(json.dumps(spec,indent=2)+'\n')
    pending=[t for t in tasks if not (OUT/(t['id']+'.json')).exists()]
    start=time.monotonic()
    with ProcessPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(run,t) for t in pending]):
            rec=future.result();row=rec['row'];(OUT/(rec['task']['id']+'.json')).write_text(json.dumps(rec,indent=2)+'\n')
            print(rec['task']['id'],json.dumps({k:row[k] for k in ['hold_drop_mm','post_transition_max_abs_error_mm','isolated_max_abs_error_mm','main_supply_hold_volume_ml','accumulator_oil_used_ml','storage_boundary_work_j']}),f'{time.monotonic()-start:.0f}s',flush=True)
if __name__=='__main__':main()
