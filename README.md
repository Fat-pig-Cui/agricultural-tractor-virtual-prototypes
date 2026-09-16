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
submission manuscripts:

- the two English LaTeX sources and compiled PDFs;
- current manuscript figures;
- source code under code/;
- scripts used for the reported experiments and figures;
- declared paper-1 parameter and assumption records;
- result JSON files used to support the current conclusions.

Historical draft material and diagnostics excluded from the manuscripts,
including invalid terminal-SOC fuel figures, are not part of this release.

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

The paper-2 workflow includes the 20-path causal benchmark and the
horizon-preview mechanism map, so it can take several minutes. It writes
outputs under results/ and figures under papers/figures/.

To compile the supplied manuscript sources, install a TeX distribution with
XeLaTeX and run:

~~~bash
./build_manuscripts.sh
~~~

## Interpretation boundaries

Paper 1 meets its stated virtual-model numerical screen under the declared
filtered-gate protocol: the 20-seed hybrid result has a 9.236 mm full-run RMSE
and a 0.022 mm mean 1800 s hold drop. This is not a claim that every point in
the commanded 200 mm initial motion lies within +/-10 mm, nor a physical-hitch
performance result.

Paper 2 separates strictly causal controller statistics from an idealized
offline diagnostic. The only raw value above 20% is 21.611% for a deliberately
steep virtual low-load map, complete future knowledge, and a +/-0.01
task-terminal SOC band. Its terminal-energy-normalized value is 19.828%.
It is not an online MPC result, a general controller benefit, or a tractor
fuel-economy estimate.

## Directory map

| Path | Contents |
|---|---|
| code/ | Virtual-prototype models and controllers |
| tools/ | Reproduction, plotting, traceability, and release-verification scripts |
| results/ | Current reported experiment outputs |
| papers/figures/ | English manuscript figures |
| papers/reproducibility/ | Paper-1 parameter manifest and assumption register |
| MDPI_template_ACS/ | English LaTeX sources, PDFs, and required MDPI class files |

## Citation and archival DOI

Use CITATION.cff when citing this software archive. The public repository is
https://github.com/Fat-pig-Cui/agricultural-tractor-virtual-prototypes. The
immutable Zenodo archival release for GitHub v1.0.1 is available at
https://doi.org/10.5281/zenodo.22754510. The manuscript data-availability
statements cite both the repository and this version DOI.

## Authors

Chenyu Cui; Zhenhua Zhu; Lihan Wang; Zaiwang Lu; Yucheng Zhang.

Correspondence: zhangyucheng@ict.ac.cn
