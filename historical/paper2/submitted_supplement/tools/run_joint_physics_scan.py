from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/energy_management')]
from experiments import ExperimentConfig, run_definition

rows=[]
for low in (0.18,0.15,0.12):
    for rated in (220_000.0,240_000.0,260_000.0):
        cfg=ExperimentConfig(duration_s=600.0,
          profile_name='regenerative_agri_workcycle', accessory_for_all_w=18_000.0,
          realistic_maps=True, engine_low_load_efficiency=low,
          regenerative_braking=True, regen_power_limit_w=45_000.0,
          engine_rated_w=rated, battery_capacity_wh=200_000.0,
          battery_power_limit_w=150_000.0, motor_peak_w=150_000.0,
          mpc_terminal_weight=2_000_000.0)
        b=run_definition('realistic_ool',cfg)
        r=run_definition('robust_mpc',cfg)
        saving=(b['fuel_l']-r['fuel_l'])/b['fuel_l']*100.0 if b['valid'] else None
        row={'low_load_efficiency':low,'engine_rated_kw':rated/1000.0,
          'battery_capacity_kwh':200.0,'motor_peak_kw':150.0,
          'baseline_fuel_l':b['fuel_l'],'baseline_valid':b['valid'],
          'mpc_fuel_l':r['fuel_l'],'mpc_valid':r['valid'],
          'saving_pct':saving,'soc_error':r['soc_error'],
          'max_shortage_w':r['max_shortage_w'],
          'max_motor_power_violation_w':r['max_motor_power_violation_w'],
          'max_mg1_power_violation_w':r['max_mg1_power_violation_w'],
          'max_mg1_speed_violation_rpm':r['max_mg1_speed_violation_rpm'],
          'max_mg2_speed_violation_rpm':r['max_mg2_speed_violation_rpm']}
        rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
out=ROOT/'results/joint_physics_scan.json'
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
