from __future__ import annotations
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/lift_control')]
from experiments import ExperimentConfig, run_definition

def main():
    rows=[]
    for leak in (1.0,10.0):
        for mode in ('filtered','raw','dual'):
            for controller in ('hybrid',):
                vals=[]
                for seed in range(2026,2046):
                    r=run_definition(controller,ExperimentConfig(
                      leakage_scale=leak,lock_valve_leakage_scale=leak,
                      velocity_gate_mode=mode,filtered_velocity_gate_enabled=(mode=='filtered'),
                      duration_s=1800.0),seed=seed)
                    vals.append({'seed':seed,'hold_started':bool(r['hold_started']),
                      'hold_drop_mm':None if r['hold_drop_m'] is None else r['hold_drop_m']*1000,
                      'rmse_mm':r['rmse_m']*1000,'max_velocity_mps':r['max_velocity_mps'],
                      'hold_start_time_s':r['hold_start_time_s']})
                rows.append({'controller':controller,'leakage_scale':leak,'velocity_gate_mode':mode,
                  'hold_trigger_rate':float(np.mean([x['hold_started'] for x in vals])),
                  'mean_hold_drop_mm':float(np.mean([x['hold_drop_mm'] for x in vals if x['hold_drop_mm'] is not None])) if any(x['hold_drop_mm'] is not None for x in vals) else None,
                  'max_hold_drop_mm':float(max([x['hold_drop_mm'] for x in vals if x['hold_drop_mm'] is not None],default=0.0)),
                  'mean_rmse_mm':float(np.mean([x['rmse_mm'] for x in vals])),
                  'rows':vals})
    out=ROOT/'results/lift_dual_gate_20seeds.json'
    out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8'); print(out)
if __name__=='__main__': main()
