# Early-pullback census hosted launcher v0.2

Parent `7623dadff641536bbf165846816affa427c13b1f`, tree
`3658e7503fc4e1accda2d1b20a7059da0b61f540`. The v0.1 launcher and its
registration `a211bc565d25118675545b248d077050fa10e16fcb7f4f509518b85b35c915c0`
remain unchanged and unarmed.

The single change in this child is the authorization evidence model. The owner
explicitly authorized execution and reasonable charges while stating uncertainty
about the Massive subscription. v0.1 requires a subscription attestation and
cannot truthfully represent that message. This child binds the actual message
and a separate public documentation projection instead. It does not infer a
verified credit balance, credit provider, or account entitlement.

## Public pricing basis

On September 12, 2026, Massive's official [All Tickers documentation](https://massive.com/docs/rest/stocks/tickers/all-tickers)
included the endpoint in all Stocks plans and listed two years of Basic history.
The [Ticker Types documentation](https://massive.com/docs/rest/stocks/tickers/ticker-types)
also included its endpoint in all Stocks plans. The [pricing page](https://massive.com/pricing)
listed Basic at USD 0/month with five API calls per minute.

The frozen March–May 2026 dates and 12.5-second request spacing fit those public
limits. The estimated incremental API charge is USD 0.00. The operator chose a
USD 10.00 maximum within the owner's reasonable-charge authorization. This is
not a provider-enforced billing cap or an account-specific quote. No metered
purchase, subscription change, wallet payment, alternate credential, or paid
fallback is enabled. A denied request terminates capture without retry.

The byte-bound `owner-authorization-source.json` and
`public-pricing-observation.json` are manual source projections, not signed
attestations or raw website archives. The approval validator requires their
exact hashes and rejects invented subscription, balance, or billing guarantees.
The pricing observation expires after seven days; approval remains limited to
seven days and must be valid at launch.

## Unchanged execution mechanics

The new module, CLI, and workflow retain v0.1's exact tested parent, sole added
execution file, successful CI and every job step, first attempt only, permanent
create-only consumption, independently pinned durable preflight, frozen runtime,
credential ordering, evidence retention, and failure semantics. The consumption
ref and artifact paths are isolated under v0.2. The old four-call provider check
remains permanently consumed and is never reused.

The unchanged census adapter still permits only the two fixed Massive API-key
GET routes, 30 fixed dates, 20 pages per date, 601 total attempts, 12.5-second
spacing, and the original byte ceilings. No strategy or backtest runs here.
No transcript records were opened. Recap actions, fills, later outcomes, and
evaluation narratives remain excluded from replay and runtime. All previous
losses, incomplete attempts, and frozen policies remain intact. Full hybrid
integration and eventual profitability are separate research questions.

The code checkpoint ships without an execution JSON. After its full suite and
hosted CI succeed, the already authorized execution is a separate sole-file
child. Actual complete or partial capture must be verified against the original
GitHub artifact digests and preflight chain; synthetic tests cannot establish
provider origin. A failed or consumed run is not automatically replaced.

## Local implementation verification

All 100 focused tests passed normally and under optimized Python, including 34
new v0.2 tests. The completed full retry ran 2,725 tests: 2,652 passed, 73 optional
SDK skips, zero failures or errors, in 412.215 seconds including discovery.
The first local full attempt stopped advancing at the existing planner's parent
registration test, before reaching the new tests, and was interrupted. Its log
and exact runner are retained as incomplete evidence; the cause is unisolated.

A retained synthetic launch verified nine preflight files and all 127 capture
archive members. Its checkout, authority, runtime, transport, and clock are
fixtures. It establishes mechanics only. Registration:
`44f61029f59bce5fbf5d5b6555aed954ffbdd801bcd91362c78ac7632d9dadab`.
