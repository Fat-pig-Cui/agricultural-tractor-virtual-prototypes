"""Second development diagnostic; never an independent validation set."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code/lift_control'))
from lift_reserve_coordination import LiftV2Config,run_lift_v2
OUT=ROOT/'revisions/machines_major_revision/results/reserve_long_pilot'
CHAINS=('observer_hybrid','pid_accumulator','smc_accumulator','reserve_supervisor')
def run(t):
    return dict(task=t,row=run_lift_v2(t['chain'],LiftV2Config(**t['config']),
        integration_substeps=10,integration_scheme='rk4',baseline_dwell_s=8.,
        trace_interval_s=1.))
def main():
    OUT.mkdir(exist_ok=True); tasks=[]
    for chain in CHAINS:
        for enabled in (True,False):
            conf=dict(duration_s=1800.,seed=5201,leakage_scale=5.,
                tracking_gain_scale=1.3,accumulator_gain_scale=.5,
                hold_main_valve_limit=.10,accumulator_enabled=enabled,
                main_isolation_intervals=[[600.,1200.]])
            tasks.append(dict(id=chain+('_enabled' if enabled else '_disabled'),chain=chain,config=conf))
    paths=[Path(__file__),ROOT/'code/lift_control/lift_reserve_coordination.py',ROOT/'code/lift_control/hydraulic_v2.py']
    spec=dict(tasks=tasks,role='exploration only',source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    p=OUT/'protocol.json'
    if p.exists():assert json.loads(p.read_text())==spec
    else:p.write_text(json.dumps(spec,indent=2)+'\n')
    pending=[t for t in tasks if not (OUT/(t['id']+'.json')).exists()]
    start=time.monotonic()
    with ProcessPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(run,t) for t in pending]):
            rec=f.result(); r=rec['row'];(OUT/(rec['task']['id']+'.json')).write_text(json.dumps(rec,indent=2)+'\n')
            print(rec['task']['id'],{k:round(r[k],4) for k in ['hold_drop_mm','post_transition_max_abs_error_mm','main_supply_hold_volume_ml','accumulator_oil_used_ml','storage_boundary_work_j']},round(time.monotonic()-start),flush=True)
if __name__=='__main__':main()
