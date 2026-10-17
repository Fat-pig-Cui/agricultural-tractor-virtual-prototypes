"""Check the stated virtual-model equations; this is not calibration."""
from __future__ import annotations
import json
import math
from pathlib import Path
import random
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/energy_management')]
from viability_ecms_v2 import PowerSplitVirtualPlant, PowerSplitParameters, PowerSplitState


def main():
    rng=random.Random(5240)
    plant=PowerSplitVirtualPlant(PowerSplitParameters(engine_power_step_w=5000.))
    p=plant.p
    maxima=dict(planetary_speed_rpm=0., mechanical_power_w=0., battery_power_w=0.,
                electrical_balance_w=0., soc_update=0.)
    reasons={};tested=0;feasible=0
    for _ in range(1200):
        state=PowerSplitState(soc=rng.uniform(.22,.78),engine_power_w=rng.choice([0.,60000.,120000.,200000.,280000.]),
            engine_on_time_s=10.,engine_off_time_s=10.)
        speed=rng.uniform(.1,3.0);demand=rng.uniform(0.,300000.)
        for action in plant.candidate_actions(state):
            point=plant.evaluate(state,action,demand,speed);tested+=1
            if not point.feasible:
                reasons[point.reason]=reasons.get(point.reason,0)+1;continue
            feasible+=1
            ring=speed/(2*math.pi*p.wheel_radius_m)*60*p.final_drive_ratio
            engine=action.engine_power_w
            on=engine>1.
            kinematic=point.mg1_speed_rpm+p.planetary_ratio*ring-(1+p.planetary_ratio)*(action.engine_speed_rpm if on else 0)
            # Engine + mechanical MG2 input = wheel power + MG1 generated power.
            mechanical=engine+point.mg2_power_w-demand-point.mg1_power_w
            ocv=p.battery_nominal_voltage_v+80*(state.soc-p.soc_target)
            battery=ocv*point.battery_current_a-point.battery_loss_w-point.battery_bus_w
            bus=(plant._electrical_power(point.mg2_power_w,point.mg2_speed_rpm)
                 +plant._electrical_power(-point.mg1_power_w,point.mg1_speed_rpm)+p.accessory_power_w)
            soc=state.soc-point.battery_current_a*p.dt_s/(3600*(p.battery_capacity_wh/p.battery_nominal_voltage_v))
            for key,value in [('planetary_speed_rpm',kinematic),('mechanical_power_w',mechanical),
                              ('battery_power_w',battery),('electrical_balance_w',bus-point.battery_bus_w),
                              ('soc_update',soc-point.next_soc)]:maxima[key]=max(maxima[key],abs(value))
    assert feasible>1000
    assert maxima['battery_power_w']<1e-6 and maxima['mechanical_power_w']<1e-6
    assert maxima['planetary_speed_rpm']<1e-8 and maxima['soc_update']<1e-12
    signs={}
    for bus in [-180000.,0.,180000.]:
        current,loss=plant._battery_current(bus,p.soc_target)
        assert (current==0 if bus==0 else current*bus>0)
        signs[str(bus)]=dict(current_a=current,loss_w=loss)
    q=p.battery_capacity_wh/p.battery_nominal_voltage_v
    output=dict(kind='algebraic_and_numerical_verification_not_empirical_validation',
        seed=5240,sampled_states=1200,tested_actions=tested,feasible_actions=feasible,
        rejected_by_reason=reasons,max_absolute_residuals=maxima,
        battery_boundary_points=signs,derived_scales=dict(capacity_ah=q,
            bus_to_engine_ratio=p.battery_bus_limit_w/p.engine_rated_w,
            battery_rated_engine_hours=p.battery_capacity_wh/p.engine_rated_w,
            reserve_trigger_w=p.electric_reserve_fraction*p.battery_bus_limit_w,
            ideal_peak_bsfc_g_kwh=3.6e9/(p.fuel_lower_heating_value_j_kg*.42)))
    path=ROOT/'revisions/energies_major_revision/results/model_consistency_checks.json'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
