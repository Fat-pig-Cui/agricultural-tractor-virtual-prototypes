"""Publication-size vector figures for the independent revision experiments."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'revisions/energies_major_revision'
sys.path[:0]=[str(ROOT/'code'),str(ROOT/'code/energy_management')]
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch,FancyBboxPatch
import numpy as np
from os_ecvt_model import LiteratureBSFCMap
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':12,
    'axes.labelsize':12,'xtick.labelsize':11,'ytick.labelsize':11,'legend.fontsize':11,
    'pdf.fonttype':42,'ps.fonttype':42})
FIGS=OUT/'figures';FIGS.mkdir(exist_ok=True)


def save(fig,name):
    fig.savefig(FIGS/(name+'.pdf'),bbox_inches='tight',facecolor='white')
    fig.savefig(FIGS/(name+'.png'),dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)


def architecture():
    fig,ax=plt.subplots(figsize=(7.2,4.0));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    def box(x,y,w,h,text,color):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.006',
            fc=color,ec='#25415a',lw=.8))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=11,linespacing=1.25)
    def arrow(start,end):ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=10,lw=1,color='#25415a'))
    box(.02,.69,.28,.24,'Current demand;\nspeed; SOC;\nengine state; time','#e5eef5')
    box(.36,.69,.28,.24,'Hard constraints;\nfeasible actions;\nconditional reserve','#e5eef5')
    box(.70,.69,.28,.24,'ECMS proposal:\nequivalent fuel;\npublic SOC target','#e7f0e4')
    box(.70,.22,.28,.28,'Soft SOC safeguard:\ntest successor SOC;\nshrinking corridor','#f7eee0')
    box(.36,.22,.28,.28,'Nonempty: min cost\nEmpty: nearest SOC\nCost breaks ties','#f7eee0')
    box(.02,.22,.28,.28,'Apply action;\nupdate plant;\nlog SOC, corrections','#e5eef5')
    arrow((.30,.81),(.36,.81));arrow((.64,.81),(.70,.81))
    arrow((.84,.69),(.84,.50));arrow((.70,.36),(.64,.36))
    arrow((.36,.36),(.30,.36));arrow((.16,.50),(.16,.69))
    ax.text(.17,.585,'State feedback',fontsize=11,ha='left')
    ax.text(.50,.09,'Hard-feasible set empty: record failure and stop the virtual task',ha='center',fontsize=11,color='#8f3434')
    save(fig,'revision_architecture')


def model_maps():
    engine=LiteratureBSFCMap(peak=.42,rated_power_w=300000.)
    loads=np.linspace(.05,1,80)
    fig,axes=plt.subplots(1,2,figsize=(7.2,3.0),layout='constrained')
    for speed in [1200,1500,1800]:
        axes[0].plot(loads,[engine.efficiency(speed,p*300000) for p in loads],label=f'{speed} rpm')
    axes[0].axvline(.2,ls=':',color='gray');axes[0].set(xlabel='Engine power / 300 kW',ylabel='Defined virtual efficiency',title='(a) Defined engine map')
    axes[0].legend(frameon=False);axes[0].grid(alpha=.2)
    currents=np.linspace(-285,295,100)
    axes[1].plot(currents,(650*currents-.045*currents**2)/1000,color='#25415a')
    axes[1].axhline(180,ls=':',color='gray');axes[1].axhline(-180,ls=':',color='gray')
    axes[1].axvline(0,color='gray',lw=.6)
    axes[1].set(xlabel='Current (A); discharge positive',ylabel='Battery bus power (kW)',title='(b) Battery law at SOC = 0.55')
    axes[1].grid(alpha=.2);save(fig,'revision_model_maps')


def ablation():
    j=json.loads((OUT/'results/ablation_and_comparison.json').read_text());h=j['holdout']
    keys=['full','without_adaptation','without_phase','without_filter','without_reserve']
    labels=['Adapt.\n+ filter','Fixed\n+ filter','No\nphase','No\nfilter','No\nreserve']
    fig,axes=plt.subplots(1,2,figsize=(7.2,3.15),layout='constrained')
    for i,k in enumerate(keys):
        s=h[k]['summary'];value=s['mean_saving_pct']
        if value is not None:
            low,high=s['saving_95ci_pct']
            axes[0].bar(i,value,color='#4d7895',width=.63,yerr=np.array([[value-low],[high-value]]),capsize=3)
        else:axes[0].text(i,.5,'No valid\npairs',ha='center',fontsize=11)
        axes[0].text(i,10.8,f"{s['paired_valid_count']}/20",ha='center',fontsize=11)
    axes[0].set(ylim=(0,12),ylabel='Normalized fuel saving (%)',title='(a) Fuel saving: valid pairs')
    axes[0].set_xticks(range(5),labels,fontsize=11);axes[0].grid(axis='y',alpha=.2)
    axes[1].bar(range(5),[h[k]['summary']['max_abs_soc_error'] for k in keys],color='#b47a4d')
    axes[1].axhline(1e-4,color='#8f3434',ls='--',label='Strict tolerance')
    axes[1].set(yscale='log',ylim=(5e-7,2e-2),ylabel='Maximum terminal SOC error',title='(b) Terminal SOC: all paths')
    axes[1].set_xticks(range(5),labels,fontsize=11);axes[1].legend(frameon=False);axes[1].grid(axis='y',alpha=.2)
    save(fig,'revision_ablation')


def trajectories():
    h=json.loads((OUT/'results/ablation_and_comparison.json').read_text())['holdout']
    fig,axes=plt.subplots(2,1,figsize=(7.2,4.5),sharex=True,layout='constrained')
    for k,label,color in [('full','Frozen adaptive','#25415a'),('without_adaptation','Fixed factor + safeguard','#5d8d55'),
                         ('without_filter','Adaptive without safeguard','#b47a4d')]:
        r=next(r for r in h[k]['rows'] if r['seed']==5120)
        rows=r.get('trajectory_full',r.get('trajectory_30s'))
        axes[0].plot([x['time_s'] for x in rows],[x['soc'] for x in rows],label=label,color=color,lw=1.2)
        if k=='full':
            axes[0].plot([x['time_s'] for x in rows],[x['reference_soc'] for x in rows],ls=':',color='black',label='Public SOC reference')
            axes[1].plot([x['time_s'] for x in rows],[x['wheel_demand_w']/1000 for x in rows],color='gray',lw=.8,label='Demand')
            axes[1].plot([x['time_s'] for x in rows],[x['engine_power_w']/1000 for x in rows],color=color,lw=.8,label='Applied engine')
    axes[0].set(ylabel='SOC')
    axes[0].set_title('Illustrative seed 5120 (selected by identifier)',pad=46)
    axes[0].legend(ncol=2,frameon=False,fontsize=11,loc='upper center',bbox_to_anchor=(.5,1.34));axes[0].grid(alpha=.2)
    axes[1].set(xlabel='Time (s)',ylabel='Power (kW)');axes[1].legend(frameon=False,ncol=2);axes[1].grid(alpha=.2)
    save(fig,'revision_soc_trajectory')


def main():
    architecture();model_maps();ablation();trajectories()
    print('Wrote four vector figures and PNG previews')


if __name__=='__main__':main()
