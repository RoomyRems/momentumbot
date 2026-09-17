"""Read only accepted archives; prepare conservative exact-minute requests."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from collections import Counter
import gzip

from momentumbot.research import candidate_rvol_source as m
from momentumbot.research.candidate_source_archive import CandidateMinuteArchive
from momentumbot.research.candidate_volume_projection import selected_split_volumes, compare_completed_bucket_volumes
from run_offline_python_v13 import deny_external_io


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--coarse-capture',required=True);p.add_argument('--raw-capture',required=True)
    p.add_argument('--split-capture',nargs='+',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    sys.addaudithook(deny_external_io)
    days=[]
    with m.CandidateCoarseArchive(root,args.coarse_capture) as coarse, CandidateMinuteArchive(root,args.raw_capture) as raw, m.split_source.ScannerMinuteArchive(root,args.split_capture) as split:
        for target in sorted(set(r['trading_date'] for r in coarse.contract['requests'])):
            result=coarse.read_day(target);symbols=sorted(result['sessions_by_symbol'])
            minute=selected_split_volumes(split,target,symbols)
            native=raw.read_day(target)['candidate_raw_minute_bars_by_symbol'];cases=[]
            for symbol,history in sorted(result['sessions_by_symbol'].items()):
                cases.append({'symbol':symbol,'prior_sessions':sorted(d for d in history if d!=target),
                    'prior_coarse_bar_count':sum(len(f) for d,f in history.items() if d!=target),
                    **compare_completed_bucket_volumes(minute[symbol],history[target],target),
                    'acquisition_filter':m.possible_rvol_minutes(native[symbol],minute[symbol],history,target)})
            days.append({'trading_date':target,'source_provenance':result['provenance'],'cases':cases})
            print(target,dict(Counter(c['status'] for c in cases)),'retained',sum(c['acquisition_filter']['retain_for_exact'] for c in cases),flush=True)
        requests=m.exact_requests(coarse.contract['requests'],days)
        counts=dict(Counter(c['status'] for d in days for c in d['cases']))
        value=m.seal({'contract_id':m.ID,'accepted_coarse_proof_sha256':m.PROOF_SEAL,
            'accepted_raw_proof_sha256':raw.proof['content_sha256'],'accepted_split_proof_sha256':split.proof['content_sha256'],
            'days':days,'counts':counts,'prepared_exact_requests':requests,
            'retained_cases':sum(c['acquisition_filter']['retain_for_exact'] for d in days for c in d['cases']),
            'candidate_cases':sum(len(d['cases']) for d in days),'bar_count':sum(d['source_provenance']['bar_count'] for d in days),
            'coarse_filter_values_allowed_in_runtime':False,'new_capture_authorized_by_this_report':False,
            'provider_requests':0,'exact_same_time_rvol_complete':False,**m.capture.old.parent.parent.BOUNDARY})
    path=Path(args.output);m.require(not path.exists(),'fresh diagnostic output required')
    path.write_bytes(gzip.compress(m.capture.render(value),mtime=0))
    print(value['content_sha256'],counts,'retained',value['retained_cases'],'prepared roots',len(requests),flush=True)


if __name__=='__main__':main()
