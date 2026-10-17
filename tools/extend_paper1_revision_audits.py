"""Aligned historical-noise replay and original-plant observer statistics."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'code'),str(ROOT/'code/lift_control')]
from run_paper1_major_revision import summarize
from lift_v2_experiment import run_lift_v2,LiftV2Config

def run(seed):
    return run_lift_v2('observer_hybrid',LiftV2Config(duration_s=1800,seed=seed,
        pressure_noise_scale=2),trace_interval_s=.1 if seed==2060 else None)

def main():
    out=ROOT/'revisions/machines_major_revision/results'
    with ProcessPoolExecutor(max_workers=4) as p:rows=list(p.map(run,range(2060,2080)))
    (out/'aligned_legacy_pressure_noise.json').write_text(json.dumps(dict(
        protocol='V2: 0.10 MPa independent raw noise per chamber, internal observer retained; seeds2060--2079; 1800s',
        alignment_limits='Same absolute pressure SD and seed identifiers as historical audit. Different plants, reference paths, noise draws/interfaces and observers; not an isolated architecture-only intervention.',
        summary=summarize(rows),rows=rows),indent=2))
    original=json.loads((ROOT/'results/paper1_two_chamber_v2.json').read_text())
    stats={}
    for c,b in original['holdout'].items():
        rr=[dict(r,stroke_boundary_samples=0,accumulator_active_time_s=0,
                 minimum_accumulator_pressure_mpa=14) for r in b['rows']]
        summary=summarize(rr)
        # No invented diagnostics for archived runs: remove fields not recorded.
        for key in ['stroke_boundary_samples','accumulator_active_time_s','minimum_accumulator_pressure_mpa']:summary.pop(key)
        stats[c]=summary
    (out/'submitted_statistics.json').write_text(json.dumps(stats,indent=2))
    print(json.dumps({'aligned':summarize(rows)},indent=2))
if __name__=='__main__':main()
