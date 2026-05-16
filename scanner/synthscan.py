#!/usr/bin/env python3
"""SynthScan – detect AI-generated / synthetic code patterns in a repository."""

import ast
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
    applies_to: "frozenset[str] | None" = None  # file extensions, e.g. {".py"}

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
    context: str = "CODE"  # "COMMENT", "STRING", or "CODE"
    clustered: bool = False


@dataclass
class ScanResult:
    """Aggregated result of a full scan."""
    total_score: float = 0.0
    matches: List[Match] = field(default_factory=list)
    lines_scanned: int = 0
    files_scanned: int = 0
    by_directory: "dict[str, float]" = field(default_factory=dict)

    @property
    def synthetic_code_score(self) -> float:
        """Score normalised per 1 000 lines of code."""
        if self.lines_scanned == 0:
            return 0.0
        return (self.total_score / self.lines_scanned) * 1000

    @property
    def high_critical_hit_rate(self) -> float:
        """Number of HIGH or CRITICAL matches per file scanned."""
        if self.files_scanned == 0:
            return 0.0
        hc = sum(1 for m in self.matches if m.severity in ("HIGH", "CRITICAL"))
        return round(hc / self.files_scanned, 2)

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
    "migrations", "generated", "proto", "protobuf", "fixtures",
    "mocks", "stubs", "coverage", "__generated__", "out",
}

# Files always skipped (pattern definitions, previous reports, etc.)
SKIP_FILES = {
    "synthetic_patterns.md",
    "synthscan-report.json",
}

MAX_FILE_SIZE_BYTES = 1_000_000  # 1 MB – skip huge generated files

# Extensions treated as documentation (phrase-slop patterns are suppressed on these)
DOC_EXTENSIONS = frozenset({".md", ".txt", ".rst", ".adoc", ".rdoc"})

# Pattern categories that must NOT fire on documentation files to avoid false positives
SOURCE_ONLY_CATEGORIES = frozenset({
    "Slop Phrases",
    "AI Slop Vocabulary",
    "Verbosity Indicators",
    "Example Usage Blocks",
    "Redundant / Tautological Comments",
    "Self-Referential Comments",
})


_SEVERITY_TAG_RE = re.compile(r"^\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*", re.IGNORECASE)
_DEFAULT_SEV_RE = re.compile(r"Default severity:\s*\*{0,2}(CRITICAL|HIGH|MEDIUM|LOW)\*{0,2}", re.IGNORECASE)
_APPLIES_TO_RE = re.compile(r"Applies to:\s*(.+)", re.IGNORECASE)


def load_patterns(md_path: str) -> List[PatternDef]:
    """Parse the Markdown pattern file and return a list of PatternDef."""
    md_path = os.path.realpath(md_path)
    patterns: List[PatternDef] = []
    current_category = "Uncategorised"
    category_severity = DEFAULT_SEVERITY
    category_applies_to: "frozenset[str] | None" = None
    in_block = False

    with open(md_path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")

            # Track category headings
            if line.startswith("## "):
                current_category = line[3:].strip()
                category_severity = DEFAULT_SEVERITY  # reset
                category_applies_to = None  # reset
                continue

            # Detect "Default severity: **HIGH**" lines outside blocks
            if not in_block:
                sev_match = _DEFAULT_SEV_RE.search(line)
                if sev_match:
                    category_severity = sev_match.group(1).upper()
                    continue

                # Detect "Applies to: .py, .pyw" lines outside blocks
                applies_match = _APPLIES_TO_RE.search(line)
                if applies_match:
                    exts = {e.strip().lower() for e in applies_match.group(1).split(",") if e.strip()}
                    category_applies_to = frozenset(exts) if exts else None
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
            if not is_regex and len(raw_pattern) < 10:
                print(f"[WARN] Plain-text pattern too short, skipped: {raw_pattern!r}", file=sys.stderr)
                continue
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
                applies_to=category_applies_to,
            ))

    return patterns

# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _should_skip_dir(dirname: str) -> bool:
    return dirname in SKIP_DIRS


def _is_scannable(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return False
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

    file_ext = filepath.suffix.lower()
    lines = text.split("\n")
    in_multiline_string: bool = False
    multiline_delim: str = ""

    for line_no, line_text in enumerate(lines, start=1):
        stripped = line_text.strip()

        # Determine line context (COMMENT / STRING / CODE)
        if in_multiline_string:
            context = "STRING"
            if multiline_delim in line_text:
                in_multiline_string = False
        elif stripped.startswith('"""') or stripped.startswith("'''"):
            context = "STRING"
            delim = '"""' if stripped.startswith('"""') else "'''"
            rest = stripped[3:]
            if delim not in rest:
                in_multiline_string = True
                multiline_delim = delim
        elif (stripped.startswith("#")
              or stripped.startswith("//")
              or stripped.startswith("/*")
              or (stripped.startswith("*") and not stripped.startswith("**"))):
            context = "COMMENT"
        else:
            context = "CODE"

        context_multiplier = {"COMMENT": 1.5, "STRING": 0.5, "CODE": 1.0}.get(context, 1.0)

        for pat in patterns:
            # Skip patterns scoped to specific file extensions
            if pat.applies_to and file_ext not in pat.applies_to:
                continue
            # Suppress phrase-slop patterns on documentation files
            if file_ext in DOC_EXTENSIONS and pat.category in SOURCE_ONLY_CATEGORIES:
                continue
            hit = False
            if pat.is_regex and pat.compiled:
                hit = bool(pat.compiled.search(line_text))
            else:
                hit = pat.raw.lower() in line_text.lower()

            if hit:
                adjusted_score = round(pat.score * context_multiplier, 2)
                matches.append(Match(
                    file=str(filepath),
                    line_number=line_no,
                    line_text=line_text.rstrip()[:200],  # cap length
                    pattern_raw=pat.raw,
                    category=pat.category,
                    severity=pat.severity,
                    score=adjusted_score,
                    context=context,
                ))
    return matches


# ---------------------------------------------------------------------------
# Pattern clustering – co-occurrence bonus
# ---------------------------------------------------------------------------

CLUSTER_WINDOW = 10
CLUSTER_MIN_HITS = 3
CLUSTER_MULTIPLIER = 1.5


def apply_clustering(matches: List[Match]) -> List[Match]:
    """Boost scores when multiple pattern hits cluster within CLUSTER_WINDOW lines."""
    if len(matches) < CLUSTER_MIN_HITS:
        return matches
    sorted_m = sorted(matches, key=lambda m: m.line_number)
    clustered_indices: set[int] = set()
    for i, anchor in enumerate(sorted_m):
        window = [
            j for j, m in enumerate(sorted_m)
            if abs(m.line_number - anchor.line_number) <= CLUSTER_WINDOW
        ]
        if len(window) >= CLUSTER_MIN_HITS:
            clustered_indices.update(window)
    for i in clustered_indices:
        sorted_m[i].score = round(sorted_m[i].score * CLUSTER_MULTIPLIER, 2)
        sorted_m[i].clustered = True
    return sorted_m


# ---------------------------------------------------------------------------
# Multi-line block detection
# ---------------------------------------------------------------------------

_TRIPLE_QUOTE_RE = re.compile(r'("""|\'\'\')(.*?)\1', re.DOTALL)
_TRY_WRAP_RE = re.compile(
    r'def\s+\w+[^:]*:\s*\n(\s+)try:\s*\n.*?\n\1except\s+Exception',
    re.DOTALL,
)
_DOCSTRING_HEADERS = frozenset({
    "args:", "parameters:", "returns:", "yields:",
    "raises:", "notes:", "examples:", "attributes:",
})


def scan_file_blocks(filepath: Path) -> List[Match]:
    """Detect AI signals that span multiple lines."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    block_matches: List[Match] = []

    # AI-structured docstring: 3+ recognised section headers inside triple-quoted string
    for m in _TRIPLE_QUOTE_RE.finditer(text):
        body_lower = m.group(2).lower()
        found = sum(1 for h in _DOCSTRING_HEADERS if h in body_lower)
        if found >= 3:
            lineno = text[:m.start()].count("\n") + 1
            block_matches.append(Match(
                file=str(filepath),
                line_number=lineno,
                line_text=m.group(2)[:120],
                pattern_raw="AI-structured docstring (Args/Returns/Raises)",
                category="Docstring Block Structure",
                severity="HIGH",
                score=5.0,
                context="STRING",
            ))

    # Function body entirely wrapped in bare try/except Exception
    for m in _TRY_WRAP_RE.finditer(text):
        lineno = text[:m.start()].count("\n") + 1
        block_matches.append(Match(
            file=str(filepath),
            line_number=lineno,
            line_text=text[m.start():m.start() + 80].split("\n")[0],
            pattern_raw="function body wrapped in bare try/except Exception",
            category="Excessive Try-Catch Wrapping",
            severity="MEDIUM",
            score=2.0,
            context="CODE",
        ))

    # Over-commented blocks: >50% comment lines in a 20-line chunk
    all_lines = text.split("\n")
    chunk_size = 20
    for chunk_start in range(0, len(all_lines), chunk_size):
        chunk = all_lines[chunk_start:chunk_start + chunk_size]
        if not chunk:
            continue
        comment_count = sum(
            1 for ln in chunk
            if ln.lstrip().startswith("#") or ln.lstrip().startswith("//")
        )
        if comment_count / len(chunk) > 0.5:
            block_matches.append(Match(
                file=str(filepath),
                line_number=chunk_start + 1,
                line_text=chunk[0][:200],
                pattern_raw=">50% comment density in 20-line block",
                category="Over-Commented Block",
                severity="LOW",
                score=1.0,
                context="COMMENT",
            ))

    return block_matches


# ---------------------------------------------------------------------------
# AST-level structural analysis (Python only)
# ---------------------------------------------------------------------------

def _max_nesting_depth(node: "ast.AST", depth: int = 0) -> int:
    """Return the maximum control-flow nesting depth under *node*."""
    max_depth = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            max_depth = max(max_depth, _max_nesting_depth(child, depth + 1))
        else:
            max_depth = max(max_depth, _max_nesting_depth(child, depth))
    return max_depth


def scan_file_ast(filepath: Path) -> List[Match]:
    """AST-based structural pattern detection for Python files."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, ValueError, OSError):
        return []

    ast_matches: List[Match] = []

    # Collect all identifiers used anywhere in the file (for unused-import detection)
    all_names: set[str] = set()
    all_attrs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            all_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            all_attrs.add(node.attr)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body

            # Unreachable code after return/raise
            terminal_idx = None
            for idx, stmt in enumerate(body):
                if isinstance(stmt, (ast.Return, ast.Raise)):
                    terminal_idx = idx
                    break
            if terminal_idx is not None:
                for stmt in body[terminal_idx + 1:]:
                    # Skip trailing string expressions (e.g. a docstring placed at the end)
                    if (isinstance(stmt, ast.Expr)
                            and isinstance(stmt.value, ast.Constant)
                            and isinstance(stmt.value.value, str)):
                        continue
                    ast_matches.append(Match(
                        file=str(filepath),
                        line_number=stmt.lineno,
                        line_text="",
                        pattern_raw="unreachable statement after return/raise",
                        category="Dead Code",
                        severity="MEDIUM",
                        score=2.0,
                        context="CODE",
                    ))

            # Overly deep control-flow nesting
            if _max_nesting_depth(node) > 3:
                ast_matches.append(Match(
                    file=str(filepath),
                    line_number=node.lineno,
                    line_text="",
                    pattern_raw="function nesting depth > 3",
                    category="Deep Nesting",
                    severity="LOW",
                    score=1.0,
                    context="CODE",
                ))

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # Unused imports
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                top = name.split(".")[0]
                if top not in all_names and top not in all_attrs:
                    ast_matches.append(Match(
                        file=str(filepath),
                        line_number=node.lineno,
                        line_text="",
                        pattern_raw=f"unused import: {name}",
                        category="Unused Imports",
                        severity="LOW",
                        score=1.0,
                        context="CODE",
                    ))

    return ast_matches


# ---------------------------------------------------------------------------
# Cross-file repetition detection
# ---------------------------------------------------------------------------

REPETITION_MIN_FILES = 3
_DOCSTRING_COLLECT_RE = re.compile(r'(?:"""|\'\'\')(.*?)(?:"""|\'\'\')' , re.DOTALL)


def detect_cross_file_repetition(registry: "dict[str, list[str]]") -> List[Match]:
    """Flag docstrings that appear verbatim (normalised) across 3+ different files."""
    extra: List[Match] = []
    for text_key, filepaths in registry.items():
        if len(filepaths) >= REPETITION_MIN_FILES:
            for fp in filepaths:
                extra.append(Match(
                    file=fp,
                    line_number=0,
                    line_text=text_key[:120],
                    pattern_raw=f"identical docstring in {len(filepaths)} files",
                    category="Cross-File Repetition",
                    severity="HIGH",
                    score=5.0,
                    context="STRING",
                ))
    return extra


# ---------------------------------------------------------------------------
# Directory walker
# ---------------------------------------------------------------------------

DIMINISHING_RETURNS_THRESHOLD = 20
DIMINISHING_RETURNS_FACTOR = 0.5


def scan_directory(root: str, patterns: List[PatternDef]) -> ScanResult:
    """Walk *root* and scan every eligible source file."""
    result = ScanResult()
    root_path = Path(root).resolve()
    docstring_registry: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            if not _is_scannable(fpath):
                continue
            # Read file text once; reuse for line count and docstring collection
            try:
                file_text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            line_count = file_text.count("\n") + 1
            result.lines_scanned += line_count
            result.files_scanned += 1

            # Collect normalised docstrings for cross-file repetition detection
            for ds_match in _DOCSTRING_COLLECT_RE.finditer(file_text):
                normalized = " ".join(ds_match.group(1).lower().split())
                if len(normalized) > 50:
                    docstring_registry.setdefault(normalized, []).append(str(fpath))

            file_matches: List[Match] = scan_file(fpath, patterns)
            file_matches = apply_clustering(file_matches)

            block_matches = scan_file_blocks(fpath)
            file_matches.extend(block_matches)

            if fpath.suffix.lower() == ".py":
                ast_matches = scan_file_ast(fpath)
                file_matches.extend(ast_matches)

            # Diminishing returns: discount the tail of hits per file
            if len(file_matches) > DIMINISHING_RETURNS_THRESHOLD:
                file_matches.sort(key=lambda m: m.score, reverse=True)
                for m in file_matches[DIMINISHING_RETURNS_THRESHOLD:]:
                    m.score = round(m.score * DIMINISHING_RETURNS_FACTOR, 2)

            result.matches.extend(file_matches)
            result.total_score += sum(m.score for m in file_matches)

            # Per-directory score accumulation
            try:
                dir_key = str(fpath.parent.relative_to(root_path)) or "."
            except ValueError:
                dir_key = str(fpath.parent)
            result.by_directory[dir_key] = (
                result.by_directory.get(dir_key, 0.0) + sum(m.score for m in file_matches)
            )

    # Cross-file repetition pass (requires full walk to be complete)
    repetition_matches = detect_cross_file_repetition(docstring_registry)
    result.matches.extend(repetition_matches)
    result.total_score += sum(m.score for m in repetition_matches)

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
    lines.append(f"**Synthetic Code Score: {result.synthetic_code_score:.1f}** (per 1k LOC)\n")
    lines.append(f"Raw score: {result.total_score:.0f} · Pattern hits: {len(result.matches)} · Lines scanned: {result.lines_scanned:,} ({result.files_scanned} files)\n")

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

    # Per-directory breakdown
    if result.by_directory:
        top = sorted(result.by_directory.items(), key=lambda x: x[1], reverse=True)[:5]
        lines.append("### Top Directories by Score\n")
        lines.append("| Directory | Score |")
        lines.append("|-----------|-------|")
        for d, s in top:
            lines.append(f"| `{d}` | {s:.0f} |")
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
            clustered_tag = " (clustered)" if m.clustered else ""
            lines.append(f"- {_severity_emoji(m.severity)} **{rel}** L{m.line_number} `[{m.severity}]` `[{m.context}]`{clustered_tag}  ")
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
    print(f"Raw score            : {result.total_score:.0f}  ({len(result.matches)} matches)")
    print(f"Lines scanned        : {result.lines_scanned}  ({result.files_scanned} files)")
    print(f"Synthetic Code Score : {result.synthetic_code_score:.1f}  (per 1k LOC)")
    print(f"HIGH/CRITICAL rate   : {result.high_critical_hit_rate:.2f} per file")
    print(f"{'='*60}")
    if result.by_directory:
        top_dirs = sorted(result.by_directory.items(), key=lambda x: x[1], reverse=True)[:5]
        print("\nTop directories by score:")
        for d, s in top_dirs:
            print(f"  - {d}: {s:.0f} pts")

    # Per-category breakdown
    if result.matches:
        by_cat: dict[str, list[Match]] = {}
        for m in result.matches:
            by_cat.setdefault(m.category, []).append(m)
        print("\nMatches by category:")
        for cat in sorted(by_cat, key=lambda c: sum(m.score for m in by_cat[c]), reverse=True):
            cat_matches = by_cat[cat]
            cat_score = sum(m.score for m in cat_matches)
            print(f"  - {cat}: {len(cat_matches)} matches ({cat_score:.0f} pts)")
    print()

    issue_body = build_issue_body(result, os.path.realpath(scan_path))

    # Write outputs for the GitHub Action
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"score={result.synthetic_code_score:.1f}\n")
            fh.write(f"raw_score={result.total_score:.0f}\n")
            fh.write(f"match_count={len(result.matches)}\n")
            fh.write(f"lines_scanned={result.lines_scanned}\n")
            fh.write(f"high_critical_hit_rate={result.high_critical_hit_rate}\n")
            fh.write(f"by_directory={json.dumps(result.by_directory)}\n")
            # Multi-line output for the issue body
            fh.write(f"issue_body<<EOF_SYNTHSCAN\n{issue_body}\nEOF_SYNTHSCAN\n")

    # Also write a JSON report
    report_path = os.environ.get("INPUT_REPORT_PATH", "synthscan-report.json")
    report = {
        "synthetic_code_score": round(result.synthetic_code_score, 1),
        "raw_score": result.total_score,
        "match_count": len(result.matches),
        "lines_scanned": result.lines_scanned,
        "files_scanned": result.files_scanned,
        "high_critical_hit_rate": result.high_critical_hit_rate,
        "by_directory": result.by_directory,
        "matches": [
            {
                "file": os.path.relpath(m.file, os.path.realpath(scan_path)),
                "line": m.line_number,
                "text": m.line_text,
                "pattern": m.pattern_raw,
                "category": m.category,
                "severity": m.severity,
                "score": m.score,
                "context": m.context,
                "clustered": m.clustered,
            }
            for m in result.matches
        ],
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"JSON report written to {report_path}")

    # Fail the step if score exceeds threshold (0 = never fail)
    if score_threshold > 0 and result.synthetic_code_score >= score_threshold:
        print(f"\n::error::Synthetic Code Score {result.synthetic_code_score:.1f} meets or exceeds threshold {score_threshold:.0f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
