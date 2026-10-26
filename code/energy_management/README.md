# Paper 2: Current ECMS and power-split model

`viability_ecms_v2.py` provides the power-split virtual plant, candidate operating points, ECMS, and soft-SOC safeguard. `os_ecvt_model.py` provides the efficiency maps. The current manuscript in `manuscripts/paper2/` is the corrected author proof; the word “viability” does not constitute a recursive-feasibility proof.

The public checkout does not include experiment outputs or historical audit ledgers. The minimal runner `./reproduce_paper2.sh --workspace /tmp/paper2-workspace` executes a short seeded adaptive-ECMS/baseline comparison from the current source and writes JSON only to the external workspace. The main protocol uses a terminal-SOC tolerance of 1e-4. The model and maps remain theoretical inputs rather than calibration data.

Follow the root README and run reproduction in an isolated workspace. The models and parameters have theoretical boundaries and must not be interpreted as vehicle or component-map calibration.
