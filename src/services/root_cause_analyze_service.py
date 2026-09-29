"""AgentCore Platform v1.0"""

# Step 3 — RootCauseAnalyze. Narrative generation (not a legal/financial
# decision) — LLM is appropriate here, with a deterministic fallback
# template when no LLM is configured (IMPLEMENTATION_LOG.md B5 pattern).
# Any LLM output containing an employee name or monetary value is discarded
# fail-safe (applies a ruling-language filter to this template's own
# prohibited-content class).

from __future__ import annotations

from typing import Any

from src.services.breach_event_ingest_service import contains_disallowed_content


def draft_root_cause(metric_name: str, service_category: str, severity_tier: str, llm: Any = None) -> str:
    fallback = (
        "## Root Cause Analysis\n\n"
        f"**Immediate Cause:** The '{metric_name}' metric for '{service_category}' "
        f"deviated from the contracted SLA threshold, triggering a '{severity_tier}' "
        "severity breach.\n\n"
        "**Contributing Factors:** Reviewers should document process, staffing, or "
        "technical factors that contributed to the deviation.\n\n"
        "**Systemic Factors:** Reviewers should assess whether this reflects a "
        "recurring or structural issue in the vendor's service delivery process.\n"
    )
    if llm is None:
        return fallback

    prompt = (
        "Draft the 'Root Cause Analysis' section of a formal SLA breach report. "
        "Structure it in three layers: immediate cause, contributing factors, "
        "systemic factors. Do not mention any employee name or monetary amount "
        "(contract value, penalty amount) — this report must exclude all such "
        "content.\n\n"
        f"Metric: {metric_name}\n"
        f"Service category: {service_category}\n"
        f"Severity tier: {severity_tier}\n"
    )
    try:
        response = llm.complete([{"role": "user", "content": prompt}])
        text = str(response.get("content", "")) if isinstance(response, dict) else str(response)
    except Exception:
        return fallback

    if not text or contains_disallowed_content(text):
        # Fail-safe: discard LLM output entirely rather than risk shipping
        # a leaked employee name or monetary value.
        return fallback
    return text
