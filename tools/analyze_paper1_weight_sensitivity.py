"""Development-only objective sensitivity; no test outcome chooses a policy."""
from pathlib import Path
from itertools import product
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'revisions/machines_major_revision'
OLD=REV/'results/risk_closure';EXT=REV/'results/risk_extension'
prior=json.loads((OLD/'selection.json').read_text());smc=json.loads((EXT/'selection.json').read_text())
training={**json.loads((OLD/'training.json').read_text()),**json.loads((EXT/'training.json').read_text())}
candidates={**prior['all_candidates'],'smc_accumulator':smc['all_candidates']}
result={}
for policy,rows in candidates.items():
    def worst(r):
        prefix='active_smc_train_' if policy=='smc_accumulator' else 'train_'+policy+'_'
        return training[prefix+str(r['candidate']['id'])]['summary']['post_transition_max_abs_error_mm']['max']
    feasible=[r for r in rows if not r['failures'] and worst(r)<=8.]
    margin=min(feasible,key=lambda r:(r['J'],r['candidate']['id']))
    profiles=[];frequency={}
    for weights in product([.5,1.,2.],repeat=4):
        def objective(r):
            values=[r['means'][k]/d for k,d in [('hold_drop_mm',10),('post_transition_rmse_mm',10),('accumulator_oil_used_ml',500),('mode_switches',225)]]
            return sum(a*b for a,b in zip(weights,values))
        selected=min(rows,key=lambda r:(r['failures'],objective(r),r['candidate']['id']))
        i=selected['candidate']['id'];frequency[i]=frequency.get(i,0)+1
        profiles.append(dict(weights=weights,selected_id=i))
    result[policy]=dict(profile_count=len(profiles),selected_id_counts=frequency,profiles=profiles,
        same_8mm_development_constraint_choice=margin['candidate'],worst_error_at_that_choice_mm=worst(margin),
        feasible_ids=[r['candidate']['id'] for r in feasible])
obj=dict(results=result,scope='Post hoc development-only sensitivity. Counts describe 81 chosen weight profiles, not probabilities. The 8 mm rule is checked across policies; it does not inspect or change any held-out gain.',
    source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),OLD/'selection.json',OLD/'training.json',EXT/'selection.json',EXT/'training.json']})
p=EXT/'weight_sensitivity.json'
if p.exists():assert json.loads(p.read_text())==json.loads(json.dumps(obj))
else:p.write_text(json.dumps(obj,indent=2)+'\n')
print(json.dumps({k:{a:b for a,b in v.items() if a!='profiles'} for k,v in result.items()},indent=2))
