#!/usr/bin/env python3
"""Predeclared revision experiments; preserve all original submission outputs."""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import statistics
import sys
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'revisions' / 'energies_major_revision'
sys.path[:0] = [str(ROOT / 'code'), str(ROOT / 'code/energy_management')]
from common.profiles import (stochastic_agri_workcycle_profile,
    agri_workcycle_profile, low_load_agri_workcycle_profile, high_variability_profile)
from viability_ecms_v2 import ControllerFeatures, ECMSSettings, PowerSplitParameters, run_cycle
from os_ecvt_model import LiteratureBSFCMap, RealisticDieselMap

PARAMS = PowerSplitParameters(engine_power_step_w=5000.0)
FROZEN = ECMSSettings(base_equivalence_factor=1.0, proportional_gain=40.0,
    viability_band_soc=0.045, terminal_soc_tolerance=1e-4)
DEV = tuple(range(5100, 5106))
TEST = tuple(range(5120, 5140))


def profile(seed):
    return stochastic_agri_workcycle_profile(600., 1., seed=seed,
        disturbance_scale=1., smooth_disturbances=True)


def evaluate(task):
    label, seed, mode, settings, features, params, map_name, cycle = task
    points = (profile(seed) if cycle == 'stochastic' else
              agri_workcycle_profile(600., 1.) if cycle == 'deterministic' else
              low_load_agri_workcycle_profile(600., 1.) if cycle == 'low_load' else
              high_variability_profile(300., 1.))
    engine_map = (LiteratureBSFCMap(peak=.42, rated_power_w=params.engine_rated_w)
                  if map_name == 'literature' else
                  RealisticDieselMap(low_load_efficiency=float(map_name)))
    try:
        row = run_cycle(points, mode, settings, params, engine_map=engine_map,
            features=features, capture_full_trajectory=seed == 5120)
        row.update(label=label, seed=seed, completed=True)
    except RuntimeError as error:
        row = dict(label=label, seed=seed, completed=False, strict_valid=False,
                   failure=str(error))
    return row


def run(tasks):
    with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
        return list(pool.map(evaluate, tasks))


def summary(rows, baselines):
    completed = [r for r in rows if r['completed']]
    pairs = [r for r in completed if r['strict_valid'] and
             baselines[r['seed']]['completed'] and baselines[r['seed']]['strict_valid']]
    def savings(rs, field):
        return [(baselines[r['seed']][field]-r[field])/baselines[r['seed']][field]*100
                for r in rs if baselines[r['seed']]['completed']]
    def ci(values):
        if len(values)<2:return None
        critical = float(student_t.ppf(.975,len(values)-1))
        half=critical*statistics.stdev(values)/len(values)**.5
        mean=statistics.fmean(values)
        return [mean-half,mean+half]
    values=savings(pairs,'energy_normalized_fuel_l')
    diagnostic=savings(completed,'energy_normalized_fuel_l')
    return dict(count=len(rows), completed_count=len(completed),
        terminal_valid_count=sum(r['strict_valid'] for r in completed),
        hard_failure_count=len(rows)-len(completed), paired_valid_count=len(pairs),
        mean_saving_pct=statistics.fmean(values) if values else None,
        saving_95ci_pct=ci(values),
        mean_raw_saving_pct=statistics.fmean(savings(pairs,'fuel_l')) if pairs else None,
        completed_only_normalized_diagnostic_pct=statistics.fmean(diagnostic) if diagnostic else None,
        mean_soc_error=statistics.fmean(r['soc_error'] for r in completed) if completed else None,
        max_abs_soc_error=max((abs(r['soc_error']) for r in completed),default=None),
        mean_shield_activations=statistics.fmean(r['shield_activations'] for r in completed) if completed else None,
        mean_soft_empty_sets=statistics.fmean(r['soft_corridor_empty_sets'] for r in completed) if completed else None,
        mean_reserve_activations=statistics.fmean(r['reserve_activations'] for r in completed) if completed else None,
        mean_engine_starts=statistics.fmean(r['engine_starts'] for r in completed) if completed else None)


def save(name, data):
    (OUT/'results').mkdir(parents=True,exist_ok=True)
    (OUT/'results'/name).write_text(json.dumps(data,indent=2),encoding='utf-8')


def controller_tasks(label,seeds,mode='viability_ecms',settings=FROZEN,
                     features=ControllerFeatures(),params=PARAMS,map_name='literature',cycle='stochastic'):
    return [(label,s,mode,settings,features,params,map_name,cycle) for s in seeds]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audit-only',action='store_true');args=parser.parse_args()
    submitted_path=ROOT/'tmp/submission_2026-09-27/energies_supplement/results/paper2_viability_ecms_v2.json'
    if not submitted_path.exists():
        submitted_path=OUT/'results/submitted_reference.json'
    original=json.loads(submitted_path.read_text())
    protocol=dict(development_seeds=DEV,independent_holdout_seeds=TEST,
        settings=asdict(FROZEN),platform=asdict(PARAMS),
        t_terminal=1e-4, original_submission='2026-09-27',
        source_sha256=hashlib.sha256((ROOT/'code/energy_management/viability_ecms_v2.py').read_bytes()).hexdigest(),
        selection='maximize terminal-valid development count, then completed count, then normalized diagnostic saving; tie minimize SOC error',
        paired_statistics='only completed, terminal-valid same-seed pairs; all failed and SOC-invalid paths retained')
    if not args.audit_only:
        base_dev=run(controller_tasks('load_following',DEV,mode='load_following'))
        bd={r['seed']:r for r in base_dev}
        configs=[]
        for family in ['fixed_ecms','adaptive_ecms','fixed_shared_filter']:
            for i in range(15):
                if family.startswith('fixed'):
                    setting=replace(FROZEN,base_equivalence_factor=.3+.1*i,proportional_gain=0.)
                else:
                    setting=replace(FROZEN,base_equivalence_factor=[.8,1.,1.2][i//5],
                                    proportional_gain=[20.,40.,60.,80.,120.][i%5])
                features=ControllerFeatures(public_phase_reference=family=='fixed_shared_filter',
                    soc_corridor_filter=family=='fixed_shared_filter')
                mode='viability_ecms' if family=='fixed_shared_filter' else family
                configs.append((family,i,mode,setting,features))
        tasks=[task for family,i,mode,setting,features in configs for task in
               controller_tasks(f'{family}:{i}',DEV,mode,setting,features)]
        dev_rows=run(tasks)
        candidates=[]
        for family,i,mode,setting,features in configs:
            rows=[r for r in dev_rows if r['label']==f'{family}:{i}']
            candidates.append(dict(family=family,index=i,mode=mode,settings=asdict(setting),
                features=asdict(features),summary=summary(rows,bd),rows=rows))
        selected={}
        for family in ['fixed_ecms','adaptive_ecms','fixed_shared_filter']:
            pool=[c for c in candidates if c['family']==family]
            selected[family]=max(pool,key=lambda c:(c['summary']['terminal_valid_count'],
                c['summary']['completed_count'],
                c['summary']['completed_only_normalized_diagnostic_pct'] or -1e6,
                -(c['summary']['max_abs_soc_error'] or 0)))
        save('development_selection.json',dict(protocol=protocol,candidates=candidates,selected=selected))
        print('Development frozen', {k:v['index'] for k,v in selected.items()},flush=True)
        configs_test=[('full', 'viability_ecms',FROZEN,ControllerFeatures()),
            ('without_adaptation','viability_ecms',replace(FROZEN,proportional_gain=0),ControllerFeatures()),
            ('without_phase','viability_ecms',FROZEN,ControllerFeatures(public_phase_reference=False)),
            ('without_filter','adaptive_ecms',FROZEN,ControllerFeatures(soc_corridor_filter=False)),
            ('without_reserve','viability_ecms',FROZEN,ControllerFeatures(conditional_electric_reserve=False)),
            ('step_adaptive_constant_reference','adaptive_ecms',FROZEN,
             ControllerFeatures(public_phase_reference=False,soc_corridor_filter=False,conditional_electric_reserve=False)),
            ('step_add_public_phase','adaptive_ecms',FROZEN,
             ControllerFeatures(soc_corridor_filter=False,conditional_electric_reserve=False)),
            ('load_following','load_following',FROZEN,ControllerFeatures())]
        for family,c in selected.items():
            configs_test.append((f'tuned_{family}',c['mode'],ECMSSettings(**c['settings']),ControllerFeatures(**c['features'])))
        rows=run([t for label,mode,setting,features in configs_test for t in
                  controller_tasks(label,TEST,mode,setting,features)])
        baseline={r['seed']:r for r in rows if r['label']=='load_following'}
        holdout={label:dict(mode=mode,settings=asdict(setting),features=asdict(features),
            rows=[r for r in rows if r['label']==label],
            summary=summary([r for r in rows if r['label']==label],baseline))
            for label,mode,setting,features in configs_test}
        replay=run(controller_tasks('submission_replay',tuple(range(3120,3140))))
        original_rows={r['seed']:r for r in original['holdout']['viability_ecms_strict_1e-4']['rows']}
        parity=max(abs(r['fuel_l']-original_rows[r['seed']]['fuel_l']) for r in replay)
        assert parity<1e-10,parity
        save('ablation_and_comparison.json',dict(protocol=protocol,holdout=holdout,
             submission_replay_fuel_max_difference_l=parity,submission_replay=replay))
        print('Independent holdout', {k:v['summary'] for k,v in holdout.items()},flush=True)
    # Same frozen Kp=40 everywhere; independent from original Kp=60 audits.
    audit_configs=[('deterministic',PARAMS,'literature','deterministic',(0,)),
        ('low_load',PARAMS,'literature','low_load',(0,)),
        ('high_variability',PARAMS,'literature','high_variability',(0,)),
        ('new_stochastic',PARAMS,'literature','stochastic',tuple(range(5160,5180)))]
    for step in [10000.,5000.,2500.]:
        audit_configs.append((f'grid_{step:g}',replace(PARAMS,engine_power_step_w=step),'literature','stochastic',tuple(range(5180,5186))))
    for name in ['literature','0.15','0.25','0.35']:
        audit_configs.append((f'map_{name}',PARAMS,name,'stochastic',tuple(range(5200,5220))))
    for cap in [120000.,200000.,280000.]:
        audit_configs.append((f'capacity_{cap:g}',replace(PARAMS,battery_capacity_wh=cap),'literature','stochastic',tuple(range(5200,5220))))
    tasks=[]
    for label,params,map_name,cycle,seeds in audit_configs:
        for mode in ['load_following','viability_ecms']:
            tasks.extend(controller_tasks(f'{label}:{mode}',seeds,mode=mode,params=params,map_name=map_name,cycle=cycle))
    rows=run(tasks)
    output=[]
    for label,params,map_name,cycle,seeds in audit_configs:
        b=[r for r in rows if r['label']==f'{label}:load_following']
        p=[r for r in rows if r['label']==f'{label}:viability_ecms']
        output.append(dict(label=label,platform=asdict(params),map=map_name,cycle=cycle,
            baseline_rows=b,proposed_rows=p,summary=summary(p,{r['seed']:r for r in b})))
    save('frozen_kp40_audits.json',dict(protocol=protocol,audits=output))
    print('Kp40 audits', {c['label']:c['summary'] for c in output},flush=True)


if __name__=='__main__':main()
