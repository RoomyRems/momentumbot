"""Download four already captured GitHub artifacts; no market-provider calls."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

REPO='RoomyRems/momentumbot'
SPECS=(
    (10474627567,'research/data-audits/early-pullback-candidate-rvol-coarse-v0.1/original-verification.zip',796826,'8ac9bae226bdfc723fad418a8e9ba7bb9483be3ea07d8bd1a2d5e5921b0200f4'),
    (10475116749,'source-inputs/coarse.zip',31719387,'11c2bbfe5f13b977e220ce8b23971836bef2b29047c21da129a541c2f510f5b8'),
    (10462664282,'source-inputs/raw.zip',4601420,'0b765e27cc96a6b7d52a0a8878b238cc1ce3d1954ec01b07184ba13bf5569f08'),
    (10450218482,'source-inputs/split.zip',92363559,'a8b3516932f4fbe8c076e7a644687848498d71eee71e4594fd3f49a724300ef4'),
)


def main():
    terminal=[]
    for identity,name,size,digest in SPECS:
        metadata=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/actions/artifacts/{identity}']))
        if metadata['id']!=identity or metadata['size_in_bytes']!=size or metadata['digest']!='sha256:'+digest or metadata['expired']:
            raise ValueError('original artifact metadata differs')
        path=Path(name);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as out:
            subprocess.run(['gh','api',f'repos/{REPO}/actions/artifacts/{identity}/zip'],stdout=out,check=True,timeout=300)
        if path.stat().st_size!=size or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('original artifact bytes differ')
        terminal.append(metadata)
    Path('source-output/original-artifacts.json').write_text(json.dumps({
        'code_commit':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
        'artifacts':terminal,'market_provider_requests':0},indent=2)+'\n')


if __name__=='__main__':main()
