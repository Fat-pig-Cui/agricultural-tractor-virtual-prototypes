# Current archive scope and verification policy

The working tree contains the accepted Machines manuscript, the corrected Energies author proof, model code, experiment-generation scripts, theoretical parameter manifests, and documentation.

Frozen experiment outputs, raw trajectories, checkpoints, development searches, and independent result-statistics JSON files are excluded. Figures and supplementary descriptions that belong to the manuscripts remain available. Complete scientific records remain in the author research workspace.

`MANIFEST.sha256` covers all files in this checkout except itself. `manifests/current_sources.json` records source mappings and exported hashes. The Paper 2 TeX comment removal and optional historical-reference behavior of three scripts are recorded as derived operations. Controllers, models, and experiment settings are unchanged.

The integrity check covers files, Python syntax, and the public scope; it does not recompute removed frozen statistics. The short smoke test and full reproduction runners write only to an external workspace. When historical references are absent, the repository does not claim byte-level parity with historical outputs.

Old manuscripts, review correspondence, author responses, marked files, cover letters, submission packages, and patents are excluded. Existing Git history and releases remain. This local revision uses amend for the latest synchronization commit and is not being pushed or published to Zenodo.
