# Executive Edition R1.0 — Engineering acceptance

Date: 2026-11-08. This release is intentionally an **add-on** to the existing R0.7 codebase, not a replacement.

## Five completed engineering units

| Unit | Implementation | Verification |
|---|---|---|
| Architecture | deterministic event store, finance and projection APIs, separate reusable view utilities | Node tests and syntax validation |
| Obsidian Dashboard | 14/30/90-day financial summaries, 300-model source population, 3 scenarios, opportunity map, filters | runtime test harness |
| 30-second walkthrough | 5 scenes, manual/timed progress, actual link between request and receipt, transfer counterfactual | scenario navigation tests |
| Data & finance | receipts/returns/requests/fittings/audits/transfers/preorders/traffic; cost and revenue logic | arithmetic reconciliation |
| Demand & rescue | 60 / 32 / 18 / 7 funnel, 7 × (8,900−4,900), stage drill-down and what-if slider | deterministic assertions |

## Additional completed UI

10 standalone interactive analytics modules, decisions list, store diagnostic, presentation mode, client-side PDF generator, offline single-file packaging and source matrix relative to 1C.

## Missing production requirements

The offline Executive layer is **not** an authenticated multitenant production SaaS. No adapters to ERP/POS or cameras. Historical data is purely synthetic. Client-side action plans use browser localStorage only. Autoplay/interaction performance and visual fidelity at actual viewports require tests in an unrestricted browser. Do not describe hypothetical margin as *real incremental profit*.

## Reproducibility

- `npm test` (dependency-free)
- `node --check build_check.js`
- `python3 scripts/build_standalone.py`
- `python3 scripts/browser_smoke.py` (environment has to permit local navigation)
