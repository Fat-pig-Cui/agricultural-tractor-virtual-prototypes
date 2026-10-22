# Paper 2: Current ECMS and power-split model

`viability_ecms_v2.py` provides the power-split virtual plant, candidate operating points, ECMS, and soft-SOC safeguard. `os_ecvt_model.py` provides the efficiency maps. The current manuscript in `manuscripts/paper2/` is the corrected author proof; the word “viability” does not constitute a recursive-feasibility proof.

The public checkout does not include experiment outputs. The main comparison, module ablations, same-safeguard fixed ECMS, map and capacity audits, and execution checks are generated from scratch by the corresponding scripts in `tools/`. The main protocol uses a terminal-SOC tolerance of 1e-4. The full-information ideal diagnostic is generated separately by `tools/run_paper2_ideal_oracle_envelope.py` and remains distinct from the causal online result.

Follow the root README and run reproduction in an isolated workspace. The models and parameters have theoretical boundaries and must not be interpreted as vehicle or component-map calibration.
