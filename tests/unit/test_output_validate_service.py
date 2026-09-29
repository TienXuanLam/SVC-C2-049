# SVC-C2-049 — Unit Tests: output_validate_service (step 7 — S-3 belt-and-suspenders)

from src.services.output_validate_service import (
    MANDATORY_DISCLAIMER,
    attach_disclaimer,
    find_prohibited_content_violations,
)


class TestFindProhibitedContentViolations:
    def test_clean_report_has_no_violations(self):
        report = (
            "# SLA Breach Report Draft\n\n"
            "## Executive Summary\n\n"
            "A minor breach was recorded for the hosting service.\n\n"
            "- **Service Category:** hosting\n"
        )
        assert find_prohibited_content_violations(report) == []

    def test_leaked_name_detected(self):
        report = "Reported by Jane Doe, the breach was significant."
        violations = find_prohibited_content_violations(report)
        assert any("name" in v for v in violations)

    def test_leaked_money_symbol_detected(self):
        report = "The penalty is $50,000 as per contract."
        violations = find_prohibited_content_violations(report)
        assert any("monetary" in v for v in violations)

    def test_leaked_money_word_detected(self):
        report = "The penalty is 50000 yen as per contract."
        violations = find_prohibited_content_violations(report)
        assert any("monetary" in v for v in violations)

    def test_leaked_japanese_detected(self):
        report = "担当者は山田太郎です。"
        violations = find_prohibited_content_violations(report)
        assert any("Japanese" in v for v in violations)

    def test_own_heading_not_false_positive(self):
        # Regression test for a lesson from an earlier project — this template's
        # own multi-word headings/labels must never be flagged.
        report = "- **Service Category:** hosting\n- **Breach Period:** 2026-06\n"
        assert find_prohibited_content_violations(report) == []

    def test_title_case_category_masked_by_platform_not_flagged_here(self):
        # Confirms this service's own scan doesn't itself flag a bare
        # Title-Case category name — consistent with the design decision
        # not to rely on bare capitalization (mirrors A8).
        report = "- **Service Category:** Data Center Hosting\n"
        assert find_prohibited_content_violations(report) == []


class TestAttachDisclaimer:
    def test_disclaimer_prepended(self):
        result = attach_disclaimer("# Report body")
        assert result.startswith(MANDATORY_DISCLAIMER)
        assert "# Report body" in result

    def test_disclaimer_mentions_review_requirement(self):
        assert "legal counsel" in MANDATORY_DISCLAIMER.lower()
        assert "not a final determination" in MANDATORY_DISCLAIMER.lower()
