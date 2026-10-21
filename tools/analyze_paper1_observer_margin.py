"""Exact linear position-filter poles, DC bias gain and frozen-input variance."""
from pathlib import Path
import hashlib,json
import numpy as np
from scipy.linalg import solve_discrete_lyapunov
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'revisions/machines_major_revision/results/margin_selection'
h=.01;alpha=.08;beta=.0005
F=np.array([[1-alpha,h],[-beta/h,1.]])
B=np.array([[alpha],[beta/h]])
P=solve_discrete_lyapunov(F,B@B.T)
dc=np.linalg.solve(np.eye(2)-F,B)
values=np.linalg.eigvals(F)
result=dict(h_s=h,alpha=alpha,beta=beta,F=F.tolist(),B=B.tolist(),poles=values.tolist(),
    spectral_radius=float(max(abs(values))),constant_measurement_gain=dc.ravel().tolist(),
    unit_noise_covariance=P.tolist(),covariance_residual_max_abs=float(np.max(np.abs(P-F@P@F.T-B@B.T))),
    frozen_input_position_noise_std_ratio=float(np.sqrt(P[0,0])),
    scope='Exact recursion for the implemented position filter. Constant-input DC response and iid measurement-noise component only; not the covariance or stability of the closed hydraulic loop. No finite Gaussian sample bound follows.',
    source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'code/lift_control/hydraulic_v2.py']})
assert result['spectral_radius']<1 and abs(dc[0,0]-1)<1e-12 and abs(dc[1,0])<1e-12
assert result['covariance_residual_max_abs']<1e-12
p=OUT/'observer_filter_analysis.json'
if p.exists():assert json.loads(p.read_text())==result
else:p.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
