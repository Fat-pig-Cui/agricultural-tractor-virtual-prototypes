"""Restore losslessly compressed scientific results without overwriting changes."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import os
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def process(check_only=False):
    entries = json.loads((ROOT / 'manifests/compressed_results.json').read_text())
    for entry in entries:
        source = ROOT / entry['compressed_path']
        target = ROOT / entry['path']
        source.resolve().relative_to(ROOT)
        target.resolve().relative_to(ROOT)
        assert digest(source) == entry['compressed_sha256'], source
        if target.exists() and not check_only:
            assert digest(target) == entry['sha256'], f'Existing modified data retained: {target}'
            continue
        h = hashlib.sha256()
        size = 0
        temporary = None
        if not check_only:
            handle = tempfile.NamedTemporaryFile(dir=target.parent, prefix='.restore-', delete=False)
            temporary = Path(handle.name)
        try:
            with gzip.open(source, 'rb') as inp:
                for block in iter(lambda: inp.read(1024 * 1024), b''):
                    h.update(block)
                    size += len(block)
                    if not check_only:
                        handle.write(block)
            assert size == entry['bytes'] and h.hexdigest() == entry['sha256'], target
            if not check_only:
                handle.close()
                os.replace(temporary, target)
        finally:
            if temporary is not None:
                handle.close()
                if temporary.exists():
                    temporary.unlink()
    return len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    print(f'compressed scientific files verified: {process(args.check_only)}')
