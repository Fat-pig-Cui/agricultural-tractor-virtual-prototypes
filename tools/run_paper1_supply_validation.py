"""Freeze a new conditional reserve study before observing its validation paths.

No new gain selection: previous independently selected hybrid/PID/SMC gains are
kept. The new supervisor inherits hybrid gains. The two pilots are development
history and are explicitly excluded from this validation.
"""
from pathlib import Path
from itertools import product
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,hashlib,json,random,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code/lift_control'))
from lift_reserve_supply import LiftV2Config,run_lift_v2
OUT=ROOT/'revisions/machines_major_revision/results/supply_validation'
CHAINS=('observer_hybrid','pid_accumulator','smc_accumulator','reserve_supervisor')
GAINS={'observer_hybrid':(1.,.5),'pid_accumulator':(1.3,.5),
       'smc_accumulator':(1.3,.5),'reserve_supervisor':(1.,.5)}
SCHEDULE=[[0.,9000.],[60.,14000.],[300.,10000.],[600.,16000.],[900.,11000.],[1200.,15000.]]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def freeze(p,x):
    x=json.loads(json.dumps(x))
    if p.exists():assert json.loads(p.read_text())==x, f'Frozen evidence drift: {p}'
    else:dump(p,x)
    return x
def plan():
    n=8;rng=random.Random(540191)
    ranges=dict(leakage_scale=(3.,8.),accumulator_flow_scale=(.8,1.2),
        position_bias_m=(-.001,.001),pressure_bias_pa=(-50000.,50000.),
        pressure_noise_scale=(1.,1.5),temperature_end_c=(40.,55.),
        post_step_load_n=(12000.,16000.))
    plant_ranges=dict(mass_kg=(1000.,1400.),stiffness_n_m=(15000.,21000.),
        viscous_n_s_m=(1800.,2600.),coulomb_n=(680.,1020.),
        stribeck_n=(280.,420.),effective_bulk_modulus_pa=(1.6e8,2.4e8))
    samples={}
    for k,(lo,hi) in {**ranges,**plant_ranges}.items():
        bins=list(range(n));rng.shuffle(bins)
        samples[k]=[lo+(hi-lo)*(b+rng.random())/n for b in bins]
    vectors=[dict(seed=5400+i,config={k:samples[k][i] for k in ranges},
        overrides={k:samples[k][i] for k in plant_ranges}) for i in range(n)]
    tasks=[]
    def add(group,chain,seed,conf=None,overrides=None,substeps=10):
        gt,ga=GAINS[chain]
        c=dict(duration_s=1800.,seed=seed,leakage_scale=5.,
            tracking_gain_scale=gt,accumulator_gain_scale=ga,
            hold_main_valve_limit=.10)
        c.update(conf or {})
        tasks.append(dict(id=f'{group}_{chain}_{seed}_{substeps}',group=group,
            chain=chain,config=c,overrides=overrides or {},substeps=substeps,
            baseline_dwell_s=8.,trace_interval_s=1. if seed in (5400,5500) else None))
    for chain,seed in product(CHAINS,range(5500,5504)):
        add('normal',chain,seed,dict(load_schedule=SCHEDULE))
    for chain,v,enabled in product(CHAINS,vectors,[True,False]):
        add('isolated_on' if enabled else 'isolated_off',chain,v['seed'],
            {**v['config'],'accumulator_enabled':enabled,
             'main_isolation_intervals':[[300.,1500.]]},v['overrides'])
    # The representative refinement vector is fixed by seed, not outcome.
    for chain,enabled in product(CHAINS,[True,False]):
        v=vectors[0]
        add('refined_on' if enabled else 'refined_off',chain,v['seed'],
            {**v['config'],'accumulator_enabled':enabled,
             'main_isolation_intervals':[[300.,1500.]]},v['overrides'],20)
    paths=[Path(__file__),ROOT/'code/lift_control/lift_reserve_supply.py',
           ROOT/'code/lift_control/hydraulic_v2.py']
    return dict(tasks=tasks,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths},
        gains=GAINS,validation_vectors=vectors,sampling_ranges=dict(config=ranges,plant=plant_ranges),
        rng_seed=540191,pilots='5200--5202; exploration only, excluded from validation',
        gain_rule='No reselection. Previous scalar hybrid/PID/corrected SMC gains frozen. Reserve inherits hybrid gains.',
        isolation='Ideal blocking of supply-connected main-valve orifice during [300,1500) s; its return orifice remains available to every policy. Not a physical pump-fault model.',
        information='Shared observer and measurements; current main-availability flag observable to every policy; only reserve uses it to allocate storage. No future duration or true-state feedback.',
        primary='Report every path, 10 mm post-transition absolute-error and confirmed-hold drop constraints; no relief/stroke boundary.',
        resources='For common endpoints t=8.01..1800 s: main supply volume, storage boundary work, and ps*main supply volume+storage boundary work. Not pump input or total energy.',
        contrasts='Paired on/off storage at fixed plant/noise; paired policies; normal tracking/resource trade-off; no universal superiority or physical probability.',
        execution='10 ms controller/noise; 1 ms coupled RK4; predeclared seed 5400 repeated at .5 ms; baseline dwell/discharge gating=8 s for PID AND SMC.')
def run(t):
    return dict(task=t,row=run_lift_v2(t['chain'],LiftV2Config(**t['config']),
        plant_overrides=t['overrides'],integration_substeps=t['substeps'],
        integration_scheme='rk4',baseline_dwell_s=t['baseline_dwell_s'],
        trace_interval_s=t['trace_interval_s']))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=8)
    ap.add_argument('--plan-only',action='store_true');a=ap.parse_args()
    OUT.mkdir(exist_ok=True);spec=freeze(OUT/'protocol.json',plan())
    if a.plan_only:print('PROTOCOL FROZEN',len(spec['tasks']));return
    folder=OUT/'checkpoints';folder.mkdir(exist_ok=True);pending=[];records={}
    for t in spec['tasks']:
        p=folder/(t['id']+'.json')
        if p.exists():
            rec=json.loads(p.read_text());assert rec['task']==t;records[t['id']]=rec
        else:pending.append(t)
    start=time.monotonic();print('PENDING',len(pending),flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for i,f in enumerate(as_completed([pool.submit(run,t) for t in pending]),1):
            rec=f.result();r=rec['row'];t=rec['task'];records[t['id']]=rec
            dump(folder/(t['id']+'.json'),rec)
            print(i,len(pending),t['id'],{k:round(r[k],4) for k in ['hold_drop_mm','post_transition_max_abs_error_mm','post_transition_main_supply_volume_ml','accumulator_oil_used_ml']},round(time.monotonic()-start),flush=True)
    freeze(OUT/'complete.json',dict(protocol_sha256=sha(OUT/'protocol.json'),
        checkpoint_sha256={t['id']:sha(folder/(t['id']+'.json')) for t in spec['tasks']}))
    print('COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
