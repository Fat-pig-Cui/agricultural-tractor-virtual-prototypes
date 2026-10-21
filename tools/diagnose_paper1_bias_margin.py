"""Locate the two already reported failures; 30 s traces are diagnostic only."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'code/lift_control')]
from lift_v2_experiment import LiftV2Config,run_lift_v2
OUT=ROOT/'revisions/machines_major_revision/results/margin_selection'
parent=ROOT/'revisions/machines_major_revision/results/risk_closure'
cases=[]
for seed in [4806,4821]:
    saved=json.loads((parent/f'checkpoints/uncertainty_{seed}.json').read_text())
    for name,gain in [('original',1.),('margin',1.3)]:
        # Truncate the recorded horizon without compressing the temperature
        # ramp: keep the original 1800 s temperature at each 10 ms sample.
        config={**saved['task']['config'],'duration_s':30.,
            'temperature_end_c':25.+25.*(3000-1)/(180000-1),
            'tracking_gain_scale':gain,'accumulator_gain_scale':.5 if name=='margin' else 1.,'hold_main_valve_limit':.10}
        cases.append(dict(seed=seed,design=name,config=config,overrides=saved['task']['overrides'],full_horizon_previous_max_error_mm=saved['row']['post_transition_max_abs_error_mm']))
spec=dict(source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'code/lift_control/lift_v2_experiment.py',ROOT/'code/lift_control/hydraulic_v2.py']},
    cases=cases,temperature_profile='First 3000 samples of the full 180000-sample 25--50 C ramp; not a compressed 30 s heating ramp.',scope='Known failures only; 30 s time-location diagnosis, not an independent 1800 s pass-rate test.')
p=OUT/'diagnostic_protocol.json'
if p.exists():assert json.loads(p.read_text())==spec
else:p.write_text(json.dumps(spec,indent=2)+'\n')
rows=[]
for t in cases:
    r=run_lift_v2('observer_hybrid',LiftV2Config(**t['config']),plant_overrides=t['overrides'],integration_substeps=10,integration_scheme='rk4',trace_interval_s=.01)
    post=[v for v in r['trace'] if v['t_s']>=8.]
    peak=max(post,key=lambda v:abs(v['error_mm']))
    if t['design']=='original':
        assert abs(r['post_transition_max_abs_error_mm']-t['full_horizon_previous_max_error_mm'])<1e-8
    rows.append(dict(case=t,row=r,maximum_error_endpoint=peak['state_time_s'],maximum_error_mode=peak['mode'],peak_before_hold_confirmation=peak['state_time_s']<r['hold_confirmation_time_s']))
    print(t['seed'],t['design'],r['post_transition_max_abs_error_mm'],peak['state_time_s'],peak['mode'],flush=True)
(OUT/'diagnostics.json').write_text(json.dumps(rows,indent=2)+'\n')
