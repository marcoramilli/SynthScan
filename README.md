# 🔍 SynthScan

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-SynthScan-orange?logo=github)](https://github.com/marketplace/actions/synthscan)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Detect AI-generated (synthetic) code patterns in your repository and automatically open a GitHub Issue with the findings.**

138 detection patterns across 17 categories · Context-aware severity weighting · **Normalised per 1 000 LOC** · AST structural analysis · Editable Markdown pattern file

---

## How It Works

1. **Patterns** are defined in a human-readable Markdown file ([patterns/synthetic_patterns.md](patterns/synthetic_patterns.md)).  
   Each pattern is either a **plain-text substring** (case-insensitive) or a **Python regex** (prefixed with `regex:`).  
   Patterns carry a **severity** (CRITICAL = 10, HIGH = 5, MEDIUM = 2, LOW = 1 points).  
   Categories can optionally be **scoped to file extensions** (e.g. `Applies to: .py`).

2. **The scanner** walks every source file in the target directory and applies four layers of detection:
   - **Line-level pattern matching** — each line is tested against all applicable patterns. Scores are multiplied by a context factor: matches inside comments (×1.5) score higher, matches inside string literals (×0.5) score lower.
   - **Multi-line block detection** — detects AI-structured docstrings (3+ section headers such as `Args:`, `Returns:`, `Raises:`), functions entirely wrapped in `bare try/except Exception`, and over-commented blocks (>50 % comment lines in a 20-line window).
   - **AST structural analysis** (Python only) — uses the `ast` module to detect unreachable code after `return`/`raise`, overly deep control-flow nesting (>3 levels), and unused imports.
   - **Cross-file repetition** — flags identical docstrings that appear verbatim in 3 or more files, a strong signal of copy-pasted AI scaffolding.

3. **Scores are refined** by two post-processing passes:
   - **Clustering bonus** — when 3 or more pattern hits fall within a 10-line window, each hit's score is multiplied by ×1.5.
   - **Diminishing returns** — beyond 20 hits per file the marginal score per additional hit is halved, preventing a single large AI-generated file from dominating the repo score.

4. **A GitHub Issue** is created (or updated) with:
   - the Synthetic Code Score, severity breakdown, and a per-directory score table,
   - every matched snippet grouped by category (with context and clustering indicators),
   - the file path and line number for each hit.

5. A **JSON report** is uploaded as a build artifact for programmatic consumption.

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
HIGH/CRITICAL rate   : 1.25 per file
============================================================

Top directories by score:
  - src/api: 142 pts
  - src/utils: 89 pts
  - src/models: 46 pts

Matches by category:
  - Decorative Section Separators: 97 matches (194 pts)
  - Excessive Try-Catch Wrapping: 57 matches (57 pts)
  - Docstring Block Structure: 12 matches (60 pts)
  - Cross-Language Confusion: 3 matches (15 pts)
  - Synthetic Comment Markers: 1 matches (5 pts)
  - Dead Code: 4 matches (8 pts)
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
| `high_critical_hit_rate` | Number of HIGH or CRITICAL matches per file scanned. |
| `by_directory` | JSON object mapping directory paths to their score. |

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
| Cross-Language Confusion (JS/TS) | HIGH | Python idioms in JS/TS files (`None`, `True`, `elif`, `print()`) |
| Hallucination Indicators | CRITICAL | Phantom imports, hallucinated API chains |
| Overly Generic Function Names | LOW | `process_data()`, `do_something()`, `helper()` |
| Excessive Try-Catch Wrapping | MEDIUM | Bare `except Exception`, generic error messages |
| Decorative Section Separators | MEDIUM | Unicode box-drawing headers, long `----` lines |
| Magic Placeholder Names | HIGH | `YOUR_API_KEY`, `YOUR_TOKEN_HERE`, `your_database_url` |
| Hyper-Verbose Identifiers | LOW | Function names >25 chars, compound-verb names (`processAndValidate`) |
| Docstring Block Structure | HIGH | Structured docstrings with 3+ AI-typical section headers |
| Over-Commented Block | LOW | >50 % comment lines in a 20-line window |
| Dead Code | MEDIUM | Unreachable statements after `return`/`raise` (AST) |
| Deep Nesting | LOW | Control-flow nesting depth >3 within a function (AST) |
| Unused Imports | LOW | Imported names never referenced in the file (AST) |
| Cross-File Repetition | HIGH | Identical docstrings appearing verbatim in 3+ files |

> **Note:** Phrase-slop categories (Slop Phrases, AI Slop Vocabulary, Verbosity Indicators, Example Usage Blocks, Redundant / Tautological Comments, Self-Referential Comments) are suppressed on documentation files (`.md`, `.txt`, `.rst`, etc.) to avoid false positives in READMEs and changelogs.

---

## Scoring Details

### Context multipliers

Each line match is adjusted based on where the match occurs in the file:

| Context | Multiplier | Rationale |
|---------|-----------|-----------|
| `COMMENT` | ×1.5 | AI slop in comments is a stronger signal |
| `CODE` | ×1.0 | Baseline |
| `STRING` | ×0.5 | String literals may be intentional user-facing copy |

### Clustering bonus

When 3 or more pattern hits occur within a 10-line window, every hit in that window is multiplied by **×1.5**. Dense clusters of AI tells are a much stronger signal than isolated matches.

### Diminishing returns

After the top 20 hits in a single file, each additional hit is scored at **×0.5**. This prevents a single large AI-generated file from making the entire repo's score uninterpretable.

---

## Updating Patterns

All detection patterns live in [patterns/synthetic_patterns.md](patterns/synthetic_patterns.md).

**To add a new pattern:**

1. Open the file and find (or create) a `## Category` section.
2. Optionally add `Applies to: .py, .js` to restrict the category to specific file extensions.
3. Inside the ` ```patterns ` block, add one pattern per line.
   - **Plain text** → matched as a case-insensitive substring (minimum 10 characters).
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
  "high_critical_hit_rate": 1.25,
  "by_directory": {
    "src/api": 142.0,
    "src/utils": 89.0
  },
  "matches": [
    {
      "file": "app.py",
      "line": 31,
      "text": "# ── Background task tracker ──────────",
      "pattern": "#.*[─━═╌╍┄┅]{5,}",
      "category": "Decorative Section Separators",
      "severity": "MEDIUM",
      "score": 3.0,
      "context": "COMMENT",
      "clustered": true
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
