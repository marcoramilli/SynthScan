#!/usr/bin/env python3
"""SynthScan – detect AI-generated / synthetic code patterns in a repository."""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

# Severity tag → numeric score
SEVERITY_SCORES = {
    "CRITICAL": 10.0,
    "HIGH": 5.0,
    "MEDIUM": 2.0,
    "LOW": 1.0,
}

# Category heading text → default severity (parsed from the MD file)
# Fallback when no explicit tag and no "Default severity" line.
DEFAULT_SEVERITY = "MEDIUM"


@dataclass
class PatternDef:
    """A single detection pattern (plain text or compiled regex)."""
    category: str
    raw: str
    is_regex: bool
    severity: str = "MEDIUM"
    compiled: "re.Pattern | None" = None

    @property
    def score(self) -> float:
        return SEVERITY_SCORES.get(self.severity, 2.0)


@dataclass
class Match:
    """A single match found in the source tree."""
    file: str
    line_number: int
    line_text: str
    pattern_raw: str
    category: str
    severity: str = "MEDIUM"
    score: float = 2.0


@dataclass
class ScanResult:
    """Aggregated result of a full scan."""
    total_score: float = 0.0
    matches: List[Match] = field(default_factory=list)

# ---------------------------------------------------------------------------
# Pattern loader – reads the Markdown pattern file
# ---------------------------------------------------------------------------

PATTERNS_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "patterns", "synthetic_patterns.md")

# File extensions to scan
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".sh", ".bash", ".zsh", ".r", ".m", ".mm", ".lua",
    ".pl", ".pm", ".dart", ".vue", ".svelte", ".html", ".css",
    ".scss", ".less", ".sql", ".yaml", ".yml", ".toml", ".json",
    ".xml", ".md", ".txt", ".cfg", ".ini", ".tf", ".hcl",
}

# Directories always skipped
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info", ".next", ".nuxt", "vendor",
}

MAX_FILE_SIZE_BYTES = 1_000_000  # 1 MB – skip huge generated files


_SEVERITY_TAG_RE = re.compile(r"^\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*", re.IGNORECASE)
_DEFAULT_SEV_RE = re.compile(r"Default severity:\s*\*{0,2}(CRITICAL|HIGH|MEDIUM|LOW)\*{0,2}", re.IGNORECASE)


def load_patterns(md_path: str) -> List[PatternDef]:
    """Parse the Markdown pattern file and return a list of PatternDef."""
    md_path = os.path.realpath(md_path)
    patterns: List[PatternDef] = []
    current_category = "Uncategorised"
    category_severity = DEFAULT_SEVERITY
    in_block = False

    with open(md_path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")

            # Track category headings
            if line.startswith("## "):
                current_category = line[3:].strip()
                category_severity = DEFAULT_SEVERITY  # reset
                continue

            # Detect "Default severity: **HIGH**" lines outside blocks
            if not in_block:
                sev_match = _DEFAULT_SEV_RE.search(line)
                if sev_match:
                    category_severity = sev_match.group(1).upper()
                    continue

            # Detect fenced-block boundaries
            if line.strip().startswith("```"):
                in_block = not in_block
                continue

            if not in_block:
                continue

            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue  # skip blanks & comments

            # Check for per-pattern severity override: [HIGH] regex:...
            severity = category_severity
            tag_m = _SEVERITY_TAG_RE.match(stripped)
            if tag_m:
                severity = tag_m.group(1).upper()
                stripped = stripped[tag_m.end():].strip()

            is_regex = stripped.startswith("regex:")
            raw_pattern = stripped[len("regex:"):] if is_regex else stripped
            compiled = None
            if is_regex:
                try:
                    compiled = re.compile(raw_pattern)
                except re.error:
                    print(f"[WARN] Invalid regex skipped: {raw_pattern}", file=sys.stderr)
                    continue

            patterns.append(PatternDef(
                category=current_category,
                raw=raw_pattern,
                is_regex=is_regex,
                severity=severity,
                compiled=compiled,
            ))

    return patterns

# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _should_skip_dir(dirname: str) -> bool:
    return dirname in SKIP_DIRS


def _is_scannable(path: Path) -> bool:
    if path.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    try:
        if path.stat().st_size > MAX_FILE_SIZE_BYTES:
            return False
    except OSError:
        return False
    return True


def scan_file(filepath: Path, patterns: List[PatternDef]) -> List[Match]:
    """Scan a single file against all patterns."""
    matches: List[Match] = []
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return matches

    lines = text.split("\n")
    for line_no, line_text in enumerate(lines, start=1):
        for pat in patterns:
            hit = False
            if pat.is_regex and pat.compiled:
                hit = bool(pat.compiled.search(line_text))
            else:
                hit = pat.raw.lower() in line_text.lower()

            if hit:
                matches.append(Match(
                    file=str(filepath),
                    line_number=line_no,
                    line_text=line_text.rstrip()[:200],  # cap length
                    pattern_raw=pat.raw,
                    category=pat.category,
                    severity=pat.severity,
                    score=pat.score,
                ))
    return matches


def scan_directory(root: str, patterns: List[PatternDef]) -> ScanResult:
    """Walk *root* and scan every eligible source file."""
    result = ScanResult()
    root_path = Path(root).resolve()

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            if not _is_scannable(fpath):
                continue
            file_matches = scan_file(fpath, patterns)
            result.matches.extend(file_matches)
            result.total_score += sum(m.score for m in file_matches)

    return result

# ---------------------------------------------------------------------------
# Issue body builder
# ---------------------------------------------------------------------------

MAX_SNIPPETS_IN_ISSUE = 50  # keep issue readable


def _severity_emoji(sev: str) -> str:
    return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}.get(sev, "⚪")


def build_issue_body(result: ScanResult, repo_root: str) -> str:
    """Generate Markdown for the GitHub issue body."""
    lines: List[str] = []
    lines.append("# SynthScan Report\n")
    lines.append(f"**Synthetic Code Score: {result.total_score:.0f}**\n")
    lines.append(f"Total pattern hits: **{len(result.matches)}**\n")

    if not result.matches:
        lines.append("\nNo synthetic-code patterns detected. :white_check_mark:\n")
        return "\n".join(lines)

    # Severity breakdown
    sev_counts: dict[str, int] = {}
    for m in result.matches:
        sev_counts[m.severity] = sev_counts.get(m.severity, 0) + 1
    lines.append("### Severity Breakdown\n")
    lines.append("| Severity | Hits | Points each |")
    lines.append("|----------|------|-------------|")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        cnt = sev_counts.get(sev, 0)
        if cnt:
            lines.append(f"| {_severity_emoji(sev)} {sev} | {cnt} | {SEVERITY_SCORES[sev]:.0f} |")
    lines.append("")

    # Group by category
    by_cat: dict[str, List[Match]] = {}
    for m in result.matches:
        by_cat.setdefault(m.category, []).append(m)

    for cat, cat_matches in sorted(by_cat.items()):
        cat_score = sum(m.score for m in cat_matches)
        lines.append(f"\n## {cat}  ({len(cat_matches)} hits · {cat_score:.0f} pts)\n")
        shown = cat_matches[:MAX_SNIPPETS_IN_ISSUE]
        for m in shown:
            rel = os.path.relpath(m.file, repo_root)
            lines.append(f"- {_severity_emoji(m.severity)} **{rel}** L{m.line_number} `[{m.severity}]`  ")
            lines.append(f"  Pattern: `{m.pattern_raw}`  ")
            lines.append(f"  ```")
            lines.append(f"  {m.line_text}")
            lines.append(f"  ```")
        if len(cat_matches) > MAX_SNIPPETS_IN_ISSUE:
            lines.append(f"\n_… and {len(cat_matches) - MAX_SNIPPETS_IN_ISSUE} more in this category._\n")

    lines.append("\n---\n_Report generated by **SynthScan** · Patterns sourced from [AI-SLOP-Detector](https://github.com/flamehaven01/AI-SLOP-Detector)._\n")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    scan_path = os.environ.get("INPUT_SCAN_PATH", ".")
    patterns_file = os.environ.get("INPUT_PATTERNS_FILE", PATTERNS_DEFAULT)
    score_threshold = float(os.environ.get("INPUT_SCORE_THRESHOLD", "0"))

    patterns = load_patterns(patterns_file)
    if not patterns:
        print("No patterns loaded – check your patterns file.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(patterns)} patterns from {patterns_file}")
    print(f"Scanning: {os.path.realpath(scan_path)}")

    result = scan_directory(scan_path, patterns)

    print(f"\n{'='*60}")
    print(f"Synthetic Code Score : {result.total_score:.0f}")
    print(f"Total matches        : {len(result.matches)}")
    print(f"{'='*60}\n")

    issue_body = build_issue_body(result, os.path.realpath(scan_path))

    # Write outputs for the GitHub Action
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"score={result.total_score:.0f}\n")
            fh.write(f"match_count={len(result.matches)}\n")
            # Multi-line output for the issue body
            fh.write(f"issue_body<<EOF_SYNTHSCAN\n{issue_body}\nEOF_SYNTHSCAN\n")

    # Also write a JSON report
    report_path = os.environ.get("INPUT_REPORT_PATH", "synthscan-report.json")
    report = {
        "score": result.total_score,
        "match_count": len(result.matches),
        "matches": [
            {
                "file": os.path.relpath(m.file, os.path.realpath(scan_path)),
                "line": m.line_number,
                "text": m.line_text,
                "pattern": m.pattern_raw,
                "category": m.category,
                "severity": m.severity,
                "score": m.score,
            }
            for m in result.matches
        ],
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"JSON report written to {report_path}")

    # Fail the step if score exceeds threshold (0 = never fail)
    if score_threshold > 0 and result.total_score >= score_threshold:
        print(f"\n::error::Synthetic score {result.total_score:.0f} meets or exceeds threshold {score_threshold:.0f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
