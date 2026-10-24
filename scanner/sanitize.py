#!/usr/bin/env python3
"""Conservative SynthScan sanitizer; all edits are opt-in and diff-first."""

import argparse
import difflib
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".sh", ".bash", ".zsh", ".r", ".m", ".mm", ".lua",
    ".pl", ".pm", ".dart", ".vue", ".svelte", ".html", ".css",
    ".scss", ".less", ".sql", ".yaml", ".yml", ".toml", ".json",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "vendor"}
COMMENT_PREFIX_RE = re.compile(r"^(\s*)(#|//)\s*(.*?)\s*$")
NOISE_COMMENT_RE = re.compile(
    r"(?:here (?:is|are) (?:the )?(?:implementation|solution|code)|"
    r"i (?:have|'ve) (?:added|implemented|updated|created|modified|written)(?: .*)?|"
    r"let me know if (?:you need|you'd like|there is anything)(?: .*)?|"
    r"hope this helps[!.]?)",
    re.IGNORECASE,
)
PLACEHOLDER_COMMENT_RE = re.compile(
    r"(?:todo|fixme)\s*:\s*(?:implement(?: this| here)?|add implementation here|fill (?:this )?in)(?:[.!])?",
    re.IGNORECASE,
)
PLACEHOLDER_CODE_RE = re.compile(
    r"(?:\bNotImplementedError\s*\(|\b(?:YOUR_API_KEY|YOUR_TOKEN_HERE|INSERT_YOUR_SECRET)\b)",
    re.IGNORECASE,
)
PASS_TODO_RE = re.compile(r"^(\s*pass)\s+#\s*(?:todo|fixme)\s*:\s*(?:implement(?: this| here)?|add implementation here)\s*$", re.IGNORECASE)
REDUNDANT_STATEMENT_RE = re.compile(r"^(?:return\b.*|raise\b.*|break|continue|pass)$", re.IGNORECASE)


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("file path must be relative and may not contain '..'")
    return path.as_posix()


def sanitize_text(text: str) -> dict:
    """Return a proposed comment-only cleanup plus non-mutating review items."""
    original_lines = text.splitlines(keepends=True)
    cleaned_lines = []
    patches = []
    review_items = []

    for line_number, line in enumerate(original_lines, 1):
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        pass_todo = PASS_TODO_RE.fullmatch(body)
        if pass_todo:
            cleaned_lines.append(pass_todo.group(1) + newline)
            patches.append({"line": line_number, "rule": "placeholder_comment", "action": "remove_inline_placeholder_comment"})
            review_items.append({"line": line_number, "rule": "placeholder_stub", "action": "manual_review_required"})
            continue
        comment = COMMENT_PREFIX_RE.match(body)
        if comment:
            comment_text = comment.group(3).strip()
            next_code = original_lines[line_number].strip() if line_number < len(original_lines) else ""
            redundant = (
                REDUNDANT_STATEMENT_RE.fullmatch(comment_text)
                and comment_text.lower() == next_code.lower()
            )
            if (NOISE_COMMENT_RE.fullmatch(comment_text)
                    or PLACEHOLDER_COMMENT_RE.fullmatch(comment_text)
                    or redundant):
                rule = (
                    "conversational_noise" if NOISE_COMMENT_RE.fullmatch(comment_text)
                    else "redundant_inner_comment" if redundant
                    else "placeholder_comment"
                )
                patches.append({"line": line_number, "rule": rule, "action": "remove_comment_line"})
                continue

        if PLACEHOLDER_CODE_RE.search(body):
            review_items.append({
                "line": line_number,
                "rule": "placeholder_code",
                "action": "manual_review_required",
            })
        cleaned_lines.append(line)

    cleaned = "".join(cleaned_lines)
    diff = "".join(difflib.unified_diff(
        original_lines,
        cleaned_lines,
        fromfile="a/source",
        tofile="b/source",
        lineterm="\n",
    ))
    return {"content": cleaned, "patches": patches, "review_items": review_items, "diff": diff}


def _git_output(args: list[str], *, input_data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", *args], input=input_data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def sanitize_staged(apply: bool = False) -> list[dict]:
    names = _git_output(["diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z"]).split(b"\0")
    results = []
    for raw_name in names:
        if not raw_name:
            continue
        name = os.fsdecode(raw_name)
        try:
            relative = _safe_relative_path(name)
        except ValueError:
            continue
        if Path(relative).suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        index_records = _git_output(["ls-files", "--stage", "-z", "--", relative]).split(b"\0")
        record = next((item for item in index_records if item), b"")
        if not record or b"\t" not in record:
            continue
        metadata, _ = record.split(b"\t", 1)
        mode, _object_id, stage = metadata.decode("ascii").split(" ", 2)
        if stage != "0":
            continue
        staged_bytes = _git_output(["show", f":{relative}"])
        if b"\0" in staged_bytes:
            continue
        try:
            staged_text = staged_bytes.decode("utf-8")
        except UnicodeDecodeError:
            continue
        result = sanitize_text(staged_text)
        result["path"] = relative
        if result["diff"] and apply:
            object_id = _git_output(["hash-object", "-w", "--stdin"], input_data=result["content"].encode("utf-8")).decode().strip()
            index_info = f"{mode} {object_id}\t{relative}\0".encode("utf-8", errors="surrogateescape")
            _git_output(["update-index", "-z", "--index-info"], input_data=index_info)
        results.append(result)
    return results


def _iter_source_files(root: Path):
    if root.is_symlink():
        return
    if root.is_file():
        if root.suffix.lower() in SOURCE_EXTENSIONS:
            yield root
        return
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = [name for name in names if name not in SKIP_DIRS]
        for filename in filenames:
            candidate = Path(directory) / filename
            if candidate.suffix.lower() in SOURCE_EXTENSIONS and not candidate.is_symlink():
                yield candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview conservative SynthScan source cleanups.")
    parser.add_argument("--path", default=".", help="A source file or project directory.")
    parser.add_argument("--staged", action="store_true", help="Read staged file contents from the Git index.")
    parser.add_argument("--apply", action="store_true", help="Apply safe comment-only fixes; staged mode changes the index only.")
    args = parser.parse_args()

    if args.staged:
        results = sanitize_staged(args.apply)
    else:
        requested_path = Path(args.path).expanduser()
        if requested_path.is_symlink():
            parser.error("refusing to sanitize a symbolic-link root")
        root = requested_path.resolve()
        if not root.exists():
            parser.error(f"path does not exist: {root}")
        results = []
        for source_path in _iter_source_files(root):
            try:
                original = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            result = sanitize_text(original)
            result["path"] = str(source_path)
            if result["diff"] and args.apply:
                source_path.write_text(result["content"], encoding="utf-8")
            results.append(result)

    changed = 0
    manual = 0
    for result in results:
        if result["diff"]:
            changed += 1
            sys.stdout.write(result["diff"].replace("a/source", f"a/{result['path']}").replace("b/source", f"b/{result['path']}"))
        for item in result["review_items"]:
            manual += 1
            print(f"[manual review] {result['path']}:{item['line']} {item['rule']}", file=sys.stderr)
    action = "Applied" if args.apply else "Proposed"
    print(f"{action} safe cleanup in {changed} file(s); {manual} manual-review item(s).")


if __name__ == "__main__":
    main()