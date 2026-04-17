# SynthScan

**Detect AI-generated (synthetic) code patterns in your repository and automatically open a GitHub Issue with the findings.**

---

## How It Works

1. **Patterns** are defined in a human-readable Markdown file ([patterns/synthetic_patterns.md](patterns/synthetic_patterns.md)).  
   Each pattern is either a **plain-text substring** (case-insensitive) or a **Python regex** (prefixed with `regex:`).

2. **The scanner** walks every source file in the target directory, tests each line against every pattern, and tallies a **Synthetic Code Score** (1 point per hit).

3. **A GitHub Issue** is created (or updated) with:
   - the total score,
   - every matched snippet grouped by category,
   - the file path and line number for each hit.

4. A **JSON report** is uploaded as a build artifact for programmatic consumption.

---

## Quick Start

### Using SynthScan in your own repository

Add the workflow file `.github/workflows/synthscan.yml`:

```yaml
name: SynthScan

on:
  workflow_dispatch:
    inputs:
      scan_path:
        description: "Path to scan"
        default: "."
      score_threshold:
        description: "Fail when score >= value (0 = never)"
        default: "0"

permissions:
  contents: read
  issues: write

jobs:
  synthscan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: <owner>/SynthScan@main          # point to this action
        with:
          scan_path: ${{ github.event.inputs.scan_path || '.' }}
          patterns_file: "patterns/synthetic_patterns.md"
          score_threshold: ${{ github.event.inputs.score_threshold || '0' }}
          create_issue: "true"
```

> Replace `<owner>` with the GitHub org/user that hosts SynthScan.

### Running manually

Go to **Actions → SynthScan → Run workflow**, fill in the optional inputs, and click **Run**.

---

## Inputs

| Name | Default | Description |
|------|---------|-------------|
| `scan_path` | `.` | Directory to scan (relative to repo root). |
| `patterns_file` | `patterns/synthetic_patterns.md` | Markdown file with detection patterns. |
| `score_threshold` | `0` | Fail the step when score ≥ this value. `0` = never fail. |
| `create_issue` | `true` | Open / update a GitHub Issue with the report. |
| `issue_label` | `synthscan` | Label applied to the created issue. |
| `report_path` | `synthscan-report.json` | Path for the JSON artefact. |

## Outputs

| Name | Description |
|------|-------------|
| `score` | Total synthetic-code score. |
| `match_count` | Number of pattern hits. |
| `issue_body` | Full Markdown report. |

---

## Updating Patterns

All detection patterns live in [patterns/synthetic_patterns.md](patterns/synthetic_patterns.md).

**To add a new pattern:**

1. Open the file and find (or create) a `## Category` section.
2. Inside the ` ```patterns ` block, add one pattern per line.
   - **Plain text** → matched as a case-insensitive substring.
   - **`regex:` prefix** → compiled as a Python regular expression.
   - Lines starting with `#` are comments and ignored.
3. Commit and push. The next scan will pick up the changes automatically.

---

## Project Structure

```
SynthScan/
├── action.yml                          # GitHub Action definition
├── scanner/
│   └── synthscan.py                    # Core scanning engine
├── patterns/
│   └── synthetic_patterns.md           # Detection patterns (editable)
├── .github/
│   └── workflows/
│       └── synthscan.yml               # Workflow (manual trigger)
└── README.md
```

---

## License

MIT
