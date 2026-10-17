"""Frozen-control, paired-seed numerical audits for the Machines major revision."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import sys,json,hashlib,time,statistics,math
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/lift_control')]
from lift_v2_experiment import LiftV2Config,run_lift_v2
from scipy.stats import t
OUT=ROOT/'revisions/machines_major_revision/results'

def stats(v):
    n=len(v);mean=statistics.fmean(v);sd=statistics.stdev(v) if n>1 else 0
    half=float(t.ppf(.975,n-1))*sd/math.sqrt(n) if n>1 else 0
    return dict(n=n,mean=mean,sd=sd,ci95_low=mean-half,ci95_high=mean+half,min=min(v),max=max(v))

def summarize(rows):
    def passed(r):
        return (r['hold_started'] and r['hold_drop_mm'] is not None and r['hold_drop_mm']<=10
            and r['post_transition_max_abs_error_mm']<=10 and not r['relief_activation_count']
            and not r['stroke_boundary_samples'])
    result=dict(n=len(rows),entered=sum(r['hold_started'] for r in rows),passed=sum(passed(r) for r in rows))
    for k in ['hold_drop_mm','post_transition_rmse_mm','post_transition_max_abs_error_mm',
              'mode_switches','accumulator_oil_used_ml','peak_pressure_mpa',
              'accumulator_active_time_s','minimum_accumulator_pressure_mpa','stroke_boundary_samples']:
        values=[r[k] for r in rows if r[k] is not None]
        result[k]=stats(values) if values else None
    return result

def job(args):
    name,controller,seed,conf,kw=args
    r=run_lift_v2(controller,LiftV2Config(seed=seed,duration_s=1800,**conf),**kw)
    return name,r

def protocol():
    tasks=[]
    def add(name,controller='observer_hybrid',seeds=range(4300,4305),conf=None,**kw):
        for seed in seeds:tasks.append((name,controller,seed,conf or {},kw))
    # Each family is fixed before execution; no newly evaluated case selects gains.
    for c in ['observer_hybrid','pid_accumulator']:
        for o in ['shared','fixed_load','raw']:
            add(f'observer_{c}_{o}',c,seeds=range(4300,4310),observer_variant=o)
    for dwell in [0,2,4,8,12,16]:
        add(f'dwell_{dwell}',conf={'mode_dwell_s':dwell})
    add('pid_accumulator_matched_dwell','pid_accumulator',baseline_dwell_s=8)
    for key in ['mass_kg','viscous_n_s_m','stiffness_n_m']:
        for scale in [.7,1.3]:
            nominal={'mass_kg':1200,'viscous_n_s_m':2200,'stiffness_n_m':18000}[key]
            add(f'mechanical_{key}_{scale}',plant_overrides={key:nominal*scale})
    for sub in [1,2,4,10]:
        add(f'integration_{sub}',integration_substeps=sub,trace_interval_s=.01 if sub in [1,10] else None)
    for scale in [1,2,4,10,20]:
        add(f'pressure_noise_{scale}',conf={'pressure_noise_scale':scale},trace_interval_s=.1)
    add('both_noise_2',conf={'position_noise_scale':2,'pressure_noise_scale':2},trace_interval_s=.1)
    # Predeclared representative seed, not a best-case selection.
    add('trajectory_nominal',seeds=[4300],trace_interval_s=.01)
    add('trajectory_pid','pid_accumulator',seeds=[4300],trace_interval_s=.01)
    return tasks

def main():
    OUT.mkdir(parents=True,exist_ok=True);tasks=protocol()
    spec=dict(duration_s=1800,controller_period_s=.01,seeds='4300--4309; first five for sensitivity',
        selection='No retuning; defaults frozen from submitted code',tasks=tasks)
    (OUT/'protocol.json').write_text(json.dumps(spec,indent=2))
    groups={};start=time.time()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(job,a) for a in tasks]
        for i,f in enumerate(as_completed(futures),1):
            name,row=f.result();groups.setdefault(name,[]).append(row)
            if i%5==0:print(i,len(tasks),name,'elapsed',round(time.time()-start),flush=True)
    for name,rows in groups.items():
        rows.sort(key=lambda r:r['seed'])
        (OUT/(name+'.json')).write_text(json.dumps(dict(summary=summarize(rows),rows=rows),indent=2))
    (OUT/'summary.json').write_text(json.dumps({k:summarize(v) for k,v in sorted(groups.items())},indent=2))
    baseline=json.loads((ROOT/'results/paper1_two_chamber_v2.json').read_text())
    parity=[]
    for name in ['observer_hybrid','pid_accumulator','pid_lock','smc_lock']:
        ref=baseline['holdout'][name]['rows'][0]
        row=run_lift_v2(name,LiftV2Config(duration_s=1800,seed=int(ref['seed'])))
        mismatch={k:(v,row[k]) for k,v in ref.items() if row[k]!=v}
        assert not mismatch,(name,mismatch)
        parity.append(dict(controller=name,seed=ref['seed'],all_original_fields_identical=True))
    (OUT/'baseline_parity.json').write_text(json.dumps(parity,indent=2))
    print('COMPLETE',len(tasks),'runs',round(time.time()-start),'s')
if __name__=='__main__':main()
