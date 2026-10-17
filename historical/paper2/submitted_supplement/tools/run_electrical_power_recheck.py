from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT/'code'), str(ROOT/'code/energy_management')]
from experiments import ExperimentConfig, run_definition

rows=[]
for peak in (90_000.0, 120_000.0, 150_000.0):
    cfg=ExperimentConfig(duration_s=60.0, profile_name='agri_workcycle',
        accessory_for_all_w=18_000.0, realistic_maps=True,
        battery_capacity_wh=150_000.0, battery_power_limit_w=peak,
        motor_peak_w=peak, mpc_terminal_weight=2_000_000.0)
    b=run_definition('realistic_ool',cfg); r=run_definition('robust_mpc',cfg)
    rows.append({'peak_kw':peak/1000.0,'battery_capacity_kwh':150.0,
        'baseline_fuel_l':b['fuel_l'],'mpc_fuel_l':r['fuel_l'],
        'saving_pct':(b['fuel_l']-r['fuel_l'])/b['fuel_l']*100.0,
        'valid':r['valid'],'soc_error':r['soc_error'],
        'max_shortage_w':r['max_shortage_w']})
out=ROOT/'results/electrical_power_recheck.json'
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
