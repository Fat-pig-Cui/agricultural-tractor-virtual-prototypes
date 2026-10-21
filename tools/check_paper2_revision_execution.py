"""Audit applied trajectories and unchanged default control after instrumentation."""
from dataclasses import replace
import json
from run_paper2_major_revision import (OUT,FROZEN,PARAMS,TEST,profile,ControllerFeatures)
from viability_ecms_v2 import run_cycle

def main():
    counts=dict(trajectories=0,samples=0,start_transitions=0,stop_transitions=0)
    for arm,mode,settings in [('adaptive','viability_ecms',FROZEN),
        ('fixed_shared','viability_ecms',replace(FROZEN,proportional_gain=0)),
        ('baseline','load_following',FROZEN)]:
        for seed in TEST:
            row=run_cycle(profile(seed),mode,settings,PARAMS,capture_full_trajectory=True)
            prior=0.;on_time=0.;off_time=1e9
            for x in row['trajectory_full']:
                power=x['engine_power_w'];is_on=power>1;was_on=prior>1
                if is_on and was_on:assert abs(power-prior)<=40000+1e-9
                if is_on and not was_on:
                    assert power==60000 and off_time>=1
                    counts['start_transitions']+=1
                if not is_on and was_on:
                    assert on_time>=5
                    counts['stop_transitions']+=1
                if is_on:assert 60000<=power<=300000
                assert abs(x['battery_bus_w'])<=180000+1e-9
                assert .2-1e-12<=x['soc']<=.8+1e-12
                if is_on:on_time=(on_time if was_on else 0)+1;off_time=0
                else:off_time=(off_time if not was_on else 0)+1;on_time=0
                prior=power;counts['samples']+=1
            assert row['strict_valid']
            counts['trajectories']+=1
    implicit=run_cycle(profile(3120),'viability_ecms',FROZEN,PARAMS)
    explicit=run_cycle(profile(3120),'viability_ecms',FROZEN,PARAMS,features=ControllerFeatures())
    for key in implicit:
        if key!='decision_timing_ms':assert implicit[key]==explicit[key],key
    reference_path=OUT/'results/submitted_reference.json'
    archive_parity=None
    if reference_path.exists():
        original=json.loads(reference_path.read_text())
        reference=next(r for r in original['holdout']['viability_ecms_strict_1e-4']['rows'] if r['seed']==3120)
        assert implicit['fuel_l']==reference['fuel_l']
        archive_parity=True
    result=dict(counts=counts,violations=0,default_feature_parity=True,
        submitted_seed3120_exact_fuel_parity=archive_parity,terminal_tolerance=1e-4,
        limitation='Execution checks do not validate hardware or prove recursive feasibility.')
    (OUT/'results/execution_constraint_checks.json').write_text(json.dumps(result,indent=2))
    print(result)

if __name__=='__main__':main()
