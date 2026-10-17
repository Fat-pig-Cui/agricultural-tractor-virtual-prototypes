"""Replay mismatched plants with frozen nominal controller/observer inputs."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import json
from run_paper1_major_revision import protocol,job,summarize,ROOT
OUT=ROOT/'revisions/machines_major_revision/results'
def main():
    tasks=[a for a in protocol() if a[0].startswith('mechanical_')]
    (OUT/'mechanical_protocol.json').write_text(json.dumps(dict(tasks=tasks,controller='All controller and observer plant coefficients remain nominal; only true plant is altered'),indent=2))
    groups={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for name,row in pool.map(job,tasks):groups.setdefault(name,[]).append(row)
    summary=json.loads((OUT/'summary.json').read_text())
    for name,rows in groups.items():
        summary[name]=summarize(rows)
        (OUT/(name+'.json')).write_text(json.dumps(dict(summary=summary[name],rows=rows),indent=2))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({n:v for n,v in summary.items() if n.startswith('mechanical_')},indent=2))
if __name__=='__main__':main()
