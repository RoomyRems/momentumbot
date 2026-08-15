# Local SEC bulk float enrichment

MomentumBot's scalable historical-float path uses the SEC's free nightly bulk archives. The raw archives stay on a local machine or ingestion host; only the small, normalized output is used by research snapshots.

This is intentionally separate from GitHub Actions because `data.sec.gov` has returned HTTP 403 from GitHub-hosted Azure runners even with an identifying User-Agent. The SEC bulk archives are also a better fit for multi-issuer research than thousands of individual HTTP requests.

## Official inputs

The SEC documents two nightly archives:

- `companyfacts.zip`: `https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip`
- `submissions.zip`: `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip`

They are republished nightly. SEC fair-access guidance applies to automated downloads; browser downloads are also fine.

## Recommended local layout

```text
momentumbot/
  data/
    sec/
      companyfacts.zip
      submissions.zip
```

`data/sec/` and both archive names are ignored by Git.

## Install the branch

```bash
git fetch origin
git checkout phase-3-historical-snapshot
python -m pip install -e .
```

## Download the archives

The simplest option is to open the two official SEC URLs in a browser and save them into `data/sec/`.

For a scripted download, identify the application/contact and keep the request rate conservative:

```bash
mkdir -p data/sec
curl -L \
  -A "MomentumBot/0.3 YOUR_NAME YOUR_EMAIL" \
  -o data/sec/companyfacts.zip \
  https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip

curl -L \
  -A "MomentumBot/0.3 YOUR_NAME YOUR_EMAIL" \
  -o data/sec/submissions.zip \
  https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
```

Do not commit the ZIP files.

## Enrich a discovery artifact

After MomentumBot has produced a market-day `discovery.csv`, run:

```bash
python scripts/enrich_discovery_with_sec_bulk.py \
  --discovery /path/to/discovery.csv \
  --companyfacts data/sec/companyfacts.zip \
  --submissions data/sec/submissions.zip \
  --output artifacts/sec-enrichment
```

The reader does not extract the archives. It builds a ticker-to-CIK index from the submissions ZIP and opens only the issuer JSON records needed by the market-day candidate set.

Outputs:

```text
artifacts/sec-enrichment/
  sec-float-facts.jsonl
  unresolved.csv
  summary.json
```

`sec-float-facts.jsonl` contains SEC public-float dollar disclosures, shares-outstanding disclosures, filing/accession provenance, and availability timestamps. It does **not** pretend that SEC public-float dollars are already tradable shares; the research layer converts those disclosures using the historical stock price and applies conservative dilution roll-forward rules.

## Known limitation

The nightly submissions archive is excellent for current ticker-to-CIK resolution, but a historical or delisted ticker may not always resolve cleanly through its current ticker list. MomentumBot records those symbols in `unresolved.csv` rather than guessing. Historical symbol mapping/corporate-action data can then be used to resolve them explicitly.

## When this becomes necessary

A single reference day does not require the full SEC bulk workflow. Multi-day/multi-year backtesting does: the SEC-API.io trial is useful as an independent validation oracle, but its finite call allowance is not a scalable historical-universe database. The bulk path lets us resolve only the issuers that survive the causal price/gain/RVOL acquisition filters while retaining reproducible point-in-time filing evidence.
