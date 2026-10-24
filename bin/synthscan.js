#!/usr/bin/env node
"use strict";

const { execFileSync, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const SCANNER = path.join(ROOT, "scanner", "synthscan.py");
const SEVERITY_RANK = { LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 };

function printHelp() {
    process.stdout.write([
        "SynthScan - synthetic-code signal and engineering-risk audit",
        "",
        "Usage:",
        "  synthscan [directory] [scanner options]",
        "  synthscan --scan-path ./src",
        "  synthscan --staged",
        "  synthscan --diff-base origin/main [--ci]",
        "  synthscan sanitize --path ./src [--apply]",
        "  synthscan serve [--host 127.0.0.1] [--port 8765]",
        "",
        "Options:",
        "  --diff-base REF       Scan lines added since REF...HEAD",
        "  --staged              Scan staged Git changes only",
        "  --ci                  Exit 1 for HIGH or CRITICAL heuristic risk",
        "  --fail-on LEVEL       CI severity threshold",
        "  --risk-threshold N    Exit 1 when the 0-100 heuristic score reaches N",
        "  --output-json PATH    Write the JSON report to PATH",
        "  --json                Print JSON instead of the terminal summary",
        "  --help                Show this help",
        "",
    ].join("\n"));
}

function parseArgs(args) {
    const options = { scannerArgs: [], json: false, ci: false, staged: false };
    for (let index = 0; index < args.length; index += 1) {
        const arg = args[index];
        if (arg === "--help" || arg === "-h") {
            printHelp();
            process.exit(0);
        }
        if (arg === "--json") {
            options.json = true;
            continue;
        }
        if (arg === "--ci") {
            options.ci = true;
            continue;
        }
        if (arg === "--staged") {
            options.staged = true;
            continue;
        }
        if (["--diff-base", "--risk-threshold", "--fail-on", "--output-json"].includes(arg)) {
            const value = args[index + 1];
            if (!value || value.startsWith("--")) throw new Error(`${arg} requires a value`);
            index += 1;
            if (arg === "--diff-base") options.diffBase = value;
            if (arg === "--risk-threshold") {
                options.riskThreshold = Number(value);
                if (!Number.isFinite(options.riskThreshold) || options.riskThreshold < 0 || options.riskThreshold > 100) {
                    throw new Error("--risk-threshold must be between 0 and 100");
                }
            }
            if (arg === "--fail-on") {
                options.failOn = value.toUpperCase();
                if (!(options.failOn in SEVERITY_RANK)) throw new Error("--fail-on must be LOW, MEDIUM, HIGH, or CRITICAL");
            }
            if (arg === "--output-json") options.outputJson = value;
            continue;
        }
        if (!arg.startsWith("-") && options.scannerArgs.length === 0) {
            options.scannerArgs.push("--scan-path", arg);
        } else {
            options.scannerArgs.push(arg);
        }
    }
    if (options.staged && options.diffBase) throw new Error("Use either --staged or --diff-base, not both");
    if (options.ci && !options.failOn && options.riskThreshold === undefined) options.failOn = "HIGH";
    return options;
}

function runGit(args) {
    return execFileSync("git", args, { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
}

function createStagedSnapshot(tempDir) {
    const snapshot = path.join(tempDir, "staged-source");
    const names = runGit(["diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z"]).split("\0").filter(Boolean);
    for (const name of names) {
        const targetPath = path.resolve(snapshot, name);
        const relative = path.relative(snapshot, targetPath);
        if (relative.startsWith(`..${path.sep}`) || relative === ".." || path.isAbsolute(relative)) {
            throw new Error(`Unsafe staged path: ${name}`);
        }
        let stagedContent;
        try {
            stagedContent = execFileSync("git", ["show", `:${name}`], { encoding: null, maxBuffer: 4 * 1024 * 1024 });
        } catch {
            continue;
        }
        fs.mkdirSync(path.dirname(targetPath), { recursive: true });
        fs.writeFileSync(targetPath, stagedContent);
    }
    return snapshot;
}

function runPython(script, args, capture) {
    const candidates = process.env.PYTHON ? [process.env.PYTHON] : ["python3", "python"];
    for (const command of candidates) {
        const result = spawnSync(command, [script, ...args], {
            cwd: process.cwd(),
            encoding: "utf8",
            maxBuffer: 32 * 1024 * 1024,
            stdio: capture ? "pipe" : "inherit",
        });
        if (!result.error) {
            if (capture && result.stderr) process.stderr.write(result.stderr);
            return capture ? result : { status: result.status, error: result.error };
        }
        if (result.error.code !== "ENOENT") throw result.error;
    }
    throw new Error("Python 3 is required to run SynthScan");
}

function runSubcommand(args) {
    if (args[0] === "sanitize") return runPython(path.join(ROOT, "scanner", "sanitize.py"), args.slice(1), false).status ?? 1;
    if (args[0] === "serve") return runPython(path.join(ROOT, "scanner", "api.py"), args.slice(1), false).status ?? 1;
    return undefined;
}

function scan() {
    const rawArgs = process.argv.slice(2);
    const subcommandStatus = runSubcommand(rawArgs);
    if (subcommandStatus !== undefined) {
        process.exitCode = subcommandStatus;
        return;
    }
    const options = parseArgs(rawArgs);
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "synthscan-cli-"));
    try {
        const scannerArgs = options.scannerArgs.slice();
        const filteredArgs = [];
        for (let index = 0; index < scannerArgs.length; index += 1) {
            if (["--format", "--report-path"].includes(scannerArgs[index])) {
                index += 1;
            } else {
                filteredArgs.push(scannerArgs[index]);
            }
        }
        if (options.staged || options.diffBase) {
            const diffArgs = options.staged
                ? ["diff", "--cached", "--binary", "--no-ext-diff"]
                : ["diff", "--binary", "--no-ext-diff", `${options.diffBase}...HEAD`];
            const diffPath = path.join(tempDir, "changes.diff");
            fs.writeFileSync(diffPath, runGit(diffArgs), "utf8");
            filteredArgs.push("--diff-file", diffPath);
        }
        if (options.staged) {
            const scanPath = createStagedSnapshot(tempDir);
            for (let index = filteredArgs.length - 1; index >= 0; index -= 1) {
                if (filteredArgs[index] === "--scan-path") filteredArgs.splice(index, 2);
            }
            filteredArgs.push("--scan-path", scanPath);
        }
        const reportPath = path.join(tempDir, "report.json");
        filteredArgs.push("--format", "json", "--report-path", reportPath);
        const result = runPython(SCANNER, filteredArgs, true);
        if (result.error) throw result.error;
        if (!fs.existsSync(reportPath)) {
            if (result.stderr) process.stderr.write(result.stderr);
            throw new Error(`Scanner exited ${result.status} without creating a JSON report`);
        }
        const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
        if (options.outputJson) fs.writeFileSync(path.resolve(options.outputJson), `${JSON.stringify(report, null, 2)}\n`);
        if (options.json) process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
        else renderSummary(report);
        if (result.status !== 0) process.exitCode = result.status || 1;
        else if (shouldFail(report, options)) process.exitCode = 1;
    } finally {
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
}

function renderSummary(report) {
    const risk = report.risk_payload || {};
    process.stdout.write(`SynthScan signal: ${report.synthetic_code_score ?? "n/a"} per 1k LOC · ${report.match_count ?? 0} findings\n`);
    process.stdout.write(`Risk index: ${risk.overall_score ?? "n/a"}/100 (${risk.overall_severity ?? "unavailable"}) · heuristic, uncalibrated\n`);
    for (const [key, vector] of Object.entries(risk.vectors || {})) {
        process.stdout.write(`  ${vector.label || key}: ${vector.score ?? "n/a"}/100 (${vector.severity || "n/a"}, ${vector.finding_count ?? 0} findings)\n`);
    }
    const findings = (risk.findings || []).slice(0, 12);
    if (findings.length) {
        process.stdout.write("\nFindings for human verification:\n");
        for (const finding of findings) {
            process.stdout.write(`  ${finding.severity || "LOW"} ${finding.file || ""}:${finding.line || 0} ${finding.category || "Finding"}\n`);
        }
    }
}

function shouldFail(report, options) {
    const risk = report.risk_payload;
    if (options.riskThreshold !== undefined) {
        if (typeof risk?.overall_score !== "number") throw new Error("Risk threshold requested, but report has no risk_payload");
        if (risk.overall_score >= options.riskThreshold) return true;
    }
    if (options.failOn) {
        const severity = risk?.overall_severity;
        if (!severity || !(severity in SEVERITY_RANK)) throw new Error("Severity gate requested, but report has no valid overall_severity");
        if (SEVERITY_RANK[severity] >= SEVERITY_RANK[options.failOn]) return true;
    }
    return false;
}

try {
    scan();
} catch (error) {
    process.stderr.write(`SynthScan: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
}
