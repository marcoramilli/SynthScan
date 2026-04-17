# 🔍 SynthScan

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-SynthScan-orange?logo=github)](https://github.com/marketplace/actions/synthscan)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Detect AI-generated (synthetic) code patterns in your repository and automatically open a GitHub Issue with the findings.**

120 detection patterns across 14 categories · Severity-weighted scoring · **Normalised per 1 000 LOC** · Editable Markdown pattern file

---

## How It Works

1. **Patterns** are defined in a human-readable Markdown file ([patterns/synthetic_patterns.md](patterns/synthetic_patterns.md)).  
   Each pattern is either a **plain-text substring** (case-insensitive) or a **Python regex** (prefixed with `regex:`).  
   Patterns carry a **severity** (CRITICAL = 10, HIGH = 5, MEDIUM = 2, LOW = 1 points).  
   Categories can optionally be **scoped to file extensions** (e.g. `Applies to: .py`).

2. **The scanner** walks every source file in the target directory, tests each line against every applicable pattern, and computes:
   - a **raw score** — the sum of severity points for all matches,
   - the **Synthetic Code Score** — the raw score **normalised per 1 000 lines of code**.  
     This makes the score comparable across projects of different sizes.

3. **A GitHub Issue** is created (or updated) with:
   - the Synthetic Code Score and severity breakdown,
   - every matched snippet grouped by category,
   - the file path and line number for each hit.

4. A **JSON report** is uploaded as a build artifact for programmatic consumption.

### Synthetic Code Score

The headline metric is **score per 1 000 lines of code**:

$$
\text{Synthetic Code Score} = \frac{\text{Raw Score}}{\text{Lines Scanned}} \times 1000
$$

This normalisation prevents large codebases from naturally accumulating higher scores than small ones.  
A project with 100 000 LOC and a handful of incidental matches will score near zero,  
while a small but fully AI-generated project will score significantly higher.

**Reference ranges** (from benchmark testing):

| Score range | Interpretation |
|-------------|---------------|
| 0 – 5 | Likely human-written |
| 5 – 15 | Low AI signal — review flagged lines |
| 15 – 30 | Moderate AI signal |
| 30+ | Strong AI signal |

---

## Quick Start

### From the GitHub Actions Marketplace

Add this workflow to any repo at `.github/workflows/synthscan.yml`:

```yaml
name: SynthScan

on:
  workflow_dispatch:
    inputs:
      scan_path:
        description: "Path to scan"
        default: "."
      score_threshold:
        description: "Fail when Synthetic Code Score >= value (0 = never)"
        default: "0"

permissions:
  contents: read
  issues: write

jobs:
  synthscan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: marcoramilli/SynthScan@v1
        with:
          scan_path: ${{ github.event.inputs.scan_path || '.' }}
          score_threshold: ${{ github.event.inputs.score_threshold || '0' }}
          create_issue: "true"
```

### Running locally

```bash
# scan the current directory
INPUT_SCAN_PATH=. python3 scanner/synthscan.py

# scan a specific folder, write report to a custom path
INPUT_SCAN_PATH=./src INPUT_REPORT_PATH=report.json python3 scanner/synthscan.py
```

Example output:

```
============================================================
Raw score            : 277  (162 matches)
Lines scanned        : 11187  (32 files)
Synthetic Code Score : 24.8  (per 1k LOC)
============================================================

Matches by category:
  - Decorative Section Separators: 97 matches (194 pts)
  - Excessive Try-Catch Wrapping: 57 matches (57 pts)
  - Cross-Language Confusion: 3 matches (15 pts)
  - Synthetic Comment Markers: 1 matches (5 pts)
  - Self-Referential Comments: 2 matches (4 pts)
  - Verbosity Indicators: 2 matches (2 pts)
```

---

## Inputs

| Name | Default | Description |
|------|---------|-------------|
| `scan_path` | `.` | Directory to scan (relative to repo root). |
| `patterns_file` | `patterns/synthetic_patterns.md` | Markdown file with detection patterns. |
| `score_threshold` | `0` | Fail the step when the **Synthetic Code Score** (per 1k LOC) ≥ this value. `0` = never fail. |
| `create_issue` | `true` | Open / update a GitHub Issue with the report. |
| `issue_label` | `synthscan` | Label applied to the created issue. |
| `report_path` | `synthscan-report.json` | Path for the JSON artefact. |

## Outputs

| Name | Description |
|------|-------------|
| `score` | **Synthetic Code Score** (normalised per 1k LOC). |
| `raw_score` | Un-normalised sum of severity points. |
| `match_count` | Number of pattern hits. |
| `lines_scanned` | Total lines of source code scanned. |
| `issue_body` | Full Markdown report. |

---

## Pattern Categories

| Category | Default Severity | What it detects |
|----------|-----------------|-----------------|
| Slop Phrases | MEDIUM | Filler clichés AI injects (`Feel free to modify`, `Here's a simple example`) |
| AI Slop Vocabulary | MEDIUM | Overused LLM words (`delve`, `leverage`, `robust`, `seamless`) |
| Synthetic Comment Markers | HIGH | Direct AI attribution (`Generated by GPT`, `AI-generated`) |
| Self-Referential Comments | MEDIUM | Comments narrating structure instead of intent |
| Redundant / Tautological Comments | LOW | Comments restating code verbatim (`# Set x to 5`) |
| Verbosity Indicators | LOW | Overly explanatory phrases (`This line initializes`) |
| Example Usage Blocks | LOW | `# Example usage:` blocks AI always appends |
| Fake / Example Data | MEDIUM | Placeholder data (`John Doe`, `user@example.com`) |
| Cross-Language Confusion | HIGH | Wrong-language idioms in Python (`.push()`, `null`, `&&`) |
| Hallucination Indicators | CRITICAL | Phantom imports, hallucinated API chains |
| Overly Generic Function Names | LOW | `process_data()`, `do_something()`, `helper()` |
| Excessive Try-Catch Wrapping | MEDIUM | Bare `except Exception`, generic error messages |
| Decorative Section Separators | MEDIUM | Unicode box-drawing headers, long `----` lines |

---

## Updating Patterns

All detection patterns live in [patterns/synthetic_patterns.md](patterns/synthetic_patterns.md).

**To add a new pattern:**

1. Open the file and find (or create) a `## Category` section.
2. Optionally add `Applies to: .py, .js` to restrict the category to specific file extensions.
3. Inside the ` ```patterns ` block, add one pattern per line.
   - **Plain text** → matched as a case-insensitive substring.
   - **`regex:` prefix** → compiled as a Python regular expression.
   - Prepend `[CRITICAL]`, `[HIGH]`, `[MEDIUM]`, or `[LOW]` to override the category default.
   - Lines starting with `#` are comments and ignored.
4. Commit and push. The next scan will pick up the changes automatically.

---

## JSON Report

The scanner writes a JSON report to `synthscan-report.json` (configurable via `report_path`):

```json
{
  "synthetic_code_score": 24.8,
  "raw_score": 277,
  "match_count": 162,
  "lines_scanned": 11187,
  "files_scanned": 32,
  "matches": [
    {
      "file": "app.py",
      "line": 31,
      "text": "# ── Background task tracker ──────────",
      "pattern": "#.*[─━═╌╍┄┅]{5,}",
      "category": "Decorative Section Separators",
      "severity": "MEDIUM",
      "score": 2.0
    }
  ]
}
```

---

## Project Structure

```
SynthScan/
├── action.yml                          # GitHub Action definition (Marketplace entry)
├── LICENSE                             # MIT License
├── scanner/
│   └── synthscan.py                    # Core scanning engine
├── patterns/
│   └── synthetic_patterns.md           # Detection patterns (editable)
└── README.md
```

---

## License

MIT — see [LICENSE](LICENSE).
