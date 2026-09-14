# Release Manifest

This table maps release files to the current manuscript evidence.

| Paper | Evidence | Release files |
|---|---|---|
| Paper 1 | 20-seed tracking/holding statistics, hold-gate and lock-leakage checks, load-step ablation, assumption-range and leakage-step stress tests, temperature-load envelope, and parameter traceability | results/lift_*.json, results/paper1_traceability.json, papers/reproducibility/, tools/run_lift_*.py, tools/run_paper1_statistics.py, tools/export_paper1_traceability.py |
| Paper 2 | Strict causal controller benchmark, predeclared horizon-preview mechanism map, and separately labeled full-information diagnostic | results/paper2_controller_framework_benchmark.json, results/paper2_mpc_mechanism_map.json, results/paper2_ideal_oracle_envelope.json, and corresponding tools/run_* and tools/plot_* files |

The paper2_ideal_oracle_envelope.json file contains a non-causal virtual
diagnostic. Its raw 21.611% figure is not part of the causal controller
statistics, and its terminal-energy-normalized value is 19.828%.

Excluded material includes superseded drafts and invalid terminal-SOC
diagnostics. In particular, no result failing continuous SOC validation is
released as a valid fuel-saving claim.
