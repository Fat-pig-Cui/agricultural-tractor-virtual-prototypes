"""Perform non-destructive release-integrity checks for the Zenodo archive."""
from __future__ import annotations

import json
import re
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
    "manifests/paper1_v2_parameter_manifest.csv",
    "manifests/paper2_v2_parameter_manifest.csv",
    "code/lift_control/hydraulic_v2.py",
    "code/lift_control/lift_v2_experiment.py",
    "code/energy_management/viability_ecms_v2.py",
    "results/paper1_two_chamber_v2.json",
    "results/paper1_v2_independent_audit.json",
    "results/paper1_v2_mode_scan.json",
    "results/paper2_viability_ecms_v2.json",
    "results/paper2_v2_crosscycle_audit.json",
    "results/paper2_v2_map_capacity_audit.json",
    "results/paper2_controller_framework_frozen_benchmark.json",
    "papers/figures/paper1_v2_architecture.png",
    "papers/figures/paper1_v2_results.png",
    "papers/figures/paper2_v2_architecture.png",
    "papers/figures/paper2_v2_results.png",
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
    verify_current_revision()
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

    paper1_v2 = load_result("paper1_two_chamber_v2.json")
    paper1_v2_summary = paper1_v2.get("holdout", {}).get("observer_hybrid", {}).get("summary", {})
    if paper1_v2_summary.get("count") != 20 or paper1_v2_summary.get("pass_count") != 20:
        raise RuntimeError("paper-1 V2 frozen holdout is incomplete")

    paper2_v2 = load_result("paper2_viability_ecms_v2.json")
    paper2_v2_summary = paper2_v2.get("holdout", {}).get("viability_ecms", {}).get("summary", {})
    if (paper2_v2_summary.get("count") != 20
            or paper2_v2_summary.get("strict_valid_count") != 20
            or paper2_v2_summary.get("mean_energy_normalized_saving_pct", 0.0) <= 0.0):
        raise RuntimeError("paper-2 V2 frozen holdout is incomplete or non-positive")

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


def verify_current_revision():
    from materialize_release_data import process, digest
    assert process(check_only=True) == 11
    entries = []
    for line in (ROOT / 'MANIFEST.sha256').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = ROOT / name
        path.resolve().relative_to(ROOT)
        assert digest(path) == expected, name
        assert path.stat().st_size < 100_000_000, name
        entries.append(name)
    assert len(entries) == len(set(entries))
    assert not any(re.search(r'(^|/)(evidence|submission_packages|patents|qa)(/|$)|response_reviewer|Response_to_Reviewer|major_revision_message|More_info_reviewer', name) for name in entries)
    sync = json.loads((ROOT / 'manifests/local_sync_sources.json').read_text())
    assert sync['version'] == '1.1.0'
    for entry in sync['byte_identical_copies']:
        assert digest(ROOT / entry['target']) == entry['sha256'], entry['target']
    p1 = ROOT / 'revisions/machines_major_revision/results'
    protocol = json.loads((p1 / 'strengthening_protocol.json').read_text())
    strength = json.loads((p1 / 'strengthening_audit.json').read_text())
    assert len(protocol['tasks']) == 70
    for name, expected in protocol['source_sha256'].items():
        assert digest(ROOT / name) == expected, name
    from run_paper1_major_revision import summarize
    assert len(strength['groups']) == 14
    assert sum(len(g['rows']) for g in strength['groups'].values()) == 70
    for g in strength['groups'].values():
        assert [r['seed'] for r in g['rows']] == protocol['seeds']
        assert summarize(g['rows']) == g['summary']
        assert g['summary']['passed'] == 5
    p2 = ROOT / 'revisions/energies_major_revision/results'
    result = json.loads((p2 / 'ablation_and_comparison.json').read_text())
    code_path = ROOT / 'code/energy_management/viability_ecms_v2.py'
    provenance = json.loads((p2 / 'revision_provenance.json').read_text())
    assert provenance['final_code_sha256'] == digest(code_path)
    # The recorded post-run change only names full-rate logs accurately.
    # Reconstruct the original bytes; never rewrite the frozen protocol hash.
    source = code_path.read_text()
    naming = '("trajectory_full" if capture_full_trajectory else "trajectory_30s"): trajectory'
    assert source.count(naming) == 1
    import hashlib
    original_source = source.replace(naming, '"trajectory_30s": trajectory')
    assert hashlib.sha256(original_source.encode()).hexdigest() == result['protocol']['source_sha256']
    from run_paper2_major_revision import evaluate, ECMSSettings, ControllerFeatures, PARAMS
    for arm, saving in [('full', 5.950644), ('without_adaptation', 7.090609)]:
        data = result['holdout'][arm]
        summary = data['summary']
        assert summary['paired_valid_count'] == 20
        assert abs(summary['mean_saving_pct'] - saving) < 0.000001
        frozen = data['rows'][0]
        replay = evaluate((frozen['label'], frozen['seed'], data['mode'],
                           ECMSSettings(**data['settings']), ControllerFeatures(**data['features']),
                           PARAMS, 'literature', 'stochastic'))
        for key, value in frozen.items():
            if key != 'decision_timing_ms':
                assert replay[key] == value, (arm, key)
    assert 'version: 1.1.0' in (ROOT / 'CITATION.cff').read_text()
    print(f'v1.1.0 current revision and {len(entries)} release hashes verified')


if __name__ == "__main__":
    main()
