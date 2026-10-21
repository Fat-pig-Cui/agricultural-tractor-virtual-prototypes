"""Frozen risk-closure protocol with checkpoints and independent tuning/test seeds.

All simulation outputs, including failures, are retained. Historical files are
never rewritten. No task is selected after inspecting validation outcomes.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from itertools import product
from pathlib import Path
import hashlib
import json
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'code'), str(ROOT/'code/lift_control')]
from lift_v2_experiment import LiftV2Config, run_lift_v2
from run_paper1_major_revision import summarize

OUT = ROOT/'revisions/machines_major_revision/results/risk_closure'
SCHEDULE = ((0.,9000.),(60.,14000.),(300.,10000.),(600.,16000.),(900.,11000.),(1200.,15000.))
TRAIN_SCHEDULE = ((0.,9000.),(60.,14000.),(100.,10000.),(160.,16000.),(220.,11000.),(260.,15000.))
CHAINS = ('observer_hybrid','pid_accumulator')
METRICS = ('hold_drop_mm','post_transition_rmse_mm','accumulator_oil_used_ml','mode_switches')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path, obj): path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')

def task(group, seed, chain='observer_hybrid', substeps=10, duration=1800.,
         config=None, overrides=None, matched=False, candidate=None):
    conf = dict(duration_s=duration, seed=seed, load_schedule=SCHEDULE, leakage_scale=5.)
    conf.update(config or {})
    return dict(id=f'{group}_{seed}', group=group, chain=chain, config=conf,
                overrides=overrides or {}, substeps=substeps,
                matched=matched, candidate=candidate)

def plan():
    conv=[]
    arms = {'nominal':dict(leakage_scale=1.), 'leak5':{},
            'disabled':dict(accumulator_enabled=False), 'fric07':{}, 'fric13':{}}
    for arm,conf in arms.items():
        scale={'fric07':.7,'fric13':1.3}.get(arm)
        overrides=({k:v*scale for k,v in [('viscous_n_s_m',2200.),('coulomb_n',850.),('stribeck_n',350.)]} if scale else {})
        for sub,seed in product([10,20],range(4400,4403)):
            conv.append(task(f'convergence_{arm}_{sub}',seed,substeps=sub,config=conf,overrides=overrides))
    train=[]
    candidates=[]
    for i,(track,acc) in enumerate(product([.7,1.,1.3],[.5,1.,1.5])):
        conf=dict(tracking_gain_scale=track,accumulator_gain_scale=acc,
                  hold_main_valve_limit=.10,load_schedule=TRAIN_SCHEDULE)
        candidates.append(dict(id=i,tracking_gain_scale=track,accumulator_gain_scale=acc))
        for chain,seed in product(CHAINS,range(4600,4603)):
            train.append(task(f'train_{chain}_{i}',seed,chain=chain,duration=300.,
                              config=conf,matched=True,candidate=i))
    # Stratified marginal samples with independent deterministic permutations.
    # The sampling distribution is a numerical design, not a physical prior.
    rng=random.Random(48191); n=24
    ranges={'mass_kg':(840.,1560.),'viscous_n_s_m':(1540.,2860.),
            'stiffness_n_m':(12600.,23400.),'coulomb_n':(595.,1105.),
            'stribeck_n':(245.,455.),'stribeck_velocity_m_s':(.0028,.0052),
            'effective_bulk_modulus_pa':(1.4e8,2.6e8),
            'valve_time_constant_s':(.035,.065)}
    extras={'leakage_scale':(1.,10.),'accumulator_flow_scale':(.5,1.5),
            'pressure_noise_scale':(1.,4.),'position_bias_m':(-.002,.002)}
    sampled={}
    for key,(low,high) in {**ranges,**extras}.items():
        bins=list(range(n));rng.shuffle(bins)
        sampled[key]=[low+(high-low)*(j+rng.random())/n for j in bins]
    uncertain=[]
    for i in range(n):
        uncertain.append(task('uncertainty',4800+i,
            config={k:sampled[k][i] for k in extras},
            overrides={k:sampled[k][i] for k in ranges}))
    return dict(
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in
            [Path(__file__),ROOT/'code/lift_control/lift_v2_experiment.py',ROOT/'code/lift_control/hydraulic_v2.py']},
        convergence=conv, training=train, uncertainty=uncertain,candidates=candidates,
        sampling_ranges=dict(plant=ranges,config=extras),
        validation_seeds=list(range(4700,4710)),validation_substeps=[10,20],
        validation_duration_s=1800., validation_schedule=SCHEDULE,
        selection_rule='minimize failing development paths, then mean J, then candidate id',
        objective='J=drop_mm/10 + rmse_mm/10 + oil_ml/500 + switches/225',
        fairness='9 candidates x 3 development seeds x 300 s per chain; 1 ms RK4; common 8 s latch/discharge gating and +/-0.10 main-valve limit; identical noise/reference/load and scalar weights',
        scope='A finite numerical comparison. No global optimum, physical probability, hardware accuracy or global nonlinear stability claim.')

def run(t):
    r=run_lift_v2(t['chain'],LiftV2Config(**t['config']),
        plant_overrides=t['overrides'],integration_substeps=t['substeps'],
        integration_scheme='rk4',baseline_dwell_s=8. if t['matched'] and t['chain']=='pid_accumulator' else 0.,
        trace_interval_s=.5 if t['config']['seed'] in (4400,4700) and 'train_' not in t['group'] else None)
    return dict(task=t,row=r)

def execute(tasks,workers):
    directory=OUT/'checkpoints';directory.mkdir(exist_ok=True)
    rows={};pending=[]
    for t in tasks:
        p=directory/(t['id']+'.json')
        if p.exists():
            saved=json.loads(p.read_text());assert saved['task']==t
            rows[t['id']]=saved
        else:pending.append(t)
    started=time.monotonic()
    print(f'pending={len(pending)} existing={len(rows)}',flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(run,t) for t in pending]
        for i,f in enumerate(as_completed(futures),1):
            saved=f.result();t=saved['task'];r=saved['row'];rows[t['id']]=saved
            dump(directory/(t['id']+'.json'),saved)
            print(f'{i}/{len(pending)} {t["id"]} drop={r["hold_drop_mm"]} error={r["post_transition_max_abs_error_mm"]:.4f} elapsed={time.monotonic()-started:.0f}s',flush=True)
    return [rows[t['id']] for t in tasks]

def groups(records):
    result={}
    for saved in records:result.setdefault(saved['task']['group'],[]).append(saved['row'])
    return {k:dict(summary=summarize(v),rows=v) for k,v in result.items()}

def objective(r):
    return (float('inf') if r['hold_drop_mm'] is None else
            r['hold_drop_mm']/10+r['post_transition_rmse_mm']/10+
            r['accumulator_oil_used_ml']/500+r['mode_switches']/225)

def select(training,spec):
    selected={};all_scores={}
    for chain in CHAINS:
        scores=[]
        for c in spec['candidates']:
            rows=training[f'train_{chain}_{c["id"]}']['rows'];s=summarize(rows)
            scores.append(dict(candidate=c,failures=len(rows)-s['passed'],
                               J=statistics.fmean(objective(r) for r in rows),
                               means={k:statistics.fmean(r[k] for r in rows if r[k] is not None) for k in METRICS}))
        feasible=[s for s in scores if not s['failures']]
        for s in scores:
            s['pareto']=s in feasible and not any(
                all(o['means'][k]<=s['means'][k] for k in METRICS) and
                any(o['means'][k]<s['means'][k] for k in METRICS)
                for o in feasible)
        selected[chain]=min(scores,key=lambda s:(s['failures'],s['J'],s['candidate']['id']))
        all_scores[chain]=scores
    selection=dict(selected=selected,all_candidates=all_scores,
                   training_protocol_sha256=sha(OUT/'protocol.json'))
    path=OUT/'selection.json'
    if path.exists():assert json.loads(path.read_text())==selection,'Frozen selection drift'
    else:dump(path,selection)
    return selection

def final_tasks(selection,spec):
    tasks=[]
    for chain in CHAINS:
        c=selection['selected'][chain]['candidate']
        config={k:c[k] for k in ['tracking_gain_scale','accumulator_gain_scale']}
        config['hold_main_valve_limit']=.10
        for sub,seed in product(spec['validation_substeps'],spec['validation_seeds']):
            tasks.append(task(f'validation_{chain}_{sub}',seed,chain,substeps=sub,config=config,matched=True))
        if chain=='observer_hybrid':
            for seed in spec['validation_seeds']:
                tasks.append(task('selected_hybrid_disabled',seed,chain,config={**config,'accumulator_enabled':False},matched=True))
    return tasks

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['all','convergence','fair','uncertainty'],default='all');parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    # Materialize tuples as JSON arrays before comparing immutable ledgers.
    spec=json.loads(json.dumps(plan()))
    path=OUT/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==spec,'Protocol/source drift; preserve completed evidence'
    else:dump(path,spec)
    if args.stage in ('all','convergence'):
        dump(OUT/'convergence.json',groups(execute(spec['convergence'],args.workers)))
    if args.stage in ('all','fair'):
        train=groups(execute(spec['training'],args.workers));dump(OUT/'training.json',train)
        selection=select(train,spec)
        dump(OUT/'validation.json',groups(execute(final_tasks(selection,spec),args.workers)))
    if args.stage in ('all','uncertainty'):
        dump(OUT/'uncertainty.json',groups(execute(spec['uncertainty'],args.workers)))
    print('COMPLETE',args.stage,flush=True)

if __name__=='__main__':main()
