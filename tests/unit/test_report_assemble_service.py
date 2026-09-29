# SVC-C2-049 — Unit Tests: report_assemble_service (step 6)

from src.services.report_assemble_service import assemble_report


def _assemble(**overrides) -> str:
    kwargs = dict(
        metric_name="uptime",
        threshold=99.9,
        actual_value=95.0,
        metric_direction="higher_is_better",
        breach_period="2026-06-01 to 2026-06-30",
        service_category="hosting",
        severity_tier="major",
        credit_eligible=True,
        severity_policy_verified=True,
        classification_rationale="Matched major severity keywords.",
        root_cause_section="## Root Cause Analysis\n\nSample text.",
        impact_section="## Business Impact Assessment\n\nSample text.",
        remediation_section="## Remediation Plan\n\nSample text.",
    )
    kwargs.update(overrides)
    return assemble_report(**kwargs)


class TestAssembleReport:
    def test_report_contains_all_mandatory_sections(self):
        report = _assemble()
        assert "Executive Summary" in report
        assert "Breach Detail" in report
        assert "Root Cause Analysis" in report
        assert "Business Impact Assessment" in report
        assert "Remediation Plan" in report
        assert "Next Review Date" in report
        assert "uptime" in report
        assert "higher_is_better" in report

    def test_report_reflects_credit_eligibility_when_policy_verified(self):
        eligible = _assemble(severity_tier="critical", credit_eligible=True, severity_policy_verified=True)
        assert "credit-eligible" in eligible.lower()
        assert "requires contract-manager determination" not in eligible.lower()

    def test_report_hedges_credit_eligibility_when_policy_unverified(self):
        # prior design review M2: shipped illustrative defaults must not be presented
        # as a credit-eligibility determination anywhere in the report.
        report = _assemble(severity_tier="critical", credit_eligible=True, severity_policy_verified=False)
        assert "requires contract-manager determination" in report.lower()
        assert "this breach is flagged as credit-eligible" not in report.lower()

    def test_credit_eligible_detail_field_hedged_when_unverified(self):
        report = _assemble(credit_eligible=True, severity_policy_verified=False)
        assert "**Credit Eligible:** requires contract-manager determination" in report
        assert "**Credit Eligible:** True" not in report
