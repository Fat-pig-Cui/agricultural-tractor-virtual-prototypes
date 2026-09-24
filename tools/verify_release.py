"""Perform non-destructive release-integrity checks for the Zenodo archive."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "README.md",
    "CITATION.cff",
    ".zenodo.json",
    "LICENSE.md",
    "requirements.txt",
    "MDPI_template_ACS/paper1_hitch_control_machines.tex",
    "MDPI_template_ACS/paper1_hitch_control_machines.pdf",
    "MDPI_template_ACS/paper2_energy_management_energies.tex",
    "MDPI_template_ACS/paper2_energy_management_energies.pdf",
    "results/paper1_statistics_20seeds.json",
    "results/lift_steady_accuracy_scan.json",
    "results/lift_fine_trim_scan.json",
    "results/lift_combined_stress.json",
    "results/paper1_measurement_observer_audit.json",
    "results/paper2_map_sensitivity_grid.json",
    "results/paper2_soc_tolerance_scan.json",
    "results/paper2_crosscycle_strict_scan.json",
    "results/paper2_high_variability_power_boundary.json",
    "results/paper2_store_forecast_sensitivity.json",
)


def load_result(name: str) -> dict[str, object]:
    return json.loads((ROOT / "results" / name).read_text(encoding="utf-8"))


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        raise RuntimeError("missing release files: " + ", ".join(missing))

    zenodo_metadata = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    creator_names = [creator.get("name") for creator in zenodo_metadata.get("creators", [])]
    if creator_names != ["Cui, Chenyu", "Wang, Peng", "Zhang, Yucheng"]:
        raise RuntimeError("Zenodo creator metadata does not match the current author roster")

    traceability = load_result("paper1_traceability.json")
    validation = traceability.get("validation")
    if not isinstance(validation, dict) or not all(validation.values()):
        raise RuntimeError("paper-1 traceability validation did not pass")

    paper1_statistics = load_result("paper1_statistics_20seeds.json")
    hybrid = paper1_statistics.get("controllers", {}).get("hybrid")
    if not isinstance(hybrid, dict) or hybrid.get("hold_trigger_rate") != 1.0:
        raise RuntimeError("paper-1 hybrid hold-entry result is incomplete")

    measurement_audit = load_result("paper1_measurement_observer_audit.json")
    audit_checks = measurement_audit.get("acceptance_checks")
    if not isinstance(audit_checks, dict) or not all(audit_checks.values()):
        raise RuntimeError("paper-1 measurement-interface audit did not pass")

    sensitivity = load_result("paper2_store_forecast_sensitivity.json")
    if len(sensitivity.get("seeds", [])) != 12:
        raise RuntimeError("paper-2 storage/forecast sensitivity seed count is incomplete")
    for section in ("battery_capacity_sensitivity", "forecast_residual_gain_sensitivity"):
        if not isinstance(sensitivity.get(section), dict):
            raise RuntimeError(f"paper-2 sensitivity is missing {section}")

    for name in (
        "paper2_mpc_mechanism_map.json",
        "paper2_ideal_oracle_envelope.json",
    ):
        checks = load_result(name).get("acceptance_checks")
        if not isinstance(checks, dict) or not all(checks.values()):
            raise RuntimeError(f"acceptance checks failed in {name}")

    removed_names = ("Zhuo Hao", "Yang Yi", "Qingyang Li", "Lihan Wang",
                     "Zaiwang Lu", "Zhenhua Zhu")
    for manuscript in (
        ROOT / "MDPI_template_ACS/paper1_hitch_control_machines.tex",
        ROOT / "MDPI_template_ACS/paper2_energy_management_energies.tex",
    ):
        text = manuscript.read_text(encoding="utf-8")
        residual = [name for name in removed_names if name in text]
        if residual:
            raise RuntimeError(f"removed authors remain in {manuscript.name}: {residual}")

    print("release verification passed")


if __name__ == "__main__":
    main()
