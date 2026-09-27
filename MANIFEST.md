# Release Manifest

This table maps release files to the current manuscript evidence.

| Paper | Evidence | Release files |
|---|---|---|
| Paper 1 | Primary two-chamber V2 holdout, independent stress audit, mode-selection record, retained reduced-order checks, and parameter traceability | results/paper1_two_chamber_v2.json, results/paper1_v2_*.json, manifests/paper1_v2_parameter_manifest.csv, results/lift_*.json, results/paper1_traceability.json, and corresponding code/tools files |
| Paper 2 | Primary viability-shielded ECMS holdout, cross-cycle and map/capacity audits, frozen causal-controller comparison, horizon-preview negative control, and separately labeled full-information diagnostic | results/paper2_viability_ecms_v2.json, results/paper2_v2_*.json, results/paper2_controller_framework_frozen_benchmark.json, manifests/paper2_v2_parameter_manifest.csv, results/paper2_mpc_mechanism_map.json, results/paper2_ideal_oracle_envelope.json, and corresponding code/tools files |

The paper2_ideal_oracle_envelope.json file contains a non-causal virtual
diagnostic. Its raw 21.611% figure is not part of the causal controller
statistics, and its terminal-energy-normalized value is 19.828%.

Excluded material includes superseded drafts and invalid terminal-SOC
diagnostics. In particular, no result failing continuous SOC validation is
released as a valid fuel-saving claim.
