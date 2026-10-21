"""Add the same nominal seed pairs without changing the margin policy."""
from pathlib import Path
from itertools import product
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import run_paper1_risk_closure as old
OUT=ROOT/'revisions/machines_major_revision/results/margin_selection'
def main():
    frozen=json.loads((OUT/'protocol.json').read_text());c=frozen['selected']['candidate']
    config={k:c[k] for k in ['tracking_gain_scale','accumulator_gain_scale']};config['hold_main_valve_limit']=.10
    tasks=[old.task(f'margin_paired_{sub}',seed,substeps=sub,config=config,matched=True) for sub,seed in product([10,20],range(4700,4710))]
    spec=json.loads(json.dumps(dict(tasks=tasks,margin_protocol_sha256=hashlib.sha256((OUT/'protocol.json').read_bytes()).hexdigest(),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'code/lift_control/lift_v2_experiment.py',ROOT/'code/lift_control/hydraulic_v2.py']},
        scope='Same preselected margin policy; common nominal seeds permit paired controller differences. These reused nominal seeds are a follow-up comparison, not an additional independent test.')))
    path=OUT/'paired_protocol.json'
    if path.exists():assert json.loads(path.read_text())==spec
    else:path.write_text(json.dumps(spec,indent=2)+'\n')
    old.OUT=OUT
    rows=old.execute(spec['tasks'],2)
    (OUT/'paired.json').write_text(json.dumps(old.groups(rows),indent=2)+'\n')
    print('COMPLETE nominal pairs',flush=True)
if __name__=='__main__':main()
