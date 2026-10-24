"""Heuristic risk-vector mapping for existing SynthScan findings."""

from __future__ import annotations

import hashlib
import math
import os
from collections import Counter


RISK_SCHEMA_VERSION = "1.0.0"
SCORING_VERSION = "heuristic-density-v1"

VECTOR_LABELS = {
    "cognitive_ownership": "Cognitive Ownership Risk",
    "hallucinated_dependency_supply_chain": "Hallucinated Dependency & Supply Chain Risk",
    "agent_over_engineering": "Agent Over-Engineering Ratio",
    "pr_review_velocity_impact": "PR Review Velocity Impact",
}

VECTOR_RATIONALES = {
    "cognitive_ownership": "Commentary, generic scaffolding, and structural signals may make intent harder to establish; they do not prove an author lacks understanding.",
    "hallucinated_dependency_supply_chain": "Suspicious imports, cross-language constructs, and credential placeholders warrant verification; this scanner does not resolve packages or prove a dependency is absent.",
    "agent_over_engineering": "Repeated defensive wrappers and boilerplate can add maintenance surface; individual matches may be intentional.",
    "pr_review_velocity_impact": "A severity-weighted review-time heuristic; it is not calibrated against measured reviewer time.",
}

CATEGORY_VECTORS = {
    "Slop Phrases": ("cognitive_ownership",),
    "AI Slop Vocabulary": ("cognitive_ownership",),
    "Synthetic Comment Markers": ("cognitive_ownership",),
    "Self-Referential Comments": ("cognitive_ownership",),
    "Redundant / Tautological Comments": ("cognitive_ownership",),
    "Verbosity Indicators": ("cognitive_ownership", "pr_review_velocity_impact"),
    "Example Usage Blocks": ("cognitive_ownership", "pr_review_velocity_impact"),
    "Overly Generic Function Names": ("cognitive_ownership",),
    "Docstring Block Structure": ("cognitive_ownership", "pr_review_velocity_impact"),
    "Over-Commented Block": ("cognitive_ownership", "pr_review_velocity_impact"),
    "Fake / Example Data": ("hallucinated_dependency_supply_chain",),
    "Cross-Language Confusion": ("hallucinated_dependency_supply_chain",),
    "Hallucination Indicators": ("hallucinated_dependency_supply_chain",),
    "Unused Imports": ("hallucinated_dependency_supply_chain",),
    "Magic Placeholder Names": ("hallucinated_dependency_supply_chain",),
    "Cross-Language Confusion (JS/TS)": ("hallucinated_dependency_supply_chain",),
    "Excessive Try-Catch Wrapping": ("agent_over_engineering", "pr_review_velocity_impact"),
    "Empty Error Handlers": ("agent_over_engineering", "pr_review_velocity_impact"),
    "Decorative Section Separators": ("agent_over_engineering",),
    "Hyper-Verbose Identifiers": ("cognitive_ownership", "agent_over_engineering"),
    "AI Response Leakage": ("cognitive_ownership",),
    "Modern AI Meta-Vocabulary": ("cognitive_ownership",),
    "TODO Padding": ("cognitive_ownership", "pr_review_velocity_impact"),
    "Structural Annotation Overuse": ("cognitive_ownership",),
    "Modern Structural Boilerplate": ("agent_over_engineering",),
    "AI Structural Patterns": ("cognitive_ownership", "agent_over_engineering"),
    "Cross-File Repetition": ("agent_over_engineering", "pr_review_velocity_impact"),
    "Dead Code": ("agent_over_engineering", "pr_review_velocity_impact"),
    "Deep Nesting": ("cognitive_ownership", "pr_review_velocity_impact"),
}

REVIEW_MINUTES_BY_SEVERITY = {
    "LOW": 0.5,
    "MEDIUM": 1.5,
    "HIGH": 3.0,
    "CRITICAL": 5.0,
}


def _risk_level(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


def _finding_id(match: object) -> str:
    stable_key = "|".join(str(value) for value in (
        getattr(match, "file", ""),
        getattr(match, "line_number", 0),
        getattr(match, "category", ""),
        getattr(match, "pattern_raw", ""),
    ))
    return hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]


def _vector_score(points: float, lines_scanned: int) -> float:
    density = max(0.0, points) * 1000 / max(1, lines_scanned)
    return round(100 * (1 - math.exp(-density / 20)), 2)


def build_risk_payload(result: object, engine_version: str = "unknown", repo_root: str | None = None) -> dict:
    """Build a reproducible risk payload without claiming calibrated risk."""
    matches = list(getattr(result, "matches", []))
    lines_scanned = int(getattr(result, "lines_scanned", 0) or 0)
    vector_matches: dict[str, list[tuple[str, object]]] = {
        vector_id: [] for vector_id in VECTOR_LABELS
    }
    findings = []
    review_minutes = 0.0

    for match in matches:
        finding_id = _finding_id(match)
        category = str(getattr(match, "category", "Unknown"))
        severity = str(getattr(match, "severity", "LOW")).upper()
        vector_ids = list(CATEGORY_VECTORS.get(category, ()))
        if "pr_review_velocity_impact" not in vector_ids:
            vector_ids.append("pr_review_velocity_impact")
        match_file = str(getattr(match, "file", ""))
        if repo_root and match_file:
            match_file = os.path.relpath(match_file, repo_root).replace(os.sep, "/")
        for vector_id in vector_ids:
            vector_matches[vector_id].append((finding_id, match))
        review_minutes += REVIEW_MINUTES_BY_SEVERITY.get(severity, 0.5)
        findings.append({
            "id": finding_id,
            "category": category,
            "severity": severity,
            "file": match_file,
            "line": int(getattr(match, "line_number", 0) or 0),
            "vectors": vector_ids,
            "confidence": "unvalidated",
        })

    vectors = {}
    for vector_id, label in VECTOR_LABELS.items():
        evidence = vector_matches[vector_id]
        points = sum(float(getattr(match, "score", 0) or 0) for _, match in evidence)
        severity_counts = Counter(
            str(getattr(match, "severity", "LOW")).upper() for _, match in evidence
        )
        if vector_id == "pr_review_velocity_impact":
            score_basis = review_minutes
            score = _vector_score(score_basis * 2, lines_scanned)
        else:
            score = _vector_score(points, lines_scanned)
        vectors[vector_id] = {
            "label": label,
            "score": score,
            "severity": _risk_level(score),
            "finding_count": len(evidence),
            "severity_counts": dict(sorted(severity_counts.items())),
            "finding_ids": [finding_id for finding_id, _ in evidence],
            "rationale": VECTOR_RATIONALES[vector_id],
            "calibrated": False,
        }

    overall_score = round(sum(vector["score"] for vector in vectors.values()) / len(vectors), 2)
    return {
        "schema_version": RISK_SCHEMA_VERSION,
        "engine_version": engine_version,
        "scoring_version": SCORING_VERSION,
        "assessment": "heuristic_signal_not_probability",
        "calibrated": False,
        "overall_score": overall_score,
        "overall_severity": _risk_level(overall_score),
        "review_time": {
            "estimate_minutes": round(review_minutes, 1),
            "method": "sum_by_finding_severity_v1",
            "calibrated": False,
        },
        "scan_metadata": {
            "lines_scanned": lines_scanned,
            "files_scanned": int(getattr(result, "files_scanned", 0) or 0),
        },
        "vectors": vectors,
        "findings": findings,
        "unmapped_category_count": sum(
            1 for match in matches
            if str(getattr(match, "category", "Unknown")) not in CATEGORY_VECTORS
        ),
    }