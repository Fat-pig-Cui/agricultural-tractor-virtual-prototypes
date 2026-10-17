"""Predeclared paired RK4 comparators and joint mechanical corner screens.

Frozen gains, 1800 s, common 10 ms sensing/control and unchanged random draws.
All eight mass/damping/stiffness corners are retained, including failures.
Checkpoints permit resuming the exact protocol without replacing evidence.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import product
import hashlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'code'), str(ROOT / 'code/lift_control')]
from lift_v2_experiment import LiftV2Config, run_lift_v2
from run_paper1_major_revision import summarize, stats

OUT = ROOT / 'revisions/machines_major_revision/results'
CHECKPOINTS = OUT / 'strengthening_checkpoints'
SEEDS = list(range(4300, 4305))
NOMINAL = {'mass_kg': 1200, 'viscous_n_s_m': 2200, 'stiffness_n_m': 18000}


def protocol():
    tasks = []
    for sub in [10, 20]:
        for chain in ['observer_hybrid', 'pid_accumulator', 'pid_accumulator_matched']:
            for seed in SEEDS:
                tasks.append(dict(family='comparators', group=f'{chain}_{sub}',
                                  chain=chain, seed=seed, substeps=sub, overrides={}))
    for scales in product([0.7, 1.3], repeat=3):
        label = '_'.join(str(int(s * 10)) for s in scales)
        overrides = {k: v * s for (k, v), s in zip(NOMINAL.items(), scales)}
        for seed in SEEDS:
            tasks.append(dict(family='joint', group=f'joint_{label}', chain='observer_hybrid',
                              seed=seed, substeps=10, scales=list(scales), overrides=overrides))
    return dict(duration_s=1800, controller_period_s=0.01, seeds=SEEDS,
                integration='classical RK4 with endpoint pressure/stroke projections; no event root finding',
                selection='All tasks fixed before execution; no retuning, no best-case selection',
                initialization='Each plant starts at its own declared force-balance initial state; observer initialization unchanged',
                controller='Nominal controller/observer coefficients remain fixed under true-plant overrides',
                joint_scope='All eight vertices of the selected three-parameter box; not its interior or a certified robust invariant set',
                pass_rule='Hold entry, drop<=10 mm, post-transition max absolute error<=10 mm, zero relief and stroke samples',
                tasks=tasks)


def run(task):
    chain = 'pid_accumulator' if task['chain'] == 'pid_accumulator_matched' else task['chain']
    row = run_lift_v2(chain, LiftV2Config(duration_s=1800, seed=task['seed']),
                      integration_scheme='rk4', integration_substeps=task['substeps'],
                      baseline_dwell_s=8 if task['chain'] == 'pid_accumulator_matched' else 0,
                      plant_overrides=task['overrides'])
    return task, row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(exist_ok=True)
    spec = protocol()
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [Path(__file__), ROOT/'code/lift_control/lift_v2_experiment.py',
                               ROOT/'code/lift_control/hydraulic_v2.py']}
    spec['source_sha256'] = source_hashes
    protocol_path = OUT / 'strengthening_protocol.json'
    if protocol_path.exists():
        assert json.loads(protocol_path.read_text()) == spec, 'Protocol/source drift: preserve existing evidence'
    else:
        protocol_path.write_text(json.dumps(spec, indent=2))
    groups = {}
    pending = []
    reused = []
    for task in spec['tasks']:
        path = CHECKPOINTS / f"{task['group']}_{task['seed']}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            assert saved['task'] == task
            groups.setdefault(task['group'], []).append(saved['row'])
        elif task['family'] == 'comparators' and task['chain'] == 'observer_hybrid':
            original = OUT / f"rk4_integration_{task['substeps']}.json"
            row = next(r for r in json.loads(original.read_text())['rows'] if r['seed'] == task['seed'])
            path.write_text(json.dumps(dict(task=task, row=row, reused_from=original.name,
                                            reused_sha256=hashlib.sha256(original.read_bytes()).hexdigest()), indent=2))
            reused.append(str(path.name))
            groups.setdefault(task['group'], []).append(row)
        else:
            pending.append(task)
    start = time.time()
    print(f"protocol={len(spec['tasks'])} pending={len(pending)} reused_hybrid={len(reused)}", flush=True)
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 1)) as pool:
        futures = [pool.submit(run, task) for task in pending]
        for i, f in enumerate(as_completed(futures), 1):
            task, row = f.result()
            (CHECKPOINTS / f"{task['group']}_{task['seed']}.json").write_text(
                json.dumps(dict(task=task, row=row), indent=2))
            groups.setdefault(task['group'], []).append(row)
            print(f"{i}/{len(pending)} {task['group']} seed={task['seed']} drop={row['hold_drop_mm']} maxerr={row['post_transition_max_abs_error_mm']:.4f} elapsed={time.time()-start:.0f}s", flush=True)
    results = {name: dict(summary=summarize(sorted(rows, key=lambda r:r['seed'])),
                          rows=sorted(rows, key=lambda r:r['seed']))
               for name, rows in sorted(groups.items())}
    paired = {}
    for sub in [10, 20]:
        hybrid = {r['seed']:r for r in results[f'observer_hybrid_{sub}']['rows']}
        for chain in ['pid_accumulator', 'pid_accumulator_matched']:
            differences = [dict(seed=r['seed'], **{k:r[k]-hybrid[r['seed']][k]
                           for k in ['hold_drop_mm', 'post_transition_rmse_mm',
                                     'accumulator_oil_used_ml', 'mode_switches']})
                           for r in results[f'{chain}_{sub}']['rows']]
            paired[f'{chain}_{sub}_minus_hybrid'] = dict(rows=differences,
                summary={k:stats([r[k] for r in differences]) for k in differences[0] if k!='seed'})
    report = dict(protocol_file=protocol_path.name, groups=results, paired=paired,
                  unique_protocol_rows=len(spec['tasks']), newly_computed_rows=60,
                  reused_hybrid_rows=10, elapsed_this_invocation_s=time.time()-start)
    (OUT/'strengthening_audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v['summary'] for k,v in results.items()}, indent=2))


if __name__ == '__main__':
    main()
