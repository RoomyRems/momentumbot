"""Offline source consistency diagnostic; no runtime or financial evaluation."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import gzip

from momentumbot.research import candidate_source_archive as m
from run_offline_python_v13 import deny_external_io


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-capture',required=True)
    p.add_argument('--split-capture',nargs='+',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    sys.addaudithook(deny_external_io)
    selected=m.parse(gzip.decompress((root/m.capture.SUPERSET_PATH).read_bytes()))
    m.capture.c.d.base.verify_seal(selected)
    m.require(selected['content_sha256']==m.capture.SUPERSET_SEAL,'saved acquisition source differs')
    results=[]
    with m.CandidateMinuteArchive(root,args.raw_capture) as raw_source, m.split_source.ScannerMinuteArchive(root,args.split_capture) as split_source:
        for day in selected['days']:
            target=day['trading_date'];raw=raw_source.read_day(target)
            frames=raw['candidate_raw_minute_bars_by_symbol']
            m.exact(sorted(frames),[c['symbol'] for c in day['candidates']],'candidate population differs')
            split=m.selected_split_closes(split_source,target,sorted(frames))
            cases=[]
            for c in day['candidates']:
                cases.append({'symbol':c['symbol'],**m.compare_price_basis(frames[c['symbol']],split[c['symbol']],
                    saved_daily_factor=c['split_target_high']/c['raw_target_high'])})
            results.append({'trading_date':target,'raw_provenance':raw['provenance'],'cases':cases})
            print(target,len(cases),flush=True)
        value=m.seal({'contract_id':m.ID,'kind':'offline_candidate_price_basis_diagnostic',
            'accepted_raw_proof_sha256':m.PROOF_SEAL,'accepted_split_proof_sha256':split_source.proof['content_sha256'],
            'daily_acquisition_source_sha256':selected['content_sha256'],'days':results,
            'daily_minute_share_basis_verified':False,'provider_requests':0,
            **m.capture.old.parent.parent.BOUNDARY})
    m.capture.gate.d.base.write_once(Path(args.output),value)
    print(value['content_sha256'])

if __name__=='__main__':main()
