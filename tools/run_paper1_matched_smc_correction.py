"""Frozen correction of the active-SMC dwell/gating execution interface.

The 255 earlier paths remain immutable. Their SMC dispatch passed zero dwell;
this separate runner supplies the same explicit eight-second argument to both
active baselines. New joint vectors are frozen before corrected development.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import product
from pathlib import Path
import copy
import hashlib
import json
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'code/lift_control')]
import run_paper1_risk_closure as historical
from lift_v2_experiment import LiftV2Config, run_lift_v2

REV = ROOT/'revisions/machines_major_revision'
OUT = REV/'results/matched_smc_correction'
EXT = REV/'results/risk_extension'
MAR = REV/'results/margin_selection'
CHAINS = ('observer_hybrid', 'pid_accumulator', 'smc_accumulator', 'margin_hybrid')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')


def freeze(path, obj):
    obj = json.loads(json.dumps(obj))
    if path.exists():
        assert json.loads(path.read_text()) == obj, f'Frozen record differs: {path}'
    else:
        dump(path, obj)
    return obj


def execution(chain, substeps):
    actual = 'observer_hybrid' if chain == 'margin_hybrid' else chain
    return dict(controller=actual, baseline_dwell_s=8.0 if actual in
                ('pid_accumulator', 'smc_accumulator') else 0.0,
                integration_substeps=substeps, integration_scheme='rk4',
                observer_variant='shared')


def task(group, seed, chain, config, overrides=None, substeps=10, duration=1800.):
    row = historical.task(group, seed, chain=chain, substeps=substeps,
                          duration=duration, config=config,
                          overrides=overrides, matched=True)
    row['execution'] = execution(chain, substeps)
    return row


def plan():
    old = json.loads((EXT/'protocol.json').read_text())
    candidates = old['candidates']
    training = [task(f'corrected_smc_train_{c["id"]}', seed, 'smc_accumulator',
                     dict(tracking_gain_scale=c['tracking_gain_scale'],
                          accumulator_gain_scale=c['accumulator_gain_scale'],
                          hold_main_valve_limit=.10,
                          load_schedule=historical.TRAIN_SCHEDULE), duration=300.)
                for c, seed in product(candidates, range(4600,4603))]
    rng = random.Random(51191)
    sampled = {}
    ranges = old['sampling_ranges']
    for key, (lo, hi) in {**ranges['plant'], **ranges['config']}.items():
        bins = list(range(24)); rng.shuffle(bins)
        sampled[key] = [lo+(hi-lo)*(j+rng.random())/24 for j in bins]
    vectors = [dict(seed=5100+i,
                    config={k:sampled[k][i] for k in ranges['config']},
                    overrides={k:sampled[k][i] for k in ranges['plant']})
               for i in range(24)]
    sources = [Path(__file__), ROOT/'code/lift_control/lift_v2_experiment.py',
               ROOT/'code/lift_control/hydraulic_v2.py',
               ROOT/'tools/run_paper1_risk_closure.py']
    return dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
                historical_protocol_sha256=sha(EXT/'protocol.json'),
                historical_selection_sha256=sha(EXT/'selection.json'),
                original_selection_sha256=sha(historical.OUT/'selection.json'),
                margin_protocol_sha256=sha(MAR/'protocol.json'),
                candidates=candidates, training=training, new_vectors=vectors,
                new_rng_seed=51191, sampling_ranges=ranges,
                correction='Historical dispatcher supplied baseline_dwell_s=0 to active SMC. This runner passes 8 explicitly, enabling the dwell latch and mode-gated discharge. All earlier results remain historical.',
                selection='Failures, mean unchanged J, candidate ID; only 27 corrected development paths select SMC. Other three policies remain frozen.',
                final_plan='20 corrected SMC common-nominal paths, 24 known-vector and 24 previously fresh-vector replays; 96 new joint paths for four policies. The 68 SMC replays are known-protocol follow-up, not fresh holdouts.',
                independent_scope='24 newly frozen stratified joint vectors; numerical design, not physical frequencies or certified robustness.',
                expected_new_paths=191)


def run(row):
    args = dict(row['execution'])
    controller = args.pop('controller')
    result = run_lift_v2(controller, LiftV2Config(**row['config']),
                         plant_overrides=row['overrides'],
                         trace_interval_s=.5 if row['config']['seed'] in (4700,5100)
                         and 'train' not in row['group'] else None, **args)
    return dict(task=row, execution_applied=row['execution'], row=result)


def execute(tasks, workers):
    tasks = json.loads(json.dumps(tasks))
    directory = OUT/'checkpoints'; directory.mkdir(exist_ok=True)
    records = {}; pending = []
    for row in tasks:
        path = directory/(row['id']+'.json')
        if path.exists():
            saved = json.loads(path.read_text()); assert saved['task'] == row
            records[row['id']] = saved
        else:
            pending.append(row)
    started = time.monotonic()
    print(f'pending={len(pending)} existing={len(records)}', flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run, row) for row in pending]
        for i, future in enumerate(as_completed(futures),1):
            saved = future.result(); row = saved['task']; records[row['id']] = saved
            dump(directory/(row['id']+'.json'), saved)
            print(f'{i}/{len(pending)} {row["id"]} error={saved["row"]["post_transition_max_abs_error_mm"]:.4f} elapsed={time.monotonic()-started:.0f}s', flush=True)
    return [records[row['id']] for row in tasks]


def select(groups, protocol):
    scores = []
    for c in protocol['candidates']:
        group = groups[f'corrected_smc_train_{c["id"]}']
        rows = group['rows']; summary = group['summary']
        scores.append(dict(candidate=c, failures=len(rows)-summary['passed'],
                           J=sum(historical.objective(r) for r in rows)/len(rows),
                           development_worst_error_mm=summary['post_transition_max_abs_error_mm']['max'],
                           means={k:sum(r[k] for r in rows)/len(rows) for k in historical.METRICS}))
    return freeze(OUT/'selection.json', dict(
        selected=min(scores,key=lambda s:(s['failures'],s['J'],s['candidate']['id'])),
        all_candidates=scores, protocol_sha256=sha(OUT/'protocol.json')))


def final_plan(protocol, selection):
    prior = json.loads((historical.OUT/'selection.json').read_text())
    margin = json.loads((MAR/'protocol.json').read_text())
    choices = {k:v['candidate'] for k,v in prior['selected'].items()}
    choices['smc_accumulator'] = selection['selected']['candidate']
    choices['margin_hybrid'] = margin['selected']['candidate']
    def conf(chain):
        return dict(tracking_gain_scale=choices[chain]['tracking_gain_scale'],
                    accumulator_gain_scale=choices[chain]['accumulator_gain_scale'],
                    hold_main_valve_limit=.10)
    tasks = [task(f'corrected_smc_nominal_{sub}', seed, 'smc_accumulator',
                  conf('smc_accumulator'), substeps=sub)
             for sub,seed in product([10,20],range(4700,4710))]
    for name, vectors in [
        ('known', [dict(seed=t['config']['seed'],config=t['config'],overrides=t['overrides'])
                   for t in json.loads((historical.OUT/'protocol.json').read_text())['uncertainty']]),
        ('previous_joint', json.loads((EXT/'protocol.json').read_text())['fresh_vectors'])]:
        tasks += [task('corrected_smc_'+name, v['seed'], 'smc_accumulator',
                       {**v['config'],**conf('smc_accumulator')}, v['overrides'])
                  for v in vectors]
    tasks += [task('new_joint_'+chain,v['seed'],chain,
                   {**v['config'],**conf(chain)},v['overrides'])
              for chain,v in product(CHAINS,protocol['new_vectors'])]
    return tasks


def main():
    p = argparse.ArgumentParser(); p.add_argument('--workers',type=int,default=6)
    p.add_argument('--stage',choices=['plan','all','training','final'],default='all')
    a = p.parse_args(); OUT.mkdir(exist_ok=True)
    protocol = freeze(OUT/'protocol.json',plan())
    if a.stage == 'plan': print('PROTOCOL FROZEN',flush=True); return
    if a.stage in ('all','training'):
        records = execute(protocol['training'],a.workers)
        groups = historical.groups(records); dump(OUT/'training.json',groups)
        selection = select(groups,protocol)
        print('SELECTED',json.dumps(selection['selected']),flush=True)
    if a.stage in ('all','final'):
        selection = json.loads((OUT/'selection.json').read_text())
        tasks = freeze(OUT/'final_tasks.json',final_plan(protocol,selection))
        groups = historical.groups(execute(tasks,a.workers)); dump(OUT/'final.json',groups)
    print('COMPLETE',a.stage,flush=True)


if __name__ == '__main__':
    main()
