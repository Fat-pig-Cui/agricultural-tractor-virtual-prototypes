"""600 s paired stochastic ablation: online-only vs offline SOC reference."""
from __future__ import annotations
import json, time
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/energy_management')]
from experiments import ExperimentConfig, run_definition
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

SEEDS=range(2026,2046)
BASE=dict(profile_name='stochastic_agri_workcycle', duration_s=600.0,
          engine_map=RealisticDieselMap(low_load_efficiency=0.22,power_width_w=90000.0),
          motor_map=RealisticMotorMap(), accessory_for_all_w=18000.0,
          mpc_terminal_weight=2000000.0, stochastic_disturbance_scale=0.25)

def main():
    out={'seeds':list(SEEDS),'disturbance_scale':0.25,'controllers':{}}
    for reference in (False, True):
        key='offline_reference' if reference else 'online_only'
        out['controllers'][key]={}
        for name in ('realistic_ool','deterministic_mpc','robust_mpc'):
            rows=[]
            for seed in SEEDS:
                t=time.perf_counter()
                r=run_definition(name,ExperimentConfig(seed=seed,
                    stochastic_offline_reference=reference,**BASE))
                row={'seed':seed,'fuel_l':float(r['fuel_l']),'valid':bool(r['valid']),
                     'soc_error':float(r['soc_error']),'max_shortage_w':float(r['max_shortage_w']),
                     'max_motor_power_violation_w':float(r['max_motor_power_violation_w']),
                     'max_mg1_power_violation_w':float(r['max_mg1_power_violation_w']),
                     'max_mg1_speed_violation_rpm':float(r['max_mg1_speed_violation_rpm']),
                     'max_mg2_speed_violation_rpm':float(r['max_mg2_speed_violation_rpm']),
                     'fallback_count':int(r['fallback_count']),
                     'runtime_s':time.perf_counter()-t}
                rows.append(row); print(key,name,seed,row['valid'],row['fuel_l'],flush=True)
            baseline=out['controllers'][key].get('realistic_ool',rows)
            out['controllers'][key][name]={'rows':rows,
              'valid_rate':float(np.mean([x['valid'] for x in rows])),
              'mean_fuel_l':float(np.mean([x['fuel_l'] for x in rows])),
              'mean_soc_error':float(np.mean([x['soc_error'] for x in rows])),
              'mean_fallback_count':float(np.mean([x['fallback_count'] for x in rows])),
              'mean_runtime_s':float(np.mean([x['runtime_s'] for x in rows]))}
    # paired savings against the same-seed OOL within each reference protocol
    for key,data in out['controllers'].items():
        b=data['realistic_ool']['rows']
        out.setdefault('paired_savings_vs_ool_pct',{})[key]={}
        for name in ('deterministic_mpc','robust_mpc'):
            c=data[name]['rows']
            vals=[(x['fuel_l']-y['fuel_l'])/x['fuel_l']*100 for x,y in zip(b,c) if x['valid'] and y['valid']]
            out['paired_savings_vs_ool_pct'][key][name]={'n_valid_pairs':len(vals),
                'mean_pct':float(np.mean(vals)) if vals else None,
                'valid_pair_rate':len(vals)/len(b)}
    path=ROOT/'results/stochastic_reference_ablation_600s.json'
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(path)
if __name__=='__main__': main()
