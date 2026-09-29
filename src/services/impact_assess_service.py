"""AgentCore Platform v1.0"""

# Step 4 — ImpactAssess. Narrative generation with a deterministic fallback,
# same fail-safe prohibited-content filter as the other LLM-generated
# sections (see root_cause_analyze_service.py for the shared rationale).

from __future__ import annotations

from typing import Any

from src.services.breach_event_ingest_service import contains_disallowed_content


def draft_impact_assessment(service_category: str, severity_tier: str, llm: Any = None) -> str:
    fallback = (
        "## Business Impact Assessment\n\n"
        f"**Affected Volume:** Reviewers should document the scope of '{service_category}' "
        "transactions or users affected during the breach period.\n\n"
        "**Downstream Service Impact:** Reviewers should assess whether the breach "
        "propagated to dependent internal services or processes.\n\n"
        f"**Customer-Facing Effect:** Reviewers should assess whether end customers "
        f"experienced a visible impact given the '{severity_tier}' severity of this breach.\n"
    )
    if llm is None:
        return fallback

    prompt = (
        "Draft the 'Business Impact Assessment' section of a formal SLA breach "
        "report. Cover: affected volume, downstream service impact, and "
        "customer-facing effect. Do not mention any employee name or monetary "
        "amount (contract value, penalty amount) — this report must exclude all "
        "such content.\n\n"
        f"Service category: {service_category}\n"
        f"Severity tier: {severity_tier}\n"
    )
    try:
        response = llm.complete([{"role": "user", "content": prompt}])
        text = str(response.get("content", "")) if isinstance(response, dict) else str(response)
    except Exception:
        return fallback

    if not text or contains_disallowed_content(text):
        return fallback
    return text
