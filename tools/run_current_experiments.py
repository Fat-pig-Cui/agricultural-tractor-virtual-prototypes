"""从源码在独立工作区生成结果，公开检出不包含实验数据。"""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    'paper1-supply': [('run_paper1_supply_validation.py', []), ('run_paper1_supply_retuning.py', [])],
    'paper2': [('run_paper2_major_revision.py', []), ('run_paper2_submitted_ablation.py', [])],
    'paper2-physics': [('check_paper2_revision_physics.py', [])],
    'paper2-execution': [('check_paper2_revision_execution.py', [])],
    'paper2-ideal': [('run_paper2_ideal_oracle_envelope.py', [])],
    'smoke': [],
}


def prepare(work):
    work = Path(work).expanduser().resolve()
    assert not work.is_relative_to(ROOT), 'Use a workspace outside this checkout.'
    assert not work.exists(), 'Choose a new workspace; existing files are never overwritten.'
    work.mkdir(parents=True)
    for folder in ['code', 'tools']:
        shutil.copytree(ROOT / folder, work / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for folder in ['revisions/machines_major_revision/results',
                   'revisions/energies_major_revision/results', 'results']:
        (work / folder).mkdir(parents=True)
    return work


def smoke(work):
    """检查空工作区中的导入、计划生成和两篇论文代表性计算。"""
    program = r'''
import json, math, sys
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
import run_paper1_supply_validation as supply
import run_paper1_supply_retuning as retuning
from run_paper2_major_revision import evaluate,controller_tasks
import run_paper2_ideal_oracle_envelope
assert len(supply.plan()['tasks'])==88
assert len(retuning.plan()['development_tasks'])==54
task=next(t for t in supply.plan()['tasks'] if t['group']=='normal' and t['chain']=='observer_hybrid')
task['config']['duration_s']=12.
row=supply.run(task)['row']
assert math.isfinite(row['post_transition_rmse_mm'])
energy=evaluate(controller_tasks('full',(5120,))[0])
baseline=evaluate(controller_tasks('baseline',(5120,),mode='load_following')[0])
assert energy['completed'] and baseline['completed']
assert energy['strict_valid'] and baseline['strict_valid']
assert len(energy['trajectory_full'])==600
result=dict(paper1_short_seconds=12,paper1_rmse_mm=row['post_transition_rmse_mm'],
    paper1_supply_tasks=88,paper1_resource_development_tasks=54,paper2_seed=5120,
    paper2_samples=600,paper2_terminal_valid=True,
    paper2_fuel_l=energy['fuel_l'],paper2_baseline_fuel_l=baseline['fuel_l'],
    scope='源码短程检查；未执行全部实验，未比较历史冻结结果。')
Path('results/smoke_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
'''
    subprocess.run([sys.executable, '-c', program], cwd=work, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('experiment', choices=RUNS)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    work = args.workspace.expanduser().resolve()
    assert not work.is_relative_to(ROOT), 'Use a workspace outside this checkout.'
    prepare(work)
    if args.prepare_only:
        print(work)
        return
    if args.experiment == 'smoke':
        smoke(work)
    else:
        for name, options in RUNS[args.experiment]:
            subprocess.run([sys.executable, str(work / 'tools' / name), *options], cwd=work, check=True)
    print('Results workspace:', work)


if __name__ == '__main__':
    main()
