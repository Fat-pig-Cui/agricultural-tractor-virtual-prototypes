"""Check that adding the active SMC name preserves all four old chains."""
from pathlib import Path
import importlib.util,json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code/lift_control'))
import lift_v2_experiment as current
recorded=json.loads((ROOT/'revisions/machines_major_revision/results/risk_closure/protocol.json').read_text())['source_sha256']['code/lift_control/lift_v2_experiment.py']
options=[ROOT/'revisions/machines_major_revision/evidence/risk_extension_baseline/lift_v2_experiment.py',ROOT/'historical_sources/pre_risk_extension/lift_v2_experiment.py']
path=next(p for p in options if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==recorded)
spec=importlib.util.spec_from_file_location('frozen_before_active_smc',path)
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
out=[]
for chain in ['pid_lock','pid_accumulator','smc_lock','observer_hybrid']:
    a=previous.run_lift_v2(chain,previous.LiftV2Config(duration_s=1800,seed=4120))
    b=current.run_lift_v2(chain,current.LiftV2Config(duration_s=1800,seed=4120))
    diff={k:[a[k],b[k]] for k in a if a[k]!=b[k]}
    out.append(dict(chain=chain,duration_s=1800,seed=4120,all_outputs_exact=not diff,differences=diff))
    print(chain,not diff,flush=True)
assert all(x['all_outputs_exact'] for x in out)
dest=ROOT/'revisions/machines_major_revision/results/risk_extension/default_parity.json'
dest.write_text(json.dumps(dict(previous_source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    current_source_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),rows=out),indent=2)+'\n')
