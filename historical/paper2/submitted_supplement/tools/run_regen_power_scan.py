from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/energy_management')]
from experiments import ExperimentConfig, run_definition
rows=[]
for regen in (30_000.0,45_000.0,60_000.0,75_000.0):
    cfg=ExperimentConfig(duration_s=600.0,
        profile_name='regenerative_agri_workcycle', accessory_for_all_w=18_000.0,
        realistic_maps=True, regenerative_braking=True,
        regen_power_limit_w=regen, engine_rated_w=300_000.0,
        battery_capacity_wh=150_000.0, battery_power_limit_w=120_000.0,
        motor_peak_w=120_000.0, mpc_terminal_weight=2_000_000.0)
    b=run_definition('realistic_ool',cfg); r=run_definition('robust_mpc',cfg)
    row={'regen_limit_kw':regen/1000.0,'baseline_fuel_l':b['fuel_l'],
         'baseline_valid':b['valid'],'mpc_fuel_l':r['fuel_l'],
         'saving_pct':(b['fuel_l']-r['fuel_l'])/b['fuel_l']*100.0,
         'valid':r['valid'],'soc_error':r['soc_error'],
         'max_shortage_w':r['max_shortage_w']}
    rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
out=ROOT/'results/regen_power_scan.json'
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
