# SynthScan

SynthScan scans source files for configurable patterns and structural signals. It reports evidence for human review; it is **not an authorship detector, security verdict, or calibrated measure of maintenance risk**.

## Install and Run

Requirements: Python 3.10+; Node.js is needed for the npm-style launcher.

Install from this checkout:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Scan a directory and write a JSON report:

```bash
.venv/bin/python scanner/synthscan.py --scan-path ./src --report-path synthscan-report.json
```

Or use the Node launcher, including readable risk-vector output:

```bash
PYTHON="$PWD/.venv/bin/python" node bin/synthscan.js --scan-path ./src
```

For JSON output, a threshold gate, or staged changes:

```bash
PYTHON="$PWD/.venv/bin/python" node bin/synthscan.js --scan-path ./src --json --output-json report.json
PYTHON="$PWD/.venv/bin/python" node bin/synthscan.js --diff-base origin/main --ci
PYTHON="$PWD/.venv/bin/python" node bin/synthscan.js --staged --ci
```

The npm package exposes `synthscan` and `slopscan` commands. `--ci` fails on HIGH or CRITICAL heuristic risk by default; `--risk-threshold N` accepts 0–100. Staged mode reads the Git index, not unstaged working-tree edits. Diff mode limits findings to added lines; cross-file repetition is omitted because it has no reliable changed-line location.

## Risk Payload

JSON reports retain the legacy Synthetic Code Score and add four versioned indices:

- Cognitive ownership signals
- Hallucinated dependency and supply-chain signals
- Agent over-engineering signals
- PR review-velocity impact

Risk Payload v1 is versioned separately from the legacy scanner engine. A suspicious import is not proof that a package is nonexistent; a code pattern does not prove how it was authored or understood. The contract is in [`schemas/synthscan-risk-v1.schema.json`](schemas/synthscan-risk-v1.schema.json), and pattern-to-vector mapping/scoring lives in `scanner/risk.py`.

The monitor repository includes `calibrate_risk.py` for an exploratory comparison against repository-age and agent-project proxies. It recomputes Risk Payload v1 from stored findings and can shallow-clone/scan a curated manifest of repositories whose GitHub `pushed_at` predates 2023, recording each scanned HEAD commit and scan failures. Outputs include cohort counts, proxy AUC/intervals, exploratory thresholds, and leave-one-out metrics. These repository-level labels are not ground truth for authorship, comprehension, dependency correctness, review time, or maintenance outcomes; the analysis does not alter production scoring. See the monitor README and generated `reports/risk_calibration_proxy.md` for method and results.

Latest proxy run used 25 pre-2023 historical repositories and 11 selected agent-project repositories. Proxy AUCs were 0.820 (ownership), 0.726 (dependency/supply chain), 0.873 (over-engineering), and 0.787 (review effort); LOOCV balanced accuracy ranged from 0.607 to 0.824. These figures measure separation of selected repository proxies only, not calibrated risk or authorship. Production coefficients and thresholds remain unchanged; see the monitor README for intervals and methodology.

## GitHub and Local Guardrails

- `.github/workflows/synthscan-pr-agent.yml` scans PR additions, uploads a JSON artifact, and updates one summary comment. The write-enabled comment job uses trusted base-branch code; fork PRs do not receive a write-token comment.
- `action.yml` remains the reusable composite Action for repository scans and optional issue creation.
- `.pre-commit-hooks.yaml` defines the staged-diff audit hook.
- `synthscan sanitize --path ./src` previews narrowly scoped comment cleanup. Nothing is changed unless `--apply` is explicit; ambiguous code placeholders are reported for manual review. `synthscan sanitize --staged --apply` changes the Git index only.

## Local Audit API

Start the optional, local-only API with:

```bash
PYTHON="$PWD/.venv/bin/python" node bin/synthscan.js serve
```

It listens on `127.0.0.1:8765`. `POST /v1/audit` returns findings and the risk payload; `POST /v1/sanitize` returns proposed diffs and never applies them. Requests are size/rate limited, source is processed in a temporary directory, and no hosted service is provided. Remote binding requires `SYNTHSCAN_API_TOKEN`; do not expose this development server directly to the internet.

## Local Smoke Check

```bash
npm run build
PYTHON="$PWD/.venv/bin/python" node bin/synthscan.js --scan-path scanner --json
```

Edit detection patterns in `patterns/synthetic_patterns.md`. Risk scores are indices; do not describe them as probabilities or measured review times.