# Two Agricultural-Tractor Papers: Current Manuscripts and Minimal Reproduction Source

This repository contains only the latest versions of the two papers, their model and algorithm source, experiment-generation scripts, parameter manifests, and documentation. Frozen experiment outputs, trajectories, checkpoints, development searches, and result statistics are intentionally excluded. Old manuscripts and review correspondence are outside the working tree; existing Git history and tags are retained.

| Paper | Current stage | Manuscript | Supplement |
| :---: | :---: | :---: | :---: |
| Paper 1 / Machines | Accepted manuscript | [Manuscript PDF](manuscripts/paper1/manuscript.pdf) | [S1–S13](manuscripts/paper1/supplementary.pdf) |
| Paper 2 / Energies | Corrected author proof | [Manuscript PDF](manuscripts/paper2/manuscript.pdf) | [S1–S7](manuscripts/paper2/supplementary.pdf) |

Paper 1: Observer-Based Hybrid Position Holding for an Electrohydraulic Agricultural Hitch: A Two-Chamber Virtual-Prototype Stress Test.

Paper 2: Phase-Informed ECMS with Soft SOC Safeguarding for a Virtual Hybrid Agricultural Tractor.

The manuscript and supplement PDFs are byte-identical to the current author files. The public Paper 2 TeX source removes editorial queries and author-response comments while retaining valid TeX content and publisher proof markings. The original production files remain in the author workspace. The proof is not the final published version; publication metadata is determined by the publisher.

## Contents

| Path | Contents |
| :---: | :---: |
| `manuscripts/paper1/`, `manuscripts/paper2/` | Current English manuscripts, supplements, TeX sources, templates, and figures |
| `code/` | Hydraulic, observer, supply-extension, power-split, and ECMS models and algorithms |
| `tools/` | Experiment-generation, verification, and isolated-workspace runners |
| `parameters/` | Declared theoretical model parameter manifests; experiment settings and seeds are in the scripts and papers |
| `manifests/` | Local source mappings and file hashes |

Figures and supplementary descriptions used by the papers remain available. The original experiment data remains in the author research workspace; this checkout does not provide frozen trajectories or precomputed statistics.

## Installation and integrity check

```sh
python3 -m pip install -r requirements.txt
python3 tools/verify_release.py
```

The integrity check uses the Python standard library. Simulations require NumPy, SciPy, and Matplotlib. The manuscript and supplement sources can be compiled with PDFLaTeX using `./build_manuscripts.sh`; run it in a separate clone because it replaces local PDFs.

## Reproduce from source

Every runner requires a new workspace outside this checkout. It copies source code and creates empty output directories, then computes results from scratch without copying or downloading experiment data.

Run the short smoke test first:

```sh
python3 tools/run_current_experiments.py smoke --workspace ../tractor-smoke
```

The smoke test generates the Paper 1 protocol plans, runs a representative 12-second hydraulic calculation, and runs the complete 600-second Paper 2 controller and baseline calculation for seed 5120. It checks that the source runs in an empty workspace; it is not a full reproduction.

Main experiment runners:

```sh
./reproduce_paper1.sh --workspace ../tractor-paper1
./reproduce_paper2.sh --workspace ../tractor-paper2
```

Paper 1 recomputes the 88-path supply comparison, the 54-path resource-selection development, and the subsequent independent validation. Paper 2 recomputes development selection, the 20-path independent comparison, ablations, map and capacity audits, and attribution on the original-submission seed group. These runs can be lengthy. The scripts save outputs and resumable checkpoints in the external workspace; development and failed paths should be retained rather than selecting only the best result. `--prepare-only` only prepares the workspace.

Additional checks:

```sh
python3 tools/run_current_experiments.py paper2-physics --workspace ../tractor-physics
python3 tools/run_current_experiments.py paper2-execution --workspace ../tractor-execution
python3 tools/run_current_experiments.py paper2-ideal --workspace ../tractor-ideal
```

The approximately 20% case is generated separately by `paper2-ideal`. It uses complete future information, an ideal map, and a wider terminal-SOC band and must remain separate from the causal online protocol. The 24.087% grid value, which did not pass continuous replay, must not be presented as a valid online result. See the paper and scripts for the declared method and boundaries.

Historical path names in the source preserve compatibility with the original scientific scripts; they are created only in the external workspace. When historical reference files are absent, Paper 2 recomputes the original baseline settings and records that byte-level historical parity was not checked. The models, controllers, seeds, and experiment settings are unchanged. The repository does not claim to reconstruct every early diagnostic bit-for-bit or to redraw every paper figure automatically. Timing varies by host.

## Theoretical scope and citation

Both papers study theoretical virtual prototypes. Parameters and maps are declared model inputs; there are no vehicle, bench, or target-component calibration data. Finite numerical experiments do not establish global stability, recursive feasibility, or hardware validation.

Authors: Chenyu Cui, Peng Wang, and Yucheng Zhang. Corresponding author: Yucheng Zhang, `zhangyucheng@ict.ac.cn`.

The [Zenodo concept DOI](https://doi.org/10.5281/zenodo.22754509) identifies the research-material collection and does not replace article DOIs. Citation information is in `CITATION.cff`; the license is in `LICENSE.md`. No new GitHub release or Zenodo operation was performed in this local revision.
