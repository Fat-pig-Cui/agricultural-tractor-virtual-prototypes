#!/usr/bin/env python3
"""Validate and export the paper-1 virtual-prototype traceability record."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "papers" / "submission" / "paper1_parameter_manifest.csv"
ASSUMPTIONS = ROOT / "papers" / "submission" / "paper1_assumption_register.md"
MANUSCRIPT = ROOT / "MDPI_template_ACS" / "paper1_hitch_control_mdpi.tex"
OUTPUT = ROOT / "results" / "paper1_traceability.json"
TRACEABILITY_VERSION = "paper1-v1.0"
REQUIRED_COLUMNS = {
    "parameter_id",
    "symbol",
    "code_identifier",
    "nominal_value",
    "unit",
    "source_class",
    "source_locator",
    "model_role",
    "stress_or_coverage",
    "claim_dependency",
}
ALLOWED_SOURCE_CLASSES = {
    "numerical_setting",
    "virtual_hydraulic_input",
    "reduced_order_coefficient",
    "virtual_mechanical_input",
    "measurement_setting",
}
REMOVED_HISTORICAL_FIELDS = {
    "valve_flow_m3_s",
    "acc_pressure_gain",
    "gravity_m_s2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest() -> list[dict[str, str]]:
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("parameter manifest contains no rows")
    if set(rows[0]) != REQUIRED_COLUMNS:
        raise ValueError("parameter manifest columns do not match the required schema")
    return rows


def verify(rows: list[dict[str, str]]) -> dict[str, object]:
    sys.path.insert(0, str(ROOT / "code" / "lift_control"))
    sys.path.insert(0, str(ROOT / "code"))
    from config.parameters import LiftParameters

    parameter_values = asdict(LiftParameters())
    identifiers: set[str] = set()
    fields: set[str] = set()
    errors: list[str] = []

    for row in rows:
        parameter_id = row["parameter_id"]
        if parameter_id in identifiers:
            errors.append(f"duplicate parameter_id: {parameter_id}")
        identifiers.add(parameter_id)
        if row["source_class"] not in ALLOWED_SOURCE_CLASSES:
            errors.append(f"unknown source_class for {parameter_id}: {row['source_class']}")
        prefix = "LiftParameters."
        if not row["code_identifier"].startswith(prefix):
            errors.append(f"invalid code_identifier for {parameter_id}: {row['code_identifier']}")
            continue
        field = row["code_identifier"][len(prefix):]
        if field in fields:
            errors.append(f"duplicate LiftParameters field in manifest: {field}")
        fields.add(field)
        if field not in parameter_values:
            errors.append(f"manifest field absent from LiftParameters: {field}")
            continue
        try:
            manifest_value = float(row["nominal_value"])
        except ValueError:
            errors.append(f"non-numeric nominal_value for {parameter_id}")
            continue
        code_value = float(parameter_values[field])
        if abs(manifest_value - code_value) > max(1e-15, abs(code_value) * 1e-12):
            errors.append(
                f"value mismatch for {field}: manifest={manifest_value!r}, code={code_value!r}"
            )

    missing = sorted(set(parameter_values) - fields)
    unexpected = sorted(fields - set(parameter_values))
    if missing:
        errors.append("manifest missing LiftParameters fields: " + ", ".join(missing))
    if unexpected:
        errors.append("manifest has unexpected LiftParameters fields: " + ", ".join(unexpected))
    retained = sorted(REMOVED_HISTORICAL_FIELDS & set(parameter_values))
    if retained:
        errors.append("historical unused fields remain in LiftParameters: " + ", ".join(retained))

    if errors:
        raise ValueError("\n".join(errors))
    return {
        "lift_parameters": parameter_values,
        "source_class_counts": dict(sorted(Counter(row["source_class"] for row in rows).items())),
        "validation": {
            "all_lift_parameters_covered": True,
            "manifest_values_match_code": True,
            "historical_unused_fields_absent": True,
        },
    }


def execution_defaults() -> dict[str, object]:
    """Snapshot the non-plant settings that define the reported protocol."""
    sys.path.insert(0, str(ROOT / "code" / "lift_control"))
    sys.path.insert(0, str(ROOT / "code"))
    from controllers import AntiWindupPID, BoundaryLayerSMC, DI_SMACKernel, PressureObserver
    from experiments import ExperimentConfig
    from leakage_compensation import HybridHoldSupervisor

    supervisor = HybridHoldSupervisor()
    return {
        "experiment_config": asdict(ExperimentConfig()),
        "controller_defaults": {
            "anti_windup_pid": asdict(AntiWindupPID()),
            "boundary_layer_smc": asdict(BoundaryLayerSMC()),
            "di_smac_kernel": asdict(DI_SMACKernel()),
            "pressure_observer": asdict(PressureObserver()),
        },
        "hold_supervisor_defaults": {
            "lock_threshold": supervisor.lock_threshold,
            "accumulator_threshold": supervisor.accumulator_threshold,
            "hysteresis": supervisor.hysteresis,
            "accumulator_enabled": supervisor.accumulator_enabled,
            "initial_mode": supervisor.mode.value,
        },
        "implementation_scope": (
            "The source hashes identify the exact run_definition implementation, "
            "including its reference trajectory, hold-entry dwell, and filter literals."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate and write the traceability record")
    args = parser.parse_args()
    try:
        rows = read_manifest()
        record = verify(rows)
    except (OSError, ValueError) as exc:
        print(f"paper1 traceability check failed: {exc}", file=sys.stderr)
        return 1

    tracked_paths = [
        MANIFEST,
        ASSUMPTIONS,
        MANUSCRIPT,
        Path(__file__).resolve(),
        ROOT / "code" / "config" / "parameters.py",
        ROOT / "code" / "lift_control" / "hydraulic_model.py",
        ROOT / "code" / "lift_control" / "controllers.py",
        ROOT / "code" / "lift_control" / "experiments.py",
    ]
    record.update(
        {
            "traceability_version": TRACEABILITY_VERSION,
            "manifest_sha256": sha256(MANIFEST),
            "assumption_register_sha256": sha256(ASSUMPTIONS),
            "execution_defaults": execution_defaults(),
            "tracked_file_sha256": {
                str(path.relative_to(ROOT)): sha256(path) for path in tracked_paths
            },
        }
    )
    OUTPUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"validated {len(rows)} parameters; wrote {OUTPUT.relative_to(ROOT)}")
    if not args.check:
        print("use --check in automated reproduction workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
