"""Recover four byte-pinned existing GitHub artifacts; never call a data provider.

Requires the GitHub CLI with read access to the repository's Actions artifacts.
The accepted verification ZIPs are already preserved in the repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from fetch_candidate_rvol_sources import REPO, SPECS as COARSE_SPECS

SPECS = (
    (10574105686, 'exact.zip', 63526941, '1c8f6358bdf684e796ed1006ed4d6da49af491523d9b38227a4a2565aad4fc17'),
    *((identity, Path(name).name, size, digest) for identity, name, size, digest in COARSE_SPECS[1:]),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    output = Path(parser.parse_args().output)
    if output.exists() or any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('fresh regular artifact directory required')
    output.mkdir(parents=True)
    metadata = []
    for identity, name, size, digest in SPECS:
        item = json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/actions/artifacts/{identity}']))
        if item['id'] != identity or item['size_in_bytes'] != size or item['digest'] != 'sha256:' + digest or item['expired']:
            raise ValueError('original artifact metadata differs or is expired; do not recapture automatically')
        path = output / name
        with path.open('xb') as out:
            subprocess.run(['gh', 'api', f'repos/{REPO}/actions/artifacts/{identity}/zip'],
                           stdout=out, check=True, timeout=300)
        if path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('original artifact bytes differ')
        metadata.append(item)
    (output / 'original-artifacts.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    main()
