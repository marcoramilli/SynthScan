"use strict";

const COMMENT_MARKER = "<!-- synthscan-pr-agent -->";

function escapeCell(value) {
  return String(value ?? "")
    .replace(/[|\r\n]/g, " ")
    .replace(/`/g, "'")
    .trim();
}

function renderComment(report) {
  const risk = report && report.risk_payload;
  if (!risk || typeof risk.overall_score !== "number") {
    throw new Error("SynthScan report is missing risk_payload v1");
  }
  const vectors = Object.entries(risk.vectors || {});
  const vectorRows = vectors.map(([key, vector]) =>
    `| ${escapeCell(vector.label || key)} | ${Number(vector.score || 0).toFixed(1)} | ${escapeCell(vector.severity || "LOW")} | ${Number(vector.finding_count || 0)} |`,
  );
  const findings = (risk.findings || [])
    .filter((finding) => ["HIGH", "CRITICAL"].includes(finding.severity)
      || /hallucination|empty error handler/i.test(finding.category || ""))
    .slice(0, 15);
  const findingRows = findings.length
    ? findings.map((finding) => `- **${escapeCell(finding.severity)}** ${escapeCell(finding.file)}:${Number(finding.line || 0)} ${escapeCell(finding.category)}`).join("\n")
    : "No high-severity findings or targeted hallucination/empty-handler signals.";
  const reviewMinutes = Number(risk.review_time?.estimate_minutes || 0).toFixed(1);

  return [
    COMMENT_MARKER,
    "## SynthScan PR Risk Review",
    `**Heuristic index:** ${risk.overall_score.toFixed(1)}/100 (${escapeCell(risk.overall_severity || "LOW")})  `,
    `**Estimated review effort:** ${reviewMinutes} minutes (uncalibrated heuristic)  `,
    `**Legacy synthetic-code signal:** ${Number(report.synthetic_code_score || 0).toFixed(1)} per 1k LOC`,
    "",
    "These scores are heuristic signals, not probabilities or a judgment of code authorship. Verify flagged changes in context.",
    "",
    "| Risk vector | Index / 100 | Band | Findings |",
    "|---|---:|---|---:|",
    ...vectorRows,
    "",
    "### Findings for human verification",
    findingRows,
    "",
    `_SynthScan ${escapeCell(report.engine_version || "v3 payload")}; ${Number(report.match_count || 0)} total findings._`,
  ].join("\n");
}

module.exports = { COMMENT_MARKER, renderComment };