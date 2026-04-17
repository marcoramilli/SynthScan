# Synthetic / AI-Generated Code Patterns

> **This file defines the detection patterns used by SynthScan.**
>
> Each pattern is defined in a fenced block under its category.
> To add new patterns, append them to the appropriate section or create a new `## Category`.
>
> **Severity tags** — prepend a pattern line with `[CRITICAL]`, `[HIGH]`, `[MEDIUM]`, or `[LOW]`
> to override the default severity for that category. If omitted, the category default applies.
>
> **Severity → score mapping:**
> | Tag | Points |
> |-----|--------|
> | CRITICAL | 10 |
> | HIGH | 5 |
> | MEDIUM | 2 |
> | LOW | 1 |
>
> Patterns sourced from [AI-SLOP-Detector Pattern Catalog v3.5.0](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md).

---

## Slop Phrases

Default severity: **LOW**

Common filler phrases and clichés frequently produced by AI code assistants.

```patterns
# Overly verbose or unnecessary comments
It's worth noting that
As an AI language model
Note that this is a simplified
This is a basic implementation
This is a placeholder
For demonstration purposes
# Trivial docstrings
This function does what its name suggests
This method is self-explanatory
# Filler transitions
Let me know if you need
Feel free to modify
Here's a simple example
As mentioned earlier
```

---

## Structural Issues

Default severity: **CRITICAL**

Patterns from [AI-SLOP-Detector: Structural Issues](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#structural-issues).

```patterns
# bare_except — catches all exceptions including SystemExit (CRITICAL)
regex:except\s*:\s*$
# mutable_default_arg — mutable default argument list/dict/set (CRITICAL)
regex:def\s+\w+\s*\(.*=\s*\[\]
regex:def\s+\w+\s*\(.*=\s*\{\}
# star_import — from module import * (HIGH)
[HIGH] regex:from\s+\w[\w.]*\s+import\s+\*
# global_statement — global keyword usage (MEDIUM)
[MEDIUM] regex:^\s*global\s+\w+
```

---

## Placeholder Indicators

Default severity: **HIGH**

Patterns from [AI-SLOP-Detector: Placeholder Indicators](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#placeholder-indicators).

```patterns
# pass_placeholder — function body is only pass (HIGH)
regex:^\s+pass\s*$
# ellipsis_placeholder — function body is only ... (HIGH)
regex:^\s+\.\.\.\s*$
# not_implemented — raise NotImplementedError stub (HIGH)
raise NotImplementedError
# empty_except — except handler with only pass (CRITICAL)
[CRITICAL] regex:except\s+\w[\w.]*(\s+as\s+\w+)?\s*:\s*\n\s+pass\s*$
# return_none_placeholder — return None as only statement (MEDIUM)
[MEDIUM] regex:^\s+return\s+None\s*$
# interface_only_class — class with all-pass bodies (HIGH)
#   (text heuristic: class + multiple pass lines detected by repetitive-structure)
```

---

## Technical Debt Comments

Default severity: **MEDIUM**

```patterns
# todo_comment
regex:#\s*TODO\b
# fixme_comment
regex:#\s*FIXME\b
# xxx_comment
[LOW] regex:#\s*XXX\b
# hack_comment
regex:#\s*HACK\b
# Go variants
regex://\s*TODO\b
regex://\s*FIXME\b
```

---

## Cross-Language Mistakes

Default severity: **HIGH**

AI models trained on multiple languages frequently emit method calls from the wrong language.
Patterns from [AI-SLOP-Detector: Cross-Language Mistakes](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#cross-language-mistakes).

```patterns
# javascript_array_push — .push() used in Python files
regex:\w+\.push\(
# javascript_array_length — .length() used in Python files
regex:\w+\.length\(\)
# java_equals_method — .equals() used in Python files
regex:\w+\.equals\(
# java_tostring_method — .toString() used in Python files
regex:\w+\.toString\(\)
# ruby_each — .each {} iterator in non-Ruby context
regex:\.\s*each\s*\{
# go_print — fmt.Println() in non-Go files
[MEDIUM] fmt.Println(
# csharp_length — .Length property in Python files
[MEDIUM] regex:\w+\.Length\b
# php_strlen — strlen() in non-PHP files
[MEDIUM] regex:\bstrlen\s*\(
```

---

## Python Advanced

Default severity: **HIGH**

Structural patterns from [AI-SLOP-Detector v2.8.0+](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#python-advanced).

```patterns
# dead_code — statements after return / raise / break / continue (MEDIUM)
[MEDIUM] regex:^\s+(return|raise|break|continue)\b.*\n\s+\S
# deep_nesting — excessive indentation depth (proxy for control-flow depth > 4)
regex:^(\s{20,})\S
# lint_escape — bare noqa silencing ALL warnings (HIGH)
regex:#\s*noqa\s*$
# lint_escape — targeted noqa (LOW)
[LOW] regex:#\s*noqa:\s*\w+
# lint_escape — type: ignore (MEDIUM)
[MEDIUM] regex:#\s*type:\s*ignore
# lint_escape — pylint: disable (MEDIUM)
[MEDIUM] regex:#\s*pylint:\s*disable=
# noinspection (MEDIUM)
[MEDIUM] regex:#\s*noinspection\b
```

---

## Placeholder Variable Naming

Default severity: **HIGH**

Variables named with placeholder/dummy names in production code.
Pattern from [AI-SLOP-Detector v3.1.0](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#placeholder_variable_naming).

```patterns
# placeholder_variable_naming — dummy/temp variable names
regex:\b(tmp|temp|dummy|foo|bar|baz)\s*=
# Numbered data/result variables (data2, result3, …)
regex:\b(data|result|value|item|obj|var)\d+\s*=
```

---

## Return Constant Stub

Default severity: **HIGH**

Function always returns the same hardcoded constant — classic AI stub.
Pattern from [AI-SLOP-Detector v3.1.0](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#return_constant_stub).

```patterns
# return_constant_stub — return 0 / return 42 / return "" / return True / return False
regex:^\s+return\s+(0|42|True|False|""|''|\[\]|\{\})\s*$
```

---

## Clone Detection Heuristics

Default severity: **HIGH**

Text-level heuristics for copy-pasted code.
Inspired by [AI-SLOP-Detector v3.1.0 Clone Detection](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#clone-detection).

```patterns
# Copy-paste function signatures differing only by a digit
regex:def\s+(\w+?)_?\d+\s*\(
# Repetitive numbered variables (var1, var2, var3 …)
regex:(\w+)[1-9]\s*=.*\n\s*\1[1-9]\s*=.*\n\s*\1[1-9]\s*=
# Excessive chained elif / else if blocks with similar bodies
regex:(elif|else\s+if)\s+.*:\s*\n(\s+.*\n){1,3}\s*(elif|else\s+if)\s+.*:\s*\n(\s+.*\n){1,3}\s*(elif|else\s+if)
```

---

## Synthetic Comment Markers

Default severity: **HIGH**

Comments that reveal AI authorship or templated generation.

```patterns
# Direct AI attribution
Generated by AI
Generated by GPT
Generated by Copilot
Generated by Claude
Generated by Gemini
Auto-generated code
This code was generated
AI-generated
written by an AI
# Template markers
[MEDIUM] BEGIN GENERATED CODE
[MEDIUM] END GENERATED CODE
AUTO-GENERATED - DO NOT EDIT
This file is auto-generated
Do not modify this file manually
```

---

## Hallucination Indicators (Phantom Import Heuristics)

Default severity: **CRITICAL**

Text-level heuristics for hallucinated imports.
Inspired by [AI-SLOP-Detector v2.9.0 Phantom Import](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#phantom-import).

```patterns
# Suspicious deeply-nested import paths (common AI hallucinations)
regex:from\s+\w+\.utils\.helpers\s+import\s+\w+
regex:from\s+\w+\.core\.exceptions\s+import\s+\w+Error
# Non-standard config references
[HIGH] regex:config\[['"](?:API_KEY|SECRET_KEY|DATABASE_URL)['"]\]
```

---

## Verbosity Indicators

Default severity: **LOW**

Phrases that signal unnecessarily verbose or over-explained code.

```patterns
# Over-explanation in comments
This line initializes
This variable stores
We need to check if
The purpose of this function is
The following code block
This section handles
Step 1:
Step 2:
Step 3:
```

---

## JavaScript / TypeScript

Default severity: **HIGH**

Patterns from [AI-SLOP-Detector v3.4.0 JS/TS](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#javascript--typescript).

```patterns
# console_log_debug — leftover console.log / debug / warn (MEDIUM)
[MEDIUM] regex:console\.(log|debug|warn)\s*\(
# any_type_cast — TypeScript 'as any' or ': any' type erasure (HIGH)
regex:\bas\s+any\b
regex::\s*any\b
# disabled_test — .skip / .todo / .only / xit / xtest in test files (HIGH)
regex:\b(describe|it|test)\.(skip|todo|only)\b
regex:\b(xit|xtest|xdescribe)\s*\(
# promise_ignore — unhandled async without await or .catch (HIGH)
regex:(?<!await\s)\b\w+\(.*\)\s*;\s*$
```

---

## Go

Default severity: **HIGH**

Patterns from [AI-SLOP-Detector v3.5.0 Go](https://github.com/flamehaven01/AI-SLOP-Detector/blob/main/docs/PATTERNS.md#go).

```patterns
# error_discard — _ = fn() silently discards error return (CRITICAL)
[CRITICAL] regex:_\s*=\s*\w[\w.]*\(
# empty_select — select {} blocks forever (HIGH)
regex:select\s*\{\s*\}
# unused_goroutine — go func() with no channel/sync (HIGH)
regex:go\s+func\s*\(
```

---

## AI Slop Vocabulary

Default severity: **MEDIUM**

Distinctive words and phrases LLMs disproportionately overuse in comments, docstrings,
and string literals. Individually low signal, but clusters of these are a strong
indicator of AI authorship.

```patterns
# High-frequency AI slop words (MEDIUM when found in code comments)
regex:#.*\b(delve|tapestry|multifaceted|nuanced|streamlined)\b
regex:#.*\b(leverage|utilize|utilize|facilitate|comprehensive)\b
regex:#.*\b(robust|seamless|cutting-edge|state-of-the-art|paradigm)\b
regex:#.*\b(aforementioned|henceforth|pertaining to|in conjunction with)\b
regex:#.*\b(endeavor|pivotal|intricate|meticulous|holistic)\b
# Phrases in docstrings / multi-line strings
regex:""".*\b(delve into|it's important to note|in order to)\b
regex:""".*\b(at the end of the day|a testament to|serves as a)\b
# Overly enthusiastic adverbs in comments
regex:#.*\b(Certainly|Absolutely|Definitely|Essentially|Fundamentally)\b
# "Simply" / "just" — oversimplification markers
[LOW] regex:#.*\b(simply|just)\s+(call|use|add|set|pass|create|return)\b
```

---

## Cross-Language Value Confusion

Default severity: **HIGH**

AI models frequently emit literals or operators from the wrong language.

```patterns
# null / undefined in Python (should be None)
regex:\b(null|undefined)\s*[;)}\],]
regex:\bif\s+\w+\s*(==|!=|is)\s*null\b
# true/false (lowercase) in Python (should be True/False)
regex:\breturn\s+(true|false)\s*$
regex:\bif\s+.*\b(true|false)\b
# Logical operators from C/JS in Python (should be and/or/not)
regex:\s&&\s
regex:\s\|\|\s
regex:\s!=\s*null\b
# Python-style in JavaScript/TypeScript (None, True, False)
[MEDIUM] regex:\b(None|True|False)\b.*[;]$
# Semicolons in Python (not needed)
[LOW] regex:^[^#"']*\w[^#"']*;\s*$
```

---

## Fake / Example Data

Default severity: **MEDIUM**

Hardcoded placeholder data that AI models insert as "examples" and developers forget to replace.

```patterns
# Names / emails / addresses
regex:['"]John\s+Doe['"]
regex:['"]Jane\s+Doe['"]
regex:['"]john[.@]example\.com['"]
regex:['"]jane[.@]example\.com['"]
regex:['"]user@example\.com['"]
regex:['"]admin@example\.com['"]
regex:['"]test@test\.com['"]
regex:['"]foo@bar\.com['"]
regex:['"]123\s+Main\s+St(reet)?['"]
regex:['"]Acme\s+(Corp|Inc|Ltd)['"]
# Lorem ipsum / placeholder text
Lorem ipsum
dolor sit amet
# Phone number placeholders
regex:['"]555-\d{4}['"]
regex:['"]\+1[-.\s]?555[-.\s]?\d{3}[-.\s]?\d{4}['"]
# Example URLs
regex:['"]https?://example\.com
regex:['"]https?://api\.example\.com
regex:['"]https?://localhost:\d+['"]
```

---

## Security Anti-Patterns

Default severity: **CRITICAL**

Hardcoded secrets, dangerous functions, and insecure defaults commonly emitted by AI.

```patterns
# Hardcoded passwords / tokens / secrets
regex:(password|passwd|pwd)\s*=\s*['"][^'"]{4,}['"]
regex:(api_key|apikey|api_token|secret_key|auth_token)\s*=\s*['"][^'"]{4,}['"]
regex:(access_token|private_key)\s*=\s*['"][^'"]{4,}['"]
# Dangerous eval / exec
[CRITICAL] regex:\beval\s*\(
[CRITICAL] regex:\bexec\s*\(
# Insecure HTTP (should be HTTPS)
[HIGH] regex:['"]http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)
# Disabled SSL verification
[CRITICAL] regex:verify\s*=\s*False
# Shell injection — subprocess with shell=True
[HIGH] regex:subprocess\.\w+\(.*shell\s*=\s*True
# Hardcoded IP addresses (non-localhost)
[MEDIUM] regex:['"](?!127\.0\.0\.1|0\.0\.0\.0|localhost)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}['"]
# SQL string concatenation (injection risk)
[HIGH] regex:['"]SELECT\s+.*['"]\s*\+\s*\w+
[HIGH] regex:['"]INSERT\s+INTO\s+.*['"]\s*\+\s*\w+
[HIGH] regex:f['"]SELECT\s+.*\{
[HIGH] regex:f['"]INSERT\s+INTO\s+.*\{
```

---

## Overly Generic Function Names

Default severity: **LOW**

Function names so generic they indicate AI-generated scaffolding rather than
domain-specific design.

```patterns
regex:def\s+(process_data|handle_request|do_something|do_stuff)\s*\(
regex:def\s+(run_task|execute_task|perform_action|main_function)\s*\(
regex:def\s+(helper|my_function|my_method|test_function)\s*\(
regex:def\s+(get_data|set_data|update_data|delete_data)\s*\(
regex:function\s+(processData|handleRequest|doSomething|getData)\s*\(
regex:func\s+(processData|handleRequest|doSomething)\s*\(
```

---

## Example Usage Blocks

Default severity: **LOW**

AI assistants almost always append "Example usage:" blocks at the bottom of generated code.

```patterns
# Example-usage header comments
regex:#\s*(Example\s+usage|Usage\s+example|Sample\s+usage|How\s+to\s+use)\s*:?\s*$
regex://\s*(Example\s+usage|Usage\s+example)\s*:?\s*$
regex:#\s*Usage:\s*$
# if __name__ with print-only demo
[LOW] regex:if\s+__name__\s*==\s*['"]__main__['"]:\s*$
```

---

## Self-Referential Comments

Default severity: **LOW**

Comments that narrate what the code is rather than why — a strong AI tell.

```patterns
# "This X does Y" tautologies
regex:#\s*This\s+(class|function|method|module|file)\s+(is|provides|represents|implements|handles|contains|defines)
regex:#\s*The\s+(following|above|below)\s+(class|function|method|code|block|section)
regex:"""This\s+(class|function|method|module)\s+(is|provides|represents|implements)
# Narrating the obvious
regex:#\s*(Import|Importing)\s+(the\s+)?(necessary|required|needed)\s+(modules|libraries|packages|dependencies)
regex:#\s*(Define|Defining|Create|Creating)\s+(the\s+)?(main|a|an|the)\s+\w+
regex:#\s*(Initialize|Initializing)\s+(the\s+)?\w+\s+(variable|object|instance|class)
```

---

## Redundant / Tautological Comments

Default severity: **LOW**

Comments that restate the code verbatim — a hallmark of LLM generation.

```patterns
# Increment / assignment restatements
regex:#\s*(Set|Assign)\s+\w+\s+to\s+
regex:#\s*(Increment|Decrement)\s+\w+(\s+by\s+\d+)?\s*$
regex:#\s*Return\s+(the\s+)?(result|value|output|data)\s*$
regex:#\s*(Loop|Iterate)\s+(through|over)\s+(the\s+)?(list|array|items|elements|data)
regex:#\s*(Check|Verify)\s+if\s+
regex:#\s*(Print|Display|Output)\s+(the\s+)?(result|value|output|message)
regex:#\s*(Open|Close|Read|Write)\s+(the\s+)?file
regex:#\s*(Add|Append|Push|Insert)\s+(the\s+)?\w+\s+(to|into)\s+(the\s+)?(list|array|queue|stack)
```

---

## Rust Specific

Default severity: **HIGH**

Common AI-generated Rust anti-patterns.

```patterns
# Excessive unwrap() chains — panics in production
regex:\.unwrap\(\)\..*\.unwrap\(\)
# Single unwrap (lower severity)
[MEDIUM] regex:\.unwrap\(\)\s*[;.]
# todo!() / unimplemented!() macros left in code
regex:\btodo!\s*\(
regex:\bunimplemented!\s*\(
# expect() with unhelpful messages
[MEDIUM] regex:\.expect\s*\(\s*["'](?:error|failed|something went wrong|todo)["']\s*\)
# clone() overuse (AI tends to .clone() everything)
[LOW] regex:\.clone\(\)\..*\.clone\(\)
```

---

## Java / C# / Kotlin Specific

Default severity: **HIGH**

```patterns
# @SuppressWarnings — hiding issues instead of fixing them
regex:@SuppressWarnings\s*\(
# Empty catch block in Java/C#/Kotlin
[CRITICAL] regex:catch\s*\([^)]*\)\s*\{\s*\}
# System.out.println debugging leftover
[MEDIUM] regex:System\.out\.print(ln)?\s*\(
# Kotlin TODO()
regex:\bTODO\(\s*["']
# C# pragma warning disable
[MEDIUM] regex:#pragma\s+warning\s+disable
# Java main method with trivial body
[LOW] regex:public\s+static\s+void\s+main\s*\(\s*String\s*\[\s*\]\s*(args)?\s*\)
```

---

## Excessive Try-Catch Wrapping

Default severity: **MEDIUM**

AI models tend to wrap every operation in try/except with generic error messages.

```patterns
# Generic exception message echoing the function name
regex:except\s+Exception\s+as\s+\w+:\s*\n\s+print\(
regex:except\s+Exception\s+as\s+\w+:\s*\n\s+return\s+None
# Bare "Error:" prefix (AI-typical)
regex:print\s*\(\s*f?['"]Error:?\s
regex:print\s*\(\s*f?['"]An error occurred
regex:print\s*\(\s*f?['"]Something went wrong
# Logging the exception but re-raising nothing
[LOW] regex:except\s+\w+.*:\s*\n\s+logging\.\w+\(.*\)\s*$
```

---

## How to Add New Patterns

1. Create a new `## Category` heading and optionally state a default severity.
2. Add a fenced code block tagged as ` ```patterns `.
3. Put one pattern per line.  
   - Plain text lines are matched as **case-insensitive substrings**.  
   - Lines starting with `regex:` are compiled as **Python regular expressions**.
   - Prepend `[CRITICAL]`, `[HIGH]`, `[MEDIUM]`, or `[LOW]` to override the category default.
4. Comment lines starting with `#` inside the block are ignored.
5. Commit and push — the action will pick up new patterns automatically.
