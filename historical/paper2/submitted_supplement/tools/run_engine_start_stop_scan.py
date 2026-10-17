"""600 s fair comparison with an auditable engine start/stop model."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / 'code'), str(ROOT / 'code/energy_management')]
from experiments import ExperimentConfig, run_definition
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

def main():
    rows=[]
    for stop_threshold in (15_000.0, 25_000.0, 35_000.0):
        cfg=ExperimentConfig(duration_s=600.0,
            profile_name='low_load_agri_workcycle', accessory_for_all_w=18_000.0,
            realistic_maps=True, engine_start_stop=True,
            engine_stop_threshold_w=stop_threshold,
            engine_restart_threshold_w=45_000.0,
            engine_minimum_on_s=5.0, engine_minimum_off_s=5.0,
            engine_start_fuel_g=1.5, mpc_terminal_weight=2_000_000.0,
            realistic_ool_minimum_engine_w=60_000.0)
        b=run_definition('realistic_ool',cfg)
        row={'stop_threshold_kw':stop_threshold/1000,
             'baseline_fuel_l':b['fuel_l'],'baseline_valid':b['valid'],
             'baseline_engine_starts':b['engine_starts']}
        for name in ('deterministic_mpc','robust_mpc'):
            r=run_definition(name,cfg)
            row[name]={'fuel_l':r['fuel_l'],'valid':r['valid'],
              'saving_pct':(b['fuel_l']-r['fuel_l'])/b['fuel_l']*100,
              'soc_error':r['soc_error'],'max_shortage_w':r['max_shortage_w'],
              'max_motor_power_violation_w':r['max_motor_power_violation_w'],
              'max_mg1_power_violation_w':r['max_mg1_power_violation_w'],
              'max_mg1_speed_violation_rpm':r['max_mg1_speed_violation_rpm'],
              'max_mg2_speed_violation_rpm':r['max_mg2_speed_violation_rpm'],
              'engine_starts':r['engine_starts']}
        rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
    out=ROOT/'results/engine_start_stop_scan.json'; out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8'); print(out)
if __name__=='__main__': main()
