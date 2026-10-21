"""Prospectively frozen bridge and active sliding-mode comparison.

The old 24 uncertainty vectors are a disclosed follow-up, not an unseen test.
A separate fresh stratified design is fixed before its outcomes are inspected.
No old result or selection is overwritten.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, random, sys
from itertools import product
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_paper1_risk_closure as old
OUT=ROOT/'revisions/machines_major_revision/results/risk_extension'
POLICIES=('observer_hybrid','pid_accumulator','smc_accumulator')

def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen(p,x):
    x=json.loads(json.dumps(x))
    if p.exists():assert json.loads(p.read_text())==x, f'Frozen evidence drift: {p}'
    else:dump(p,x)
    return x
def candidates():
    return [dict(id=i,tracking_gain_scale=t,accumulator_gain_scale=a)
        for i,(t,a) in enumerate(product([.7,1.,1.3],[.5,1.,1.5]))]
def plan():
    prior=json.loads((old.OUT/'protocol.json').read_text())
    selection=json.loads((old.OUT/'selection.json').read_text())
    bridge=[]
    for chain in POLICIES[:2]:
        c=selection['selected'][chain]['candidate']
        for saved in prior['uncertainty']:
            t=copy.deepcopy(saved);t.update(id=f'bridge_{chain}_{t["config"]["seed"]}',group=f'bridge_{chain}',chain=chain,matched=True)
            t['config'].update({k:c[k] for k in ['tracking_gain_scale','accumulator_gain_scale']},hold_main_valve_limit=.10)
            bridge.append(t)
    training=[]
    for c,seed in product(candidates(),range(4600,4603)):
        training.append(old.task(f'active_smc_train_{c["id"]}',seed,'smc_accumulator',duration=300.,
            config={**{k:c[k] for k in ['tracking_gain_scale','accumulator_gain_scale']},
                'hold_main_valve_limit':.10,'load_schedule':old.TRAIN_SCHEDULE},matched=True,candidate=c['id']))
    rng=random.Random(49191);n=24;sampled={}
    for key,(low,high) in {**prior['sampling_ranges']['plant'],**prior['sampling_ranges']['config']}.items():
        bins=list(range(n));rng.shuffle(bins)
        sampled[key]=[low+(high-low)*(j+rng.random())/n for j in bins]
    fresh=[dict(seed=4900+i,config={k:sampled[k][i] for k in prior['sampling_ranges']['config']},
        overrides={k:sampled[k][i] for k in prior['sampling_ranges']['plant']}) for i in range(n)]
    return dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'code/lift_control/lift_v2_experiment.py',ROOT/'code/lift_control/hydraulic_v2.py',ROOT/'tools/run_paper1_risk_closure.py']},
        parent_protocol_sha256=sha(old.OUT/'protocol.json'),parent_selection_sha256=sha(old.OUT/'selection.json'),
        bridge=bridge,training=training,candidates=candidates(),fresh_vectors=fresh,
        sampling_ranges=prior['sampling_ranges'],fresh_rng_seed=49191,
        policies=POLICIES,objective=prior['objective'],selection_rule=prior['selection_rule'],
        smc='s=18e+ev; robust force=1200*tanh(s/.006) N; original shared observer; PID-type active hold with 8 s dwell and mode-gated discharge; +/-0.10 main valve; no PID integral',
        scope='A boundary-layer sliding-mode implementation, not a reproduction of an adaptive-robust or backstepping paper. Common interfaces do not establish universal superiority.',
        final_plan='Selected SMC: ten common seeds 4700--4709 at 1/.5 ms, old 24 uncertainty vectors at 1 ms. All three selected policies: fresh seeds 4900--4923 at 1 ms. Selection precedes final execution. No gain changes from final outcomes.')
def selected(training,spec):
    rows=[]
    for c in spec['candidates']:
        data=training[f'active_smc_train_{c["id"]}']['rows'];s=old.summarize(data)
        rows.append(dict(candidate=c,failures=len(data)-s['passed'],J=sum(old.objective(r) for r in data)/len(data),
            means={k:sum(r[k] for r in data)/len(data) for k in old.METRICS}))
    return frozen(OUT/'selection.json',dict(selected=min(rows,key=lambda s:(s['failures'],s['J'],s['candidate']['id'])),all_candidates=rows,
        extension_protocol_sha256=sha(OUT/'protocol.json')))
def final_tasks(spec,selection):
    parent=json.loads((old.OUT/'selection.json').read_text())
    choices={k:v['candidate'] for k,v in parent['selected'].items()}
    choices['smc_accumulator']=selection['selected']['candidate'];tasks=[]
    def conf(chain):return {**{k:choices[chain][k] for k in ['tracking_gain_scale','accumulator_gain_scale']},'hold_main_valve_limit':.10}
    for sub,seed in product([10,20],range(4700,4710)):
        tasks.append(old.task(f'active_smc_validation_{sub}',seed,'smc_accumulator',substeps=sub,config=conf('smc_accumulator'),matched=True))
    prior=json.loads((old.OUT/'protocol.json').read_text())
    for t in prior['uncertainty']:
        seed=t['config']['seed']
        tasks.append(old.task('bridge_smc_accumulator',seed,'smc_accumulator',config={**t['config'],**conf('smc_accumulator')},overrides=t['overrides'],matched=True))
    for chain,v in product(POLICIES,spec['fresh_vectors']):
        tasks.append(old.task(f'fresh_{chain}',v['seed'],chain,config={**v['config'],**conf(chain)},overrides=v['overrides'],matched=True))
    return tasks
def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['initial','final','all'],default='all');p.add_argument('--workers',type=int,default=6);args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);spec=frozen(OUT/'protocol.json',plan())
    # Reuse the checkpoint executor, with a distinct output directory.
    old.OUT=OUT
    if args.stage in ['initial','all']:
        records=old.execute(spec['bridge']+spec['training'],args.workers)
        bridge=old.groups([r for r in records if r['task']['group'].startswith('bridge_')])
        training=old.groups([r for r in records if r['task']['group'].startswith('active_smc_train_')])
        dump(OUT/'bridge.json',bridge);dump(OUT/'training.json',training);selected(training,spec)
    if args.stage in ['final','all']:
        selection=json.loads((OUT/'selection.json').read_text())
        # Restore parent path only while resolving immutable parent evidence.
        old.OUT=ROOT/'revisions/machines_major_revision/results/risk_closure'
        tasks=final_tasks(spec,selection);old.OUT=OUT
        frozen(OUT/'final_tasks.json',tasks)
        dump(OUT/'final.json',old.groups(old.execute(tasks,args.workers)))
    print('COMPLETE',args.stage,flush=True)
if __name__=='__main__':main()
