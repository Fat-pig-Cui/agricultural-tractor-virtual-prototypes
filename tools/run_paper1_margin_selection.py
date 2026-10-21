"""Accuracy-margin design chosen only from the existing development grid.

The 8 mm development screen reserves a heuristic 2 mm margin for the declared
position-bias interval. It is not a bound on observer/noise error. Fresh stress
vectors and additional nominal seeds are fixed before execution.
"""
import argparse,hashlib,json,sys
from pathlib import Path
from itertools import product
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import run_paper1_risk_closure as old
OUT=ROOT/'revisions/machines_major_revision/results/margin_selection'
EXT=ROOT/'revisions/machines_major_revision/results/risk_extension'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen(p,x):
    x=json.loads(json.dumps(x))
    if p.exists():assert json.loads(p.read_text())==x,str(p)
    else:p.write_text(json.dumps(x,indent=2)+'\n')
    return x
def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    parent=old.OUT
    training=json.loads((parent/'training.json').read_text())
    sel=json.loads((parent/'selection.json').read_text())
    candidates=[]
    for row in sel['all_candidates']['observer_hybrid']:
        c=row['candidate'];g=training[f'train_observer_hybrid_{c["id"]}']['summary']
        candidates.append(dict(candidate=c,failures=row['failures'],J=row['J'],development_worst_error_mm=g['post_transition_max_abs_error_mm']['max']))
    feasible=[c for c in candidates if c['failures']==0 and c['development_worst_error_mm']<=8.]
    assert feasible,'No candidate satisfies declared margin; do not silently relax it'
    chosen=min(feasible,key=lambda c:(c['J'],c['candidate']['id']))
    c=chosen['candidate'];config={k:c[k] for k in ['tracking_gain_scale','accumulator_gain_scale']};config['hold_main_valve_limit']=.10
    extension=json.loads((EXT/'protocol.json').read_text());tasks=[]
    for sub,seed in product([10,20],range(5000,5010)):
        tasks.append(old.task(f'margin_nominal_{sub}',seed,substeps=sub,config=config,matched=True))
    for v in extension['fresh_vectors']:
        tasks.append(old.task('margin_fresh',v['seed'],config={**v['config'],**config},overrides=v['overrides'],matched=True))
    spec=dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'code/lift_control/lift_v2_experiment.py',ROOT/'code/lift_control/hydraulic_v2.py']},
        original_training_sha256=sha(parent/'training.json'),original_selection_sha256=sha(parent/'selection.json'),
        extension_protocol_sha256=sha(EXT/'protocol.json'),candidates=candidates,selected=chosen,tasks=tasks,
        rule='Among existing hybrid development candidates with no failures and worst development error <=8 mm, minimize the same J then candidate id.',
        interpretation='A disclosed follow-up design motivated by previous failures. Two millimeters is a heuristic reserve for the declared bias range, not a proof. No fresh outcome selects or changes gains. The alternative trades tracking margin against original scalar preference and is not an independently retuned comparator.')
    spec=frozen(OUT/'protocol.json',spec);old.OUT=OUT
    records=old.execute(spec['tasks'],a.workers)
    (OUT/'results.json').write_text(json.dumps(old.groups(records),indent=2)+'\n')
    print('COMPLETE margin selection',flush=True)
if __name__=='__main__':main()
