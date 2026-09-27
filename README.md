# Reproducibility Archive for Two Agricultural-Tractor Virtual-Prototype Studies

This repository contains the source code, declared virtual-model inputs,
reproduction scripts, manuscript figures, result JSON files, and English
submission manuscripts for two theoretical simulation studies:

1. Paper 1: A Dual-Mode Virtual Prototype for Long-Term Position Holding in an
   Electrohydraulic Tractor Hitch: A Parametric Stress-Test Study.
2. Paper 2: Strictly Causal Energy-Management Benchmarking for a Hybrid
   Agricultural Tractor: Map Sensitivity and Controller Feasibility.

Both studies are parameterized virtual-prototype investigations. Neither
repository nor manuscript reports field, vehicle, bench, or component-map
measurements. The declared maps, constraints, and parameters are model inputs,
not a calibrated physical platform.

## Release scope

The archive intentionally includes only evidence supporting the current
Machines and Energies submission manuscripts:

- the two English LaTeX sources and compiled PDFs;
- current manuscript figures;
- source code under code/;
- scripts used for the reported experiments and figures;
- declared paper-1 parameter and assumption records;
- result JSON files used to support the current conclusions, including the
  paper-1 two-chamber V2 holdout and controller-interface audits, and the
  paper-2 viability-shielded ECMS, cross-cycle, map/capacity, and frozen
  controller-comparison evidence.

Obsolete bulk parameter screens and historical draft artifacts are not part of
this release. The explicitly declared oracle diagnostic remains included
because the Energies manuscript reports its valid and rejected boundaries.

## Reproducing the reported results

The archive requires Python 3.9 or later and was release-checked under Python
3.9 and Python 3.13. Create an isolated environment and install the Python
dependencies:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

Run the paper-specific workflows from the repository root:

~~~bash
./reproduce_paper1.sh
./reproduce_paper2.sh
python3 tools/verify_release.py
~~~

The workflows include the primary V2 experiments as well as the retained
legacy and negative-control audits, so they can take several minutes. They
write outputs under results/ and figures under papers/figures/.

Figure 3 of the Energies manuscript is generated from
`paper2_controller_framework_frozen_benchmark.json`, the complete frozen
benchmark used by the manuscript. The similarly named non-frozen benchmark is
retained as a later exploratory state and is not used to redraw that figure.

To compile the supplied manuscript sources, install a TeX distribution with
PDFLaTeX and run:

~~~bash
./build_manuscripts.sh
~~~

## Interpretation boundaries

Paper 1 meets its stated V2 virtual-model screen on 20/20 frozen 1800 s paths.
The observer-based hybrid controller has a 1.85 mm mean hold drop, a 2.10 mm
worst hold drop, and an 8.90 mm worst post-transition error. Five-times
leakage, doubled sensor noise, and half accumulator flow remain within the
declared screen, while a +2 mm position bias exceeds it and is retained as an
interface boundary. These are theoretical design-screening results, not
physical-hitch performance claims.

Paper 2 separates strictly causal controller statistics from an idealized
offline diagnostic. The viability-shielded adaptive ECMS is strictly valid on
20/20 frozen paths and has a 5.676% mean terminal-energy-normalized saving
(95% CI 5.122%--6.230%). The only raw value above 20% is 21.611% for a
deliberately steep virtual low-load map, complete future knowledge, and a
+/-0.01 task-terminal SOC band; its terminal-energy-normalized value is
19.828%. The latter is not an online result or a tractor fuel-economy estimate.

## Directory map

| Path | Contents |
|---|---|
| code/ | Virtual-prototype models and controllers |
| tools/ | Reproduction, plotting, traceability, and release-verification scripts |
| results/ | Current reported experiment outputs |
| papers/figures/ | English manuscript figures |
| papers/reproducibility/ | Paper-1 parameter manifest and assumption register |
| manifests/ | Frozen V2 parameter manifests exported from the executable defaults |
| MDPI_template_ACS/ | English LaTeX sources, PDFs, and required MDPI class files |

## Citation and archival DOI

Use CITATION.cff when citing a released software version. The public repository
is https://github.com/Fat-pig-Cui/agricultural-tractor-virtual-prototypes. The
Zenodo concept DOI is https://doi.org/10.5281/zenodo.22754509 and resolves to
the latest public archival version. Version-specific DOIs are retained in the
release notes; the manuscript data-availability statements cite the repository
and the concept DOI.

Version 1.0.5 is the GitHub release source for the current manuscript sources
and result files. Zenodo assigns an immutable version DOI after ingesting this
release; the manuscripts cite the stable concept DOI.

## Authors

Chenyu Cui; Peng Wang; Yucheng Zhang.

Correspondence: zhangyucheng@ict.ac.cn
