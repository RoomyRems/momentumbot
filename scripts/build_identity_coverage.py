"""Build/verify the fixed dated identity/coverage handoff using saved sources."""
import argparse
import gzip
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # reuse the frozen repository identity audit helpers


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('freeze', 'validate', 'build', 'verify'))
    p.add_argument('--census-zip', type=Path)
    p.add_argument('--coverage-zip', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--panel', type=Path)
    args = p.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import identity_coverage as m
    if args.mode == 'freeze':
        with (ROOT / m.CONTRACT_PATH).open('xb') as handle: handle.write(m.render(m.registration(ROOT)))
    contract = m.validate_registration(ROOT)
    if args.mode in ('freeze', 'validate'):
        print(json.dumps({'registration_sha256': contract['content_sha256'], 'provider_requests': 0}))
        return
    m.require(args.census_zip is not None and args.coverage_zip is not None, 'both original source archives required')
    progress = lambda x: print(json.dumps(x), flush=True)
    if args.mode == 'verify':
        m.require(args.panel is not None, 'saved panel required')
        panel = m.parse(gzip.decompress(args.panel.read_bytes()))
        result = m.verify_saved(panel, args.census_zip, args.coverage_zip, ROOT, progress)
    else:
        m.require(args.output is not None and not args.output.exists()
            and not any(p.is_symlink() for p in (args.output, *args.output.parents)), 'fresh regular output required')
        panel = m.build_panel(args.census_zip, args.coverage_zip, ROOT, progress)
        result = m.summary(panel)
        args.output.mkdir(parents=True, exist_ok=False)
        raw = gzip.compress(m.render(panel), mtime=0)
        (args.output / 'identity-coverage-panel.json.gz').write_bytes(raw)
        result = m.seal({**{k:v for k,v in result.items() if k != 'content_sha256'},
            'panel_file': {'bytes': len(raw), 'sha256': m.sha(raw)}})
        (args.output / 'summary.json').write_bytes(m.render(result))
        (args.output / 'remaining-alias-plan.json').write_bytes(m.render(panel['remaining_alias_plan']))
    print(json.dumps({'panel_sha256': panel['content_sha256'], 'totals': result['totals'], 'provider_requests': 0}))


if __name__ == '__main__': main()
