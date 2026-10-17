"""Post-review attribution on the submitted paths; never used for retuning."""
from dataclasses import replace
import json
import statistics
from run_paper2_major_revision import (OUT,FROZEN,controller_tasks,run,summary,
    ControllerFeatures)

def main():
    seeds=tuple(range(3120,3140))
    configurations=[('full','viability_ecms',FROZEN,ControllerFeatures()),
        ('without_adaptation','viability_ecms',replace(FROZEN,proportional_gain=0),ControllerFeatures()),
        ('without_phase','viability_ecms',FROZEN,ControllerFeatures(public_phase_reference=False)),
        ('without_filter','adaptive_ecms',FROZEN,ControllerFeatures(soc_corridor_filter=False)),
        ('without_reserve','viability_ecms',FROZEN,ControllerFeatures(conditional_electric_reserve=False)),
        ('revised_band_load_following','load_following',FROZEN,ControllerFeatures())]
    rows=run([task for label,mode,settings,features in configurations for task in
        controller_tasks(label,seeds,mode=mode,settings=settings,features=features)])
    submitted=json.loads((OUT/'results/submitted_reference.json').read_text())
    baseline={r['seed']:{**r,'completed':True,'strict_valid':abs(r['soc_error'])<=1e-4}
        for r in submitted['holdout']['load_following']['rows']}
    arms={label:dict(rows=[r for r in rows if r['label']==label],
        summary=summary([r for r in rows if r['label']==label],baseline))
        for label,*_ in configurations}
    data=dict(purpose='Post-review attribution on submitted paths, no retuning; independent confirmation is separately reported',
        baseline='Exact submitted load-following records, internal band used settings tolerance 0.001; evaluated here at 1e-4.',
        seeds=seeds,arms=arms)
    (OUT/'results/submitted_path_ablation.json').write_text(json.dumps(data,indent=2))
    names={'full':'Submitted full adaptive','without_adaptation':'Without adaptation','without_phase':'Without phase','without_filter':'Without SOC filter','without_reserve':'Without reserve'}
    lines=[]
    for label,name in names.items():
        s=arms[label]['summary'];saving='--' if s['mean_saving_pct'] is None else f"{s['mean_saving_pct']:.3f}"
        lines.append(f"{name} & {s['paired_valid_count']}/20 & {saving} & {s['max_abs_soc_error']:.3g} & {s['mean_shield_activations']:.1f} \\\\")
    (OUT/'submitted_ablation_table.tex').write_text('\n'.join(lines)+'\n'+r'\bottomrule'+'\n')
    print({k:v['summary'] for k,v in arms.items()})

if __name__=='__main__':main()
