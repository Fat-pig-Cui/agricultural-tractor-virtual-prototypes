"""Generate vector figures and numerical tables directly from revision JSON."""
from pathlib import Path
import sys,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'revisions/machines_major_revision'
RESULT=OUT/'results';FIG=OUT/'figures'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':13,'axes.spines.top':False,'axes.spines.right':False,'savefig.bbox':'tight'})
COL=['#2166ac','#c55a11','#449568','#9a4a9b']
def load(n):return json.loads((RESULT/(n+'.json')).read_text())
def save(fig,name):
    fig.savefig(FIG/(name+'.pdf'));fig.savefig(FIG/(name+'.png'),dpi=220);plt.close(fig)
def table(name,caption,label,heads,rows,widths=None):
    spec='@{}'+('>{\\raggedright\\arraybackslash}p{.25\\linewidth}'+'>{\\centering\\arraybackslash}X'*(len(heads)-1) if widths is None else widths)+'@{}'
    text='\\begin{table}[H]\n\\centering\\small\n\\caption{'+caption+'}\\label{'+label+'}\n\\begin{tabularx}{\\linewidth}{'+spec+'}\n\\toprule\n'+' & '.join(heads)+r' \\'+'\n\\midrule\n'
    text+='\n'.join(' & '.join(str(x) for x in row)+r' \\' for row in rows)
    text+='\n\\bottomrule\n\\end{tabularx}\n\\end{table}\n'
    (OUT/(name+'.tex')).write_text(text)
def main():
    FIG.mkdir(exist_ok=True);s=load('summary');orig=load('submitted_statistics')
    names=['pid_lock','smc_lock','pid_accumulator','observer_hybrid'];labels=['PID--lock','SMC--lock','PID--accumulator','Observer hybrid']
    rows=[]
    for k,l in zip(names,labels):
        v=orig[k];a=v['hold_drop_mm'];rows.append([l,f"{v['passed']}/{v['n']}",f"{a['mean']:.2f}$\\pm${a['sd']:.2f}",f"{a['ci95_low']:.2f}--{a['ci95_high']:.2f}",f"{v['post_transition_max_abs_error_mm']['max']:.2f}"])
    table('comparison_table','Frozen 20-path V2 comparison with between-seed sample SD and two-sided Student-t 95\\% interval for mean hold drop.','tab:comparison',
        ['Controller','Pass','Drop mean$\\pm$SD (mm)','Mean-drop 95\\% CI (mm)','Worst error (mm)'],rows)
    # Observer table, six crossed arms.
    rows=[]
    for c,lab in [('observer_hybrid','Hybrid'),('pid_accumulator','PID--acc.')]:
        for o,ol in [('shared','Shared observer'),('fixed_load','Fixed load'),('raw','Raw interface')]:
            v=s[f'observer_{c}_{o}'];drop=v['hold_drop_mm']
            rows.append([lab+': '+ol,f"{v['entered']}/{v['n']}",f"{v['passed']}/{v['n']}",f"{drop['mean']:.2f}" if drop else '--',f"{v['post_transition_max_abs_error_mm']['max']:.2f}",f"{v['accumulator_oil_used_ml']['mean']:.1f}"])
    table('observer_table','Crossed observer-interface removal tests on seeds 4300--4309. A dash denotes no hold entry; failed paths remain in maximum-error statistics.','tab:observer',
        ['Control and interface','Entry','Pass','Mean drop (mm)','Worst error (mm)','Oil (mL)'],rows)
    rows=[]
    for n in [0,2,4,8,12,16]:
        v=s[f'dwell_{n}'];rows.append([str(n),f"{v['passed']}/5",f"{v['mode_switches']['mean']:.1f}",f"{v['hold_drop_mm']['mean']:.3f}",f"{v['accumulator_oil_used_ml']['mean']:.2f}"])
    table('dwell_table','Frozen hybrid dwell sensitivity, five paths per row. All other thresholds and controller settings remain unchanged.','tab:dwell',
        ['Dwell (s)','Pass','Mean switches','Mean drop (mm)','Mean oil (mL)'],rows)
    # Refined trajectories align at controller sample endpoints.
    ref=load('integration_10')['rows'];coarse=load('integration_1')['rows'];errors=[]
    for a,b in zip(coarse,ref):
        assert a['seed']==b['seed'];x=np.array([[v['p_a_mpa'],v['p_b_mpa']] for v in a['trace']]);y=np.array([[v['p_a_mpa'],v['p_b_mpa']] for v in b['trace']]);diff=x-y
        errors.append(dict(seed=a['seed'],pressure_rmse_mpa=float(np.sqrt(np.mean(diff**2))),pressure_max_difference_mpa=float(np.max(np.abs(diff))),hold_drop_difference_mm=a['hold_drop_mm']-b['hold_drop_mm']))
    (RESULT/'integration_discrepancy.json').write_text(json.dumps(errors,indent=2))
    rows=[]
    for n,h in [(1,10),(2,5),(4,2.5),(10,1)]:
        v=s[f'integration_{n}'];rows.append([str(h),f"{v['passed']}/5",f"{v['hold_drop_mm']['mean']:.3f}",f"{v['post_transition_max_abs_error_mm']['max']:.3f}",f"{v['peak_pressure_mpa']['max']:.3f}"])
    table('integration_table','Plant integration refinement at a fixed 10 ms controller and measurement period with identical noise samples.','tab:integration',
        ['Plant step (ms)','Pass','Mean drop (mm)','Worst error (mm)','Peak pressure (MPa)'],rows)
    rows=[]
    for key,label in [('mass_kg','Mass'),('viscous_n_s_m','Damping'),('stiffness_n_m','Stiffness')]:
        for scale in [.7,1.3]:
            v=s[f'mechanical_{key}_{scale}'];rows.append([label+f' $\\times${scale}',f"{v['passed']}/5",f"{v['hold_drop_mm']['max']:.2f}",f"{v['post_transition_max_abs_error_mm']['max']:.2f}",f"{v['accumulator_oil_used_ml']['mean']:.1f}"])
    table('mechanical_table','New V2 one-at-a-time mechanical mismatch tests. The observer and control coefficients remain nominal.','tab:mechanical',
        ['Changed plant input','Pass','Worst drop (mm)','Worst error (mm)','Mean oil (mL)'],rows)
    rows=[]
    for n in [1,2,4,10,20]:
        v=s[f'pressure_noise_{n}'];rows.append([f'{.05*n:.2f}',f"{v['passed']}/5",f"{v['post_transition_max_abs_error_mm']['max']:.2f}",f"{v['mode_switches']['mean']:.1f}",f"{v['accumulator_oil_used_ml']['mean']:.1f}",f"{v['minimum_accumulator_pressure_mpa']['min']:.2f}"])
    table('noise_table','V2 pressure-only noise sweep with no external prefilter. Position-noise SD remains 1.5 mm; the internal observer is retained.','tab:noise',
        ['Pressure SD (MPa)','Pass','Worst error (mm)','Switches','Oil (mL)','Min. $p_g$ (MPa)'],rows)
    # Architecture: centerlines never pass through unrelated boxes.
    fig,ax=plt.subplots(figsize=(9,5.1));ax.set_xlim(0,10);ax.set_ylim(0,6);ax.axis('off')
    boxes=[(0.15,4.5,2.5,.9,'Position and pressure\nmeasurements'),(3.6,4.5,2.7,.9,'Sampled interface\n10 ms'),(7.0,4.5,2.7,.9,'Shared observer\nposition, rate, load'),(.15,2.45,2.5,.95,'Two-chamber plant\nspool and\naccumulator'),(3.6,2.45,2.7,.95,'Reference and\ntracking law\npressure command'),(7,2.45,2.7,.95,'Hold supervisor\nPID / SMC / hybrid'),(.15,.45,3.9,.9,'Revision tests\nintegration, noise\nand mismatch'),(5.25,.45,4.45,.9,'Interface removal tests\nfixed load / raw sensing\nno retuning')]
    for x,y,w,h,label in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.05',fc='#eef4fa',ec='#34495e'));ax.text(x+w/2,y+h/2,label,ha='center',va='center',fontsize=11.5)
    for a,b in [((2.65,4.95),(3.6,4.95)),((6.3,4.95),(7,4.95)),((8.35,4.5),(8.35,3.4)),((7,2.92),(6.3,2.92)),((3.6,2.92),(2.65,2.92)),((1.4,3.4),(1.4,4.5)),((2.1,1.35),(2.1,2.45)),((7.4,1.35),(8.35,2.45))]:
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=13,color='#34495e',lw=1.3))
    save(fig,'revision_architecture')
    fig,axes=plt.subplots(1,2,figsize=(9,3.8),layout='constrained');x=np.arange(4)
    for ax,metric,ylabel in [(axes[0],'hold_drop_mm','Hold drop (mm)'),(axes[1],'post_transition_max_abs_error_mm','Max. error after 8 s (mm)')]:
        vals=[orig[k][metric]['mean'] for k in names];errs=[orig[k][metric]['sd'] for k in names]
        ax.bar(x,vals,yerr=errs,capsize=3,color=COL);ax.scatter(x,[orig[k][metric]['max'] for k in names],marker='D',s=26,c='black',label='Worst seed',zorder=4)
        ax.axhline(10,color='#b22222',ls='--',lw=1);ax.set_xticks(x,['PID\nlock','SMC\nlock','PID\naccumulator','Observer\nhybrid']);ax.set_ylabel(ylabel);ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False);save(fig,'revision_comparison')
    a=load('trajectory_nominal')['rows'][0]['trace'];b=load('trajectory_pid')['rows'][0]['trace']
    fig,axes=plt.subplots(3,1,figsize=(8.4,7),layout='constrained',sharex=True)
    for tr,lab,col in [(a,'Hybrid',COL[0]),(b,'PID-accumulator',COL[1])]:
        t=np.array([v['t_s'] for v in tr]);mask=(t>=55)&(t<=85)
        for ax,key in zip(axes,['error_mm','p_a_mpa','p_b_mpa']):ax.plot(t[mask],[v[key] for v,m in zip(tr,mask) if m],label=lab,c=col,lw=1)
    for ax,y in zip(axes,['Position error (mm)','Chamber A (MPa)','Chamber B (MPa)']):ax.set_ylabel(y);ax.axvline(60,c='gray',ls='--',lw=.8)
    axes[0].legend(frameon=False,ncol=2);axes[-1].set_xlabel('Time (s)');save(fig,'revision_load_step')
    fig,axes=plt.subplots(1,2,figsize=(9,3.7),layout='constrained');d=np.array([0,2,4,8,12,16])
    axes[0].plot(d,[s[f'dwell_{n}']['mode_switches']['mean'] for n in d],'-o',c=COL[0],label='Hybrid')
    axes[0].axhline(s['pid_accumulator_matched_dwell']['mode_switches']['mean'],c=COL[1],ls='--',label='PID + 8 s latch')
    axes[0].set(xlabel='Hybrid dwell (s)',ylabel='Mean mode changes');axes[0].legend(frameon=False,fontsize=12)
    axes[1].plot(d,[s[f'dwell_{n}']['hold_drop_mm']['mean'] for n in d],'-o',c=COL[0]);axes[1].set(xlabel='Hybrid dwell (s)',ylabel='Mean hold drop (mm)',ylim=(0,3));save(fig,'revision_dwell')
    fig,axes=plt.subplots(2,1,figsize=(8.5,5.8),layout='constrained')
    for n,h in [(1,10),(2,5),(4,2.5),(10,1)]:
        v=s[f'integration_{n}'];axes[0].errorbar(h,v['hold_drop_mm']['mean'],yerr=v['hold_drop_mm']['sd'],fmt='o',capsize=4,c=COL[0])
    axes[0].set(xlabel='Plant integration step (ms)',ylabel='Hold drop mean and SD (mm)')
    r=ref[0]['trace'];c=coarse[0]['trace'];ts=np.array([v['t_s'] for v in r]);mask=(ts>=59.8)&(ts<=61)
    for tr,lab,col in [(c,'10 ms',COL[0]),(r,'1 ms',COL[1])]:axes[1].plot(ts[mask],[v['p_a_mpa'] for v,m in zip(tr,mask) if m],label=lab,c=col)
    axes[1].set(xlabel='Time (s), seed 4300',ylabel='Chamber A pressure (MPa)');axes[1].legend(frameon=False);save(fig,'revision_integration')
    fig,axes=plt.subplots(2,1,figsize=(8.5,5.6),layout='constrained',sharex=True)
    for n,lab,col in [(1,'Nominal sensors',COL[0]),(2,'Both sensor SDs doubled',COL[1]),(20,'Pressure SD = 1 MPa',COL[3])]:
        tr=load('both_noise_2' if n==2 else f'pressure_noise_{n}')['rows'][0]['trace'];tt=[v['t_s'] for v in tr]
        for ax,key in zip(axes,['error_mm','p_acc_mpa']):ax.plot(tt,[v[key] for v in tr],label=lab,c=col,lw=.75)
    axes[0].set_ylabel('Position error (mm)');axes[1].set(ylabel='Accumulator pressure (MPa)',xlabel='Time (s)');axes[0].legend(frameon=False,fontsize=12,ncol=2);save(fig,'revision_noise')
    original_noise=load('original_noise_diagnostics')
    fig,axes=plt.subplots(3,1,figsize=(8.5,6.8),layout='constrained',sharex=True)
    for tr,lab,col in [(original_noise['nominal_seed4160']['trace'],'Nominal, seed 4160',COL[0]),(original_noise['joint_rows'][0]['trace'],'Both SDs doubled, seed 4160',COL[1])]:
        mask=[v['t_s']>=8 for v in tr];tt=[v['t_s'] for v,m in zip(tr,mask) if m]
        for ax,key in zip(axes,['error_mm','p_acc_mpa','accumulator_valve']):ax.plot(tt,[v[key] for v,m in zip(tr,mask) if m],label=lab,c=col,lw=.8)
    axes[0].set_ylabel('Position error\n(mm)');axes[1].set_ylabel('Accumulator pressure\n(MPa)');axes[2].set(ylabel='Support command',xlabel='Time (s)');axes[0].legend(frameon=False,fontsize=12,ncol=2)
    fig.set_constrained_layout_pads(h_pad=.10,hspace=.08)
    save(fig,'revision_original_noise')
    # Local frozen-volume spectral and discretization consistency checks.
    A=.012;m=1200;c=2200;k=18000;beta=2e8;C=5e-14;H=1/(.004+A*.35)+1/(.004+A*(.85-.35))
    M=np.array([[0,1,0],[-k/m,-c/m,A/m],[0,-beta*H*A,-beta*H*C]])
    eig=np.linalg.eigvals(M)
    (RESULT/'boundedness_check.json').write_text(json.dumps(dict(H=H,eigenvalues=[[v.real,v.imag] for v in eig],all_negative_real=bool(np.all(eig.real<0)),scope='Frozen volumes only; not a nonlinear switched stability proof'),indent=2))
    print('assets complete; pressure discrepancy',errors)
if __name__=='__main__':main()
