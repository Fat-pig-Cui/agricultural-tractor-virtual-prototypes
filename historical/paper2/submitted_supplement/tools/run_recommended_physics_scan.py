from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/energy_management')]
from experiments import ExperimentConfig, run_definition

rows=[]
for rated in (180_000.0, 220_000.0, 260_000.0, 300_000.0):
    cfg=ExperimentConfig(duration_s=600.0,
        profile_name='regenerative_agri_workcycle',
        accessory_for_all_w=18_000.0, realistic_maps=True,
        regenerative_braking=True, regen_power_limit_w=45_000.0,
        engine_rated_w=rated, battery_capacity_wh=150_000.0,
        battery_power_limit_w=120_000.0, motor_peak_w=120_000.0,
        mpc_terminal_weight=2_000_000.0)
    b=run_definition('realistic_ool',cfg)
    row={'engine_rated_kw':rated/1000.0,'baseline_fuel_l':b['fuel_l'],
         'baseline_valid':b['valid']}
    for name in ('deterministic_mpc','robust_mpc'):
        r=run_definition(name,cfg)
        row[name]={'fuel_l':r['fuel_l'],'valid':r['valid'],
          'saving_pct':(b['fuel_l']-r['fuel_l'])/b['fuel_l']*100.0,
          'soc_error':r['soc_error'],'max_shortage_w':r['max_shortage_w'],
          'max_motor_power_violation_w':r['max_motor_power_violation_w'],
          'max_mg1_power_violation_w':r['max_mg1_power_violation_w'],
          'max_mg1_speed_violation_rpm':r['max_mg1_speed_violation_rpm'],
          'max_mg2_speed_violation_rpm':r['max_mg2_speed_violation_rpm']}
    rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
out=ROOT/'results/recommended_physics_scan.json'
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
