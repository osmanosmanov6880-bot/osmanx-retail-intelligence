# OSMANX RETAIL INTELLIGENCE — ATELIER R6

**Status:** offline demonstrator; five new working decision workflows on top of R5. No changes to the existing FastAPI/SQLite backend, no 1C/POS connection, no external analytics, no public deployment.

## Five production-quality *demonstration* workflows

### 1. Data Mapping Studio (`#/mapping-lab`)

- Parses local CSV with RFC-style quoted fields; detects `,` or `;`, BOM, duplicate headers, row limits and missing required fields.
- Suggests column mappings (Russian and English aliases). The user may change the mapping; each required field must map to exactly one source column.
- Converts known demonstration store labels to `s1`/`s2`/`s3`; identifiers for real models outside the 300-item demonstration catalogue are rejected, **not** guessed or fabricated.
- Atomically validates all rows using R5's canonical sales/returns/stock contract. Linked returns require prior validated receipt rows. Error rows block the entire package.
- Exports normalized CSV with spreadsheet formula-injection protection. Uploaded text remains in the current browser tab only; never changes receipts, inventory, demo KPIs or external systems. No actual 1C import or sync.

### 2. Demand Evidence Trace (`#/demand-trace`)

- Each observed request gets one mutually exclusive state: linked purchase, solution found but no linked check, stock in another store **as of today**, unavailable/unverified, or broken receipt link.
- Displays request ID, date, model, size, consent, linked sale ID, supporting stock IDs, and estimated scenario economics with configurable conversion/handling cost.
- The estimated conversion-based figure includes **only consented non-purchased requests**. It cannot be claimed as incremental gross profit. No historical availability is inferred from present stock.
- CSV export and task creation for follow-up; no warehouse/reservation changes.

### 3. Return Risk by Receipt Cohort (`#/returns-risk`)

- Group by SKU model, size or store; denominator is **original receipts** in the selected sale cohort, not raw store visitors.
- Returns are linked to those receipts through the report date even if the return happened after the selected sale period. Duplicate return links are flagged.
- Shows observed return rate, Wilson 95% interval, reasons when reported, IDs of underlying receipts/returns, and observed gross reversal.
- New receipts are right-censored (not yet eligible for a full return window). Batch defects cannot be concluded without batch data. CSV and evidence-backed task support.

### 4. Pilot Design Studio (`#/pilot-design`)

- Two-arm experiment plan with baseline purchase conversion, minimum relevant uplift in percentage points, gross margin per purchase, treatment cost and a finite budget.
- Uses a conservative normal approximation for the required sample per group at two-sided 5% significance and about 80% power. Reports observed request throughput and rough days to recruit enough events.
- Deterministic ID-and-seed assignment is provided as **a planning illustration**, not as production user-level randomization or privacy-compliant outbound messaging. Repeat customers and spillover are explicitly cautioned.
- Exports trial assignment CSV and adds a task to the local execution board. No automatic A/B routing and no guaranteed incremental economics.

### 5. Execution / Accountability Board (`#/action-board`)

- Locally create and track evidence-backed tasks with approved owner roles, priority, date and scenario; tasks from the demand, return, or pilot rooms are linked automatically.
- Strict finite-state lifecycle `planned → working → review → closed` (review may return to working). A 10-character minimum written outcome is mandatory to close. Closed tasks cannot be silently reopened.
- Append-only history per task; localStorage versioning and validation, scenario isolation, formula-safe CSV export, limits to 100 tasks and no external notifications.
- Offline data lives in the current browser profile. Losing browser storage loses the task list, so export regularly for critical real workflows. **This is not a server-side corporate audit log.**

## Verification

```sh
cd executive
npm test
python3 scripts/build_standalone.py
node --check build_check.js
python3 scripts/r6_browser_smoke.py # requires Playwright/Chromium
```

The browser suite performs live clicks, CSV exports, task handoffs, lifecycle transitions, persistence after reload, five new routes at **390 / 768 / 1440 / 1920 px**, and verifies the single-file offline HTML. Chromium may be blocked locally by an administrative URL policy; GitHub Actions runs in an environment with actual navigation.

## Boundaries

- **All baseline analytical events are synthetic.** CSV mapping allows real text to be privately inspected in-browser but never implies an actual connected integration.
- Receipts are accounting observations. Requested sizes and stock snapshots are signals. Scenario figures use manual assumptions and are **not** incremental profit or a causal conclusion.
- No personally identifying contact data are collected in the demonstrator; real operations require a privacy assessment, permission model, retention and secure backend.
- Branch main, existing backend and production server are not changed by this release.
