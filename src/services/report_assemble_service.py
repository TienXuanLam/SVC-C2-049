"""AgentCore Platform v1.0"""

# Step 6 — ReportAssemble. Deterministic Markdown assembly of all
# ITIL4/ISO 20000-aligned sections. No employee name, contract value, or
# penalty amount appears here — only the caller-supplied breach metrics.

from __future__ import annotations


def assemble_report(
    metric_name: str,
    threshold: float,
    actual_value: float,
    metric_direction: str,
    breach_period: str,
    service_category: str,
    severity_tier: str,
    credit_eligible: bool,
    severity_policy_verified: bool,
    classification_rationale: str,
    root_cause_section: str,
    impact_section: str,
    remediation_section: str,
) -> str:
    # prior design review M2: an unverified/illustrative severity policy must not be
    # presented as a credit-eligibility determination anywhere in the
    # report, including the Executive Summary and Breach Detail fields —
    # not just the Remediation Plan section (remediation_draft_service.py
    # already gates its own section independently; this gates the other two
    # surfaces so the same guarantee holds end to end).
    if severity_policy_verified:
        credit_summary_sentence = (
            "This breach is flagged as credit-eligible."
            if credit_eligible
            else "This breach is not flagged as credit-eligible."
        )
        credit_detail_value = str(credit_eligible)
    else:
        credit_summary_sentence = "Credit eligibility requires contract-manager determination."
        credit_detail_value = "requires contract-manager determination (unverified severity policy)"

    return (
        "# SLA Breach Report Draft\n\n"
        "## Executive Summary\n\n"
        f"A '{severity_tier}' severity SLA breach was recorded for the "
        f"'{service_category}' service during {breach_period}. "
        f"{credit_summary_sentence}\n\n"
        "## Breach Detail\n\n"
        f"- **Metric:** {metric_name}\n"
        f"- **Metric Direction:** {metric_direction}\n"
        f"- **Threshold:** {threshold}\n"
        f"- **Actual Value:** {actual_value}\n"
        f"- **Breach Period:** {breach_period}\n"
        f"- **Service Category:** {service_category}\n"
        f"- **Severity Tier:** {severity_tier}\n"
        f"- **Credit Eligible:** {credit_detail_value}\n"
        f"- **Classification Rationale:** {classification_rationale}\n\n"
        f"{root_cause_section}\n\n"
        f"{impact_section}\n\n"
        f"{remediation_section}\n\n"
        "## Next Review Date\n\n"
        "A follow-up review should be scheduled per the vendor governance "
        "framework to confirm remediation effectiveness.\n"
    )
