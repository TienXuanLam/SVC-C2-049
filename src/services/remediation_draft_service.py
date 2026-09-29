"""AgentCore Platform v1.0"""

# Step 5 — RemediationDraft. Narrative generation with a deterministic
# fallback, same fail-safe prohibited-content filter as the other
# LLM-generated sections. Never states a specific penalty/credit monetary
# amount — that is a contractual calculation out of scope for this template
# (proposal §4 scope note).

from __future__ import annotations

from typing import Any

from src.services.breach_event_ingest_service import contains_disallowed_content


def _credit_eligibility_text(credit_eligible: bool, severity_policy_verified: bool) -> str:
    # prior design review M2: severity_thresholds/credit_eligible_tiers are shipped
    # illustrative defaults, not a verified institution policy, until
    # severity_policy_verified is explicitly attested in config.yaml. An
    # unverified policy must not be presented as a credit-eligibility
    # determination — render it as a contract-manager question instead.
    # Deliberately computed here (not delegated to the LLM prompt below) so
    # this exact wording is guaranteed regardless of whether an `llm` is
    # configured — see draft_remediation_plan()'s docstring note.
    if not severity_policy_verified:
        return (
            "**Credit Eligibility:** Requires contract-manager determination — the "
            "configured severity-tier thresholds are illustrative defaults, not yet "
            "attested as calibrated against this vendor's actual SLA contract terms "
            "(see docs/07_operation_guide.md 'Severity Threshold Setup').\n"
        )
    if credit_eligible:
        return (
            "**Credit Eligibility:** This breach is flagged as credit-eligible under "
            "the SLA contract terms; the specific credit amount is a contractual "
            "calculation outside the scope of this report.\n"
        )
    return (
        "**Credit Eligibility:** This breach is not flagged as credit-eligible under the configured severity tiers.\n"
    )


def draft_remediation_plan(
    severity_tier: str, credit_eligible: bool, severity_policy_verified: bool, llm: Any = None
) -> str:
    """Drafts corrective-actions/timeline/KPI/recurrence-prevention narrative.

    The Credit Eligibility line is ALWAYS appended deterministically after
    the narrative body (fallback or LLM-generated) — it is never delegated
    to the LLM, so an LLM cannot bypass the severity_policy_verified gate
    (prior design review M2) by asserting a credit-eligibility determination on its
    own.
    """
    credit_eligibility_text = _credit_eligibility_text(credit_eligible, severity_policy_verified)

    fallback_body = (
        "## Remediation Plan\n\n"
        f"**Corrective Actions:** Vendor should propose specific corrective actions "
        f"proportionate to this '{severity_tier}' severity breach.\n\n"
        "**Timeline:** A remediation timeline with milestones should be agreed with "
        "the vendor.\n\n"
        "**KPI Targets:** Post-remediation KPI targets should be defined to confirm "
        "the corrective actions are effective.\n\n"
        "**Recurrence Prevention:** Vendor should document process changes intended "
        "to prevent recurrence.\n"
    )
    if llm is None:
        return fallback_body + "\n" + credit_eligibility_text

    prompt = (
        "Draft the 'Remediation Plan' section of a formal SLA breach report. Cover ONLY: "
        "corrective actions, timeline, KPI targets, and recurrence prevention measures. "
        "Do not state a specific monetary penalty or credit amount, do not mention any "
        "employee name, and do not make any statement about credit eligibility — that is "
        "appended separately by this system, not by you.\n\n"
        f"Severity tier: {severity_tier}\n"
    )
    try:
        response = llm.complete([{"role": "user", "content": prompt}])
        text = str(response.get("content", "")) if isinstance(response, dict) else str(response)
    except Exception:
        return fallback_body + "\n" + credit_eligibility_text

    if not text or contains_disallowed_content(text):
        return fallback_body + "\n" + credit_eligibility_text
    return text + "\n" + credit_eligibility_text
