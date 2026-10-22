# Paper 1: Current virtual model

`hydraulic_v2.py` and `lift_v2_experiment.py` implement the two-chamber hydraulic plant, mechanical object, observer, and holding supervisor. `lift_reserve_supply.py` implements the main-supply availability extension and boundary-resource accounting. See `manuscripts/paper1/` for the current manuscript and declared scope.

The public checkout does not include experiment outputs. `tools/run_paper1_supply_retuning.py` recomputes resource-oriented budget selection and independent validation; `tools/run_paper1_supply_validation.py` generates the supply and storage on/off comparison. Main-valve resource and storage-outlet work are defined boundary metrics, not measured whole-vehicle energy.

Use the isolated reproduction runners in the root README. Do not run legacy-path research scripts directly in the public snapshot. Parameters are declared theoretical inputs with no hardware calibration data.
