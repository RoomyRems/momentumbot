"""Explain frozen price-scale residuals using a fixed cent-rounding hypothesis."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from collections import Counter
import gzip

from momentumbot.research import candidate_source_archive as m
from momentumbot.research.candidate_price_rounding import explain_case
from run_offline_python_v13 import deny_external_io

ID = 'early-pullback-candidate-price-rounding-v0.1'
PARENT_SEAL = 'fc6179cb78130c313e99c498d58097d1304cbdde251aa243b45601eadd630c4e'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-capture',required=True)
    p.add_argument('--split-capture',nargs='+',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--model',choices=['nearest_cent','observed_precision'],default='nearest_cent')
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    sys.addaudithook(deny_external_io)
    parent=m.parse(gzip.decompress((root/m.BASE/'price-basis-diagnostic.json.gz').read_bytes()))
    m.capture.c.d.base.verify_seal(parent)
    m.require(parent['content_sha256']==PARENT_SEAL,'original price diagnostic differs')
    selected=m.parse(gzip.decompress((root/m.capture.SUPERSET_PATH).read_bytes()))
    m.capture.c.d.base.verify_seal(selected)
    m.require(selected['content_sha256']==m.capture.SUPERSET_SEAL,'original daily source differs')
    results=[]
    with m.CandidateMinuteArchive(root,args.raw_capture) as raw_source, m.split_source.ScannerMinuteArchive(root,args.split_capture) as split_source:
        for day,original in zip(selected['days'],parent['days'],strict=True):
            target=day['trading_date'];m.exact(target,original['trading_date'],'parent date differs')
            frames=raw_source.read_day(target)['candidate_raw_minute_bars_by_symbol']
            m.exact(sorted(frames),[c['symbol'] for c in day['candidates']],'candidate population differs')
            split=m.selected_split_closes(split_source,target,sorted(frames))
            cases=[]
            for c,old in zip(day['candidates'],original['cases'],strict=True):
                symbol=c['symbol'];m.exact(symbol,old['symbol'],'parent case differs')
                cases.append({'symbol':symbol,'original_mismatched_prices':old.get('mismatched_prices_at_relative_tolerance_1e9',0),
                    **explain_case(frames[symbol],split[symbol],raw_daily_high=c['raw_target_high'],split_daily_high=c['split_target_high'],model=args.model)})
            results.append({'trading_date':target,'cases':cases});print(target,dict(Counter(c['status'] for c in cases)),flush=True)
        counts=dict(Counter(c['status'] for d in results for c in d['cases']))
        value=m.seal({'contract_id':ID,'parent_diagnostic_sha256':PARENT_SEAL,'model':'one positive factor and nearest-cent adjusted prices; closed ties' if args.model == 'nearest_cent' else 'post-hoc observed precision: nearest 0.001 below 10, nearest 0.01 otherwise; closed ties; reported adjusted value selects precision',
            'accepted_raw_proof_sha256':m.PROOF_SEAL,'accepted_split_proof_sha256':split_source.proof['content_sha256'],
            'daily_acquisition_source_sha256':selected['content_sha256'],'counts':counts,'days':results,
            'vendor_rounding_documented':False,'daily_minute_share_basis_verified':False,'runtime_normalization_authorized':False,
            'provider_requests':0,**m.capture.old.parent.parent.BOUNDARY})
    m.capture.gate.d.base.write_once(Path(args.output),value)
    print(value['content_sha256'],counts)

if __name__=='__main__':main()
