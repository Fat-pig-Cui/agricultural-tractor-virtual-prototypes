# v1.0.6

- Refines the Energies manuscript Figure 1 box labels from 17 pt to 15.5 pt
  and the feedback label from 14.5 pt to 13.2 pt after page-scale review.
- Retains the two- and three-line label layout, with no text clipping, border
  contact, arrow overlap, page-count change, or scientific-content change.

# v1.0.5

- Increases the Energies manuscript Figure 1 box labels from the 9.2 pt
  plotting default to 17 pt and the feedback label to 14.5 pt.
- Reflows long labels across two or three lines so the enlarged text remains
  inside its boxes with no arrow, border, or caption overlap.
- Rebuilds the 16-page Energies PDF; the controller structure, numerical
  results, and simulation-only evidence boundaries are unchanged.

# v1.0.4

- Synchronizes the current Machines and Energies manuscripts and compiled PDFs
  with the submission-ready 2026-09-27 sources.
- Adds the primary paper-1 two-chamber V2 model, 20-path holdout, independent
  stress audit, mode-selection record, exported parameter manifest, and V2
  architecture/result figures.
- Adds the primary paper-2 viability-shielded adaptive ECMS model, 20-path
  holdout, cross-cycle and map/capacity audits, exported parameter manifest,
  and V2 architecture/result figures.
- Pins the controller-comparison figure to the complete frozen benchmark JSON
  used by the manuscript while retaining the later exploratory result file as
  a separate artifact.
- Corrects minor figure-label and annotation collisions in both manuscripts;
  no evidence boundary is relaxed and the approximately 20% result remains an
  idealized full-information diagnostic.

# v1.0.3

- Removes Lihan Wang from both manuscript author lists and transfers the
  Investigation role to Chenyu Cui.
- Updates the current CRediT, CFF, license, Zenodo, and README metadata to the
  three-author roster. Earlier GitHub and Zenodo versions remain immutable
  historical snapshots.
- Adds the Machines and Energies manuscript sources and PDFs used for the
  current submissions, replacing the earlier generic-journal source aliases
  as the release-verification targets.
- Adds the paper-1 20-seed controller-interface/observer audit, including the
  retained unfiltered-pressure-noise failure boundary and a declared filtered
  combined-mismatch condition.
- Adds the paper-2 frozen 120--280 kWh storage-capacity and causal-predictor
  sensitivity audits; neither changes the sign of the certified MPC result.
- Corrects all active archive references to the Zenodo concept DOI
  `10.5281/zenodo.22754509`. The version DOI `10.5281/zenodo.22754510` remains
  the immutable v1.0.1 record and is not the concept DOI.

# v1.0.2

- Removes the unassigned MDPI-template DOI
  `10.3390/agriengineering1010000` from both submitted-manuscript footers.
- Rebuilds both manuscript PDFs without changing their submission-mode status
  text, study content, or page counts.
- Updates the author roster to Chenyu Cui, Peng Wang, Lihan Wang, and Yucheng
  Zhang; Peng Wang holds the Validation role in both manuscripts and archive
  metadata.
- Expands the manuscript background and related-work sections with
  DOI-verified literature, and changes the manuscript data-availability links
  to the Zenodo concept DOI `10.5281/zenodo.22754509`.
- This GitHub release is the source snapshot for the next Zenodo version. The
  concept DOI `10.5281/zenodo.22754509` will resolve to that new immutable
  record after it is published; the v1.0.1 version DOI below remains the
  previous immutable snapshot.

# v1.0.1

Zenodo-ready archival release supporting two English submissions to
AgriEngineering. This version adds the public GitHub repository URL to the
two manuscript data-availability statements.

The immutable Zenodo archival record for this release is
https://doi.org/10.5281/zenodo.22754510.

- Includes the current manuscript sources and compiled PDFs.
- Includes reproducible virtual-prototype code, parameters, figures, and
  result outputs used by the current papers.
- Includes Zenodo metadata and a CFF citation record.
- Excludes superseded drafts and invalid terminal-SOC fuel diagnostics.

This archive reports theoretical simulation evidence only. It contains no
field, vehicle, bench, or calibrated component-map measurements.
