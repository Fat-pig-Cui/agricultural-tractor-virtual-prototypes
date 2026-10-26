"""Verify the current public snapshot and all stored file hashes."""
from pathlib import Path
import ast
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    expected = {}
    for line in (ROOT / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = ROOT / name
        path.resolve().relative_to(ROOT)
        assert path.is_file() and sha(path) == digest, name
        assert path.stat().st_size < 100_000_000, name
        assert not re.search(rb'gh[pousr]_[A-Za-z0-9]{30,}', path.read_bytes()), name
        expected[name] = digest
    actual = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()
        and '.git' not in p.relative_to(ROOT).parts and '__pycache__' not in p.parts
        and p.name not in ['MANIFEST.sha256', '.DS_Store'] and p.suffix not in ['.pyc', '.aux', '.out', '.log']}
    assert actual == set(expected), (actual - set(expected), set(expected) - actual)
    assert not any((ROOT / name).exists() for name in ['experiments', 'results', 'revisions', 'historical', 'historical_sources', 'submission_packages', 'MDPI_template_ACS'])
    forbidden_suffixes = {'.json.gz', '.npz', '.npy', '.pkl', '.mat', '.h5'}
    assert not any(Path(name).suffix in forbidden_suffixes for name in expected)
    allowed_tools = {'verify_release.py', 'run_current_experiments.py',
                     'reproduce_paper1.py', 'reproduce_paper2.py'}
    assert {Path(name).name for name in expected if name.startswith('tools/') and name.endswith('.py')} == allowed_tools
    public_text = []
    for name in expected:
        if name == 'tools/verify_release.py':
            continue
        if name.endswith(('.py', '.sh', '.md', '.tex', '.json')):
            public_text.append((name, (ROOT / name).read_text(errors='replace')))
    forbidden_references = ('revisions/', 'historical_sources/', 'submitted_reference.json',
                            'run_paper1_', 'run_paper2_', 'plot_paper', 'frozen JSON outputs')
    assert not [(name, token) for name, text in public_text for token in forbidden_references if token in text]
    assert not any(re.search(r'(^|/)(evidence|qa|responses_current)(/|$)|Response_to_Reviewer|response_reviewer|manuscript_marked|cover_letter|major_revision_message|More_info_reviewer', name, re.I) for name in expected)
    for path in ROOT.rglob('*.py'):
        if '.git' not in path.parts:
            ast.parse(path.read_text(), filename=str(path))
    for number in [1, 2]:
        for stem in ['manuscript', 'supplementary']:
            assert (ROOT / f'manuscripts/paper{number}/{stem}.pdf').is_file()
            assert (ROOT / f'manuscripts/paper{number}/{stem}.tex').is_file()
    proof = (ROOT / 'manuscripts/paper2/manuscript.tex').read_text()
    assert '% Author response:' not in proof and '%MDPI:' not in proof
    metadata = json.loads((ROOT / '.zenodo.json').read_text())
    assert len(metadata['creators']) == 3
    assert not any(name.endswith(('.json.gz', '.npz', '.npy', '.pkl')) for name in expected)
    assert all(not name.endswith('.json') or name in ['.zenodo.json', 'manifests/current_sources.json', 'manifests/publication_status.json'] for name in expected)
    print(json.dumps(dict(status='verified', files=len(expected), current_only=True,
        experiment_results_included=False, simulations_run=False, journal_submission_verified=False)))


if __name__ == '__main__':
    main()
