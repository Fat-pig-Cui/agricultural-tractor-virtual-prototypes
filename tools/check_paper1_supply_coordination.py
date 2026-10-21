"""Independent checks and a recoverable snapshot for the reserve extension."""
from pathlib import Path
from unittest.mock import patch
import argparse,hashlib,json,math,shutil,sys
from concurrent.futures import ProcessPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'revisions/machines_major_revision'
OUT=REV/'results/supply_validation'
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'code/lift_control')]
import lift_v2_experiment as original
import lift_reserve_supply as current
import run_paper1_supply_validation as runner
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def snapshot():
    target=REV/'evidence/supply_coordination_baseline';target.mkdir(exist_ok=True)
    files=[*REV.glob('*.tex'),*REV.glob('*.pdf'),REV/'responses.json',REV/'artifact.md',
        REV/'本轮实验进度.md',REV/'Reviewer3_评价更正与正文合规复核.md',ROOT/'README.md']
    files+=list((REV/'responses_current').glob('*'))
    files += [ROOT/'tools'/n for n in ['build_paper1_risk_closure_responses.py',
        'make_paper1_reviewer3_marked.py','package_paper1_reviewer3_revision.py']]
    ledger={}
    for p in files:
        if not p.is_file():continue
        rel=p.relative_to(ROOT);dest=target/rel
        if dest.exists():assert sha(dest)==sha(p),f'Snapshot exists and current changed: {p}'
        else:dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        ledger[str(rel)]=sha(dest)
    dump(target/'MANIFEST.json',ledger);print('SNAPSHOT',len(ledger))
def preflight():
    checks={};parity=[]
    for chain in runner.CHAINS[:3]:
        gt,ga=runner.GAINS[chain]
        conf=dict(duration_s=30.,seed=5399,leakage_scale=5.,tracking_gain_scale=gt,
            accumulator_gain_scale=ga,hold_main_valve_limit=.10)
        kw=dict(integration_substeps=10,integration_scheme='rk4',baseline_dwell_s=8.)
        a=original.run_lift_v2(chain,original.LiftV2Config(**conf),**kw)
        b=current.run_lift_v2(chain,current.LiftV2Config(**conf),**kw)
        parity.append(dict(chain=chain,all_old_fields_identical=all(a[k]==b[k] for k in a)))
    checks['metering_preserves_all_original_30s_fields']=all(r['all_old_fields_identical'] for r in parity)
    p=current.MeteredIsolationPlant();s=p.initial_state()
    for spool in [.1,-.1]:
        p.main_available=True;normal=p.valve_flows(spool,s.p_a_pa,s.p_b_pa)
        p.main_available=False;blocked=p.valve_flows(spool,s.p_a_pa,s.p_b_pa)
        checks[f'supply_only_orifice_isolation_{spool}']=blocked==((0.,normal[1]) if spool>=0 else (normal[0],0.)) and any(blocked)
    spec=json.loads((OUT/'protocol.json').read_text())
    checks['protocol_regenerates']=json.loads(json.dumps(runner.plan()))==spec
    observed=[]
    def spy(chain,config,**kwargs):observed.append((chain,config,kwargs));return {}
    with patch.object(runner,'run_lift_v2',spy):
        for chain in runner.CHAINS:runner.run(next(t for t in spec['tasks'] if t['chain']==chain))
    checks['both_baselines_receive_8s_gate']=len(observed)==4 and all(kw['baseline_dwell_s']==8. for _,_,kw in observed)
    result=dict(checks=checks,parity=parity);dump(OUT/'preflight.json',result)
    print(json.dumps(result,indent=2));assert all(checks.values())
def full_parity_job(chain):
    p=OUT/'checkpoints'/f'normal_{chain}_5500_10.json';record=json.loads(p.read_text());t=record['task']
    old=original.run_lift_v2(chain,original.LiftV2Config(**t['config']),
        plant_overrides=t['overrides'],integration_substeps=t['substeps'],integration_scheme='rk4',
        baseline_dwell_s=t['baseline_dwell_s'],trace_interval_s=t['trace_interval_s'])
    new=record['row'];differences={k:[v,new[k]] for k,v in old.items() if k!='trace' and v!=new[k]}
    trace_equal=len(old['trace'])==len(new['trace']) and all(all(v==b[k] for k,v in a.items()) for a,b in zip(old['trace'],new['trace']))
    return dict(chain=chain,checkpoint_sha256=sha(p),differences=differences,all_old_trace_fields_identical=trace_equal,original_row=old)
def full_parity():
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(full_parity_job,['observer_hybrid','smc_accumulator']))
    result=dict(original_source_sha256=sha(ROOT/'code/lift_control/lift_v2_experiment.py'),rows=rows)
    dump(OUT/'full_parity.json',result)
    print({r['chain']:not r['differences'] and r['all_old_trace_fields_identical'] for r in rows})
    assert all(not r['differences'] and r['all_old_trace_fields_identical'] for r in rows)
def results():
    from report_paper1_supply_coordination import summarize_new,KEYS,CHAINS,passed,pair
    spec=json.loads((OUT/'protocol.json').read_text());a=json.loads((OUT/'analysis.json').read_text())
    records=[json.loads(p.read_text()) for p in (OUT/'checkpoints').glob('*.json')]
    byid={r['task']['id']:r for r in records};checks={}
    checks['88_unique_complete_paths']=len(records)==len(byid)==len(spec['tasks'])==88
    checks['every_frozen_task_preserved']=all(byid[t['id']]['task']==t for t in spec['tasks'])
    checks['current_sources_equal_frozen_sources']=all(sha(ROOT/n)==h for n,h in spec['source_sha256'].items())
    checks['protocol_regenerates']=json.loads(json.dumps(runner.plan()))==spec
    checks['all_1800s_common_control_and_authority']=all(t['config']['duration_s']==1800 and t['config']['hold_main_valve_limit']==.1 and t['baseline_dwell_s']==8. and t['substeps'] in [10,20] for t in spec['tasks'])
    checks['all_gains_preserve_previous_choices']=all([t['config'][k] for k in ['tracking_gain_scale','accumulator_gain_scale']]==spec['gains'][t['chain']] for t in spec['tasks'])
    checks['exactly13_stratified_marginals']=sum(len(v) for v in spec['sampling_ranges'].values())==13 and all(
        sorted(min(7,int((v['overrides' if g=='plant' else 'config'][k]-lo)/(hi-lo)*8)) for v in spec['validation_vectors'])==list(range(8))
        for g,fields in spec['sampling_ranges'].items() for k,(lo,hi) in fields.items())
    checks['new_validation_noise_seeds_disjoint_from_exploration']=not({t['config']['seed'] for t in spec['tasks']} & {5200,5201,5202,5399})
    checks['all_four_policies_share_joint_vectors']=all(
        r['task']['overrides']==v['overrides'] and all(r['task']['config'][k]==x for k,x in v['config'].items())
        for v in spec['validation_vectors'] for r in records if r['task']['group'].startswith('isolated_') and r['task']['config']['seed']==v['seed'])
    checks['main_supply_exactly_zero_during_disconnection']=all(r['row']['main_supply_isolated_volume_ml']==0 for r in records)
    checks['positive_resources_and_boundary_index_identity']=all(
        r['row']['post_transition_main_supply_volume_ml']>=0 and r['row']['post_transition_storage_boundary_work_j']>=0 and
        math.isclose(r['row']['post_transition_boundary_resource_j'],21*r['row']['post_transition_main_supply_volume_ml']+r['row']['post_transition_storage_boundary_work_j'],rel_tol=1e-12,abs_tol=1e-8) for r in records)
    conservation=[];n=1.2;v0=.004*(8./14.)**(1/n);kg=14e6*v0**n
    for rec in records:
        r=rec['row'];dv=r['accumulator_oil_used_ml']*1e-6
        exact=kg/(1-n)*((v0+dv)**(1-n)-v0**(1-n))
        conservation.append(dict(id=rec['task']['id'],volume_residual_ml=r['storage_quadrature_volume_ml']-r['accumulator_oil_used_ml'],gas_work_residual_j=r['storage_boundary_work_j']-exact))
    checks['storage_volume_matches_state_change']=max(abs(r['volume_residual_ml']) for r in conservation)<2e-6
    checks['storage_work_matches_analytic_polytropic_integral']=max(abs(r['gas_work_residual_j']) for r in conservation)<1e-4
    checks['disabled_storage_all_zero']=all(all(abs(rec['row'][k])<1e-10 for k in ['accumulator_oil_used_ml','storage_quadrature_volume_ml','storage_boundary_work_j']) for rec in records if rec['task']['config'].get('accumulator_enabled') is False)
    checks['normal_hybrid_and_availability_outputs_identical']=all(
        all(byid[f'normal_observer_hybrid_{seed}_10']['row'][k]==value for k,value in byid[f'normal_reserve_supervisor_{seed}_10']['row'].items() if k!='controller') for seed in range(5500,5504))
    checks['all_disconnection_paths_120000_control_samples']=all(r['row']['isolated_samples']==(120000 if r['task']['group']!='normal' else 0) for r in records)
    checks['all_windows_reconstruct']=all(abs(r['row']['hold_drop_mm']-1000*max(0.,r['row']['hold_start_position_m']-r['row']['hold_min_position_m']))<1e-9 and abs(r['row']['hold_start_time_s']-r['row']['hold_confirmation_time_s']-.01)<1e-8 for r in records if r['row']['hold_started'])
    checks['trace_availability_and_endpoint_times_match']=all(
        x['main_available']==not_any and abs(x['state_time_s']-x['t_s']-.01)<1e-8
        for rec in records for x in rec['row'].get('trace',[]) for not_any in [not any(lo<=x['t_s']<hi for lo,hi in rec['task']['config'].get('main_isolation_intervals',[]))])
    groups={}
    for r in records:groups.setdefault(r['task']['group'],{}).setdefault(r['task']['chain'],[]).append(r['row'])
    def near(x,y):
        if isinstance(x,dict):return x.keys()==y.keys() and all(near(v,y[k]) for k,v in x.items())
        if isinstance(x,list):return len(x)==len(y) and all(near(v,w) for v,w in zip(x,y))
        if isinstance(x,(float,int)) and not isinstance(x,bool):return math.isclose(x,y,rel_tol=1e-10,abs_tol=2e-8)
        return x==y
    for family in groups.values():
        for rr in family.values():rr.sort(key=lambda r:r['seed'])
    checks['all_88_summaries_recomputed']=all(near(a['summary'][g][c],summarize_new(rows)) for g,f in groups.items() for c,rows in f.items())
    checks['paired_normal_intervals_recomputed']=all(near(a['paired_normal_smc_to_hybrid'][k],pair(groups['normal']['smc_accumulator'],groups['normal']['observer_hybrid'],k)) for k in KEYS)
    checks['both_joint_policy_interval_sets_recomputed']=all(near(a[name][k],pair(groups['isolated_on'][left],groups['isolated_on'][right],k)) for name,left,right in [('paired_isolated_smc_to_hybrid','smc_accumulator','observer_hybrid'),('paired_isolated_scalar_to_availability','observer_hybrid','reserve_supervisor')] for k in KEYS)
    checks['paired_storage_effects_recomputed']=all(near(a['storage_causal'][c]['off_minus_on'][k],pair(groups['isolated_on'][c],groups['isolated_off'][c],k)) for c in CHAINS for k in KEYS)
    checks['every_conditional_storage_pass_transition_recomputed']=all(a['storage_causal'][c]['on_pass_off_fail']==[r['seed'] for r,o in zip(groups['isolated_on'][c],groups['isolated_off'][c]) if passed(r) and not passed(o)] for c in CHAINS)
    exploratory=0
    for directory,npaths in [('reserve_pilot',12),('reserve_long_pilot',8),('supply_pilot',8)]:
        p=REV/'results'/directory;protocol=json.loads((p/'protocol.json').read_text())
        checks[directory+'_frozen_sources_and_all_paths_preserved']=all(sha(ROOT/n)==h for n,h in protocol['source_sha256'].items()) and all((p/(t['id']+'.json')).is_file() for t in protocol['tasks']) and len(protocol['tasks'])==npaths
        exploratory+=npaths
    checks['28_exploratory_paths_excluded_from88']=exploratory==28 and all(t['config']['seed'] not in [5200,5201,5202] for t in spec['tasks'])
    parity=json.loads((OUT/'full_parity.json').read_text())
    checks['two_1800s_original_controller_trajectories_exactly_preserved']=parity['original_source_sha256']==sha(ROOT/'code/lift_control/lift_v2_experiment.py') and all(not r['differences'] and r['all_old_trace_fields_identical'] and r['checkpoint_sha256']==sha(OUT/'checkpoints'/f'normal_{r["chain"]}_5500_10.json') for r in parity['rows']) and len(parity['rows'])==2
    checks['abandoned88_path_plan_has_no_claimed_results']=(REV/'results/reserve_validation/protocol.json').is_file() and not (REV/'results/reserve_validation/checkpoints').exists()
    protected=json.loads((REV/'evidence/risk_extension_baseline/protected_paper2.json').read_text())
    checks['all220_accepted_paper2_files_unchanged']=len(protected)==220 and all((ROOT/n).is_file() and sha(ROOT/n)==h for n,h in protected.items())
    result=dict(checks=checks,conservation=conservation,protocol_sha256=sha(OUT/'protocol.json'),
        analysis_sha256=sha(OUT/'analysis.json'),checker_sha256=sha(Path(__file__)))
    dump(OUT/'numerical_verification.json',result);print(json.dumps(checks,indent=2));assert all(checks.values()),{k:v for k,v in checks.items() if not v}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--snapshot',action='store_true')
    ap.add_argument('--preflight',action='store_true');ap.add_argument('--results',action='store_true');ap.add_argument('--full-parity',action='store_true');a=ap.parse_args()
    if a.snapshot:snapshot()
    if a.preflight:preflight()
    if a.full_parity:full_parity()
    if a.results:results()
if __name__=='__main__':main()
