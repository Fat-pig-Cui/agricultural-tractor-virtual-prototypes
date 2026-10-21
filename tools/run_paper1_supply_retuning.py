"""Prospective, equal-budget resource retuning; never rewrites prior experiments."""
from pathlib import Path
from itertools import product
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse, hashlib, json, sys, time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'code/lift_control'))
from lift_reserve_supply import LiftV2Config, run_lift_v2
OUT = ROOT/'revisions/machines_major_revision/results/supply_retuning'
CHAINS = ('observer_hybrid', 'smc_accumulator')
SCHEDULE = [[0.,9000.],[60.,14000.],[300.,10000.],[600.,16000.],[900.,11000.],[1200.,15000.]]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x): p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def freeze(p,x):
    x=json.loads(json.dumps(x))
    if p.exists(): assert json.loads(p.read_text())==x, f'Frozen evidence drift: {p}'
    else: dump(p,x)
    return x
def passes(r):
    return bool(r['hold_started'] and r['hold_drop_mm'] is not None
        and r['hold_drop_mm']<=10 and r['post_transition_max_abs_error_mm']<=10
        and r['relief_activation_count']==0 and r['stroke_boundary_samples']==0)
def task(group,chain,candidate,seed):
    return dict(id=f'{group}_{chain}_{candidate["id"]}_{seed}',group=group,chain=chain,
        candidate=candidate,config=dict(duration_s=1800.,seed=seed,leakage_scale=5.,
        tracking_gain_scale=candidate['tracking_gain_scale'],
        accumulator_gain_scale=candidate['accumulator_gain_scale'],
        hold_main_valve_limit=.10,load_schedule=SCHEDULE),
        substeps=10,baseline_dwell_s=8.)
def plan():
    grid=[dict(id=f'g{i:02}',tracking_gain_scale=t,accumulator_gain_scale=a)
          for i,(t,a) in enumerate(product((.7,1.,1.3),(.3,.5,.7)))]
    paths=[Path(__file__),ROOT/'code/lift_control/lift_reserve_supply.py',ROOT/'code/lift_control/hydraulic_v2.py']
    return dict(candidates=grid,chains=CHAINS,development_seeds=list(range(5600,5603)),
        validation_seeds=list(range(5620,5624)),
        development_tasks=[task('development',c,g,s) for c,g,s in product(CHAINS,grid,range(5600,5603))],
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths},
        selection='Per policy: minimize failed development paths, then mean post-transition boundary resource B in joules, then candidate ID. Feasible means zero failures; no global optimum claim.',
        screen='Confirmed hold, drop <=10 mm, post-transition absolute error <=10 mm, no relief activation or stroke-boundary samples; retain every failed path.',
        objective='B = ps * post-transition main-supply volume + post-transition storage boundary work; endpoints 8.01..1800 s, RK4 quadrature. B is not total input energy.',
        fairness='Identical 9 candidates x 3 full 1800 s paths per policy; shared observer, main-valve limit, explicit 8 s latch and discharge gate; all gains selected before new validation.',
        scope='Normal supply only, fixed nominal plant and fivefold leakage with repeated loads; additional resource-oriented development after earlier results, not original preregistration or uncertainty certification.',
        execution='10 ms sensing/control, coupled 1 ms RK4; original model and earlier frozen experiments unchanged.')
def run(t):
    return dict(task=t,row=run_lift_v2(t['chain'],LiftV2Config(**t['config']),
        integration_substeps=t['substeps'],integration_scheme='rk4',baseline_dwell_s=t['baseline_dwell_s']))
def execute(tasks,workers):
    folder=OUT/'checkpoints';folder.mkdir(exist_ok=True);records={};pending=[]
    for t in tasks:
        p=folder/(t['id']+'.json')
        if p.exists():
            rec=json.loads(p.read_text());assert rec['task']==t;records[t['id']]=rec
        else: pending.append(t)
    start=time.monotonic();print('PENDING',len(pending),flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i,f in enumerate(as_completed([pool.submit(run,t) for t in pending]),1):
            rec=f.result();t=rec['task'];r=rec['row'];records[t['id']]=rec
            dump(folder/(t['id']+'.json'),rec)
            print(i,len(pending),t['id'],'pass',passes(r),'B',round(r['post_transition_boundary_resource_j'],2),round(time.monotonic()-start),flush=True)
    return [records[t['id']] for t in tasks]
def select(spec,records):
    ranks={};selected={}
    for chain in spec['chains']:
        rows=[]
        for g in spec['candidates']:
            rr=[r['row'] for r in records if r['task']['chain']==chain and r['task']['candidate']==g]
            assert len(rr)==3
            rows.append(dict(candidate=g,failures=sum(not passes(r) for r in rr),
                mean_B_j=sum(r['post_transition_boundary_resource_j'] for r in rr)/len(rr),
                mean_rmse_mm=sum(r['post_transition_rmse_mm'] for r in rr)/len(rr),
                worst_error_mm=max(r['post_transition_max_abs_error_mm'] for r in rr)))
        rows.sort(key=lambda r:(r['failures'],r['mean_B_j'],r['candidate']['id']))
        ranks[chain]=rows;selected[chain]=rows[0]['candidate']
    return dict(protocol_sha256=sha(OUT/'protocol.json'),rankings=ranks,selected=selected,
        development_checkpoint_sha256={r['task']['id']:sha(OUT/'checkpoints'/(r['task']['id']+'.json')) for r in records})
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=8);ap.add_argument('--plan-only',action='store_true');a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);spec=freeze(OUT/'protocol.json',plan())
    if a.plan_only: print('PROTOCOL FROZEN',len(spec['development_tasks']));return
    development=execute(spec['development_tasks'],a.workers)
    selection=freeze(OUT/'selection.json',select(spec,development))
    validation_tasks=[task('validation',c,selection['selected'][c],s) for c,s in product(spec['chains'],spec['validation_seeds'])]
    freeze(OUT/'validation_protocol.json',dict(selection_sha256=sha(OUT/'selection.json'),tasks=validation_tasks))
    validation=execute(validation_tasks,a.workers)
    all_records=development+validation
    freeze(OUT/'complete.json',dict(protocol_sha256=sha(OUT/'protocol.json'),selection_sha256=sha(OUT/'selection.json'),
        validation_protocol_sha256=sha(OUT/'validation_protocol.json'),
        checkpoint_sha256={r['task']['id']:sha(OUT/'checkpoints'/(r['task']['id']+'.json')) for r in all_records}))
    print('COMPLETE',len(all_records),json.dumps(selection['selected']),flush=True)
if __name__=='__main__': main()
