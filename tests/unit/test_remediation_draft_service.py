# SVC-C2-049 — Unit Tests: remediation_draft_service (step 5)

from src.services.remediation_draft_service import draft_remediation_plan


class TestDraftRemediationPlanVerifiedPolicy:
    def test_fallback_without_llm_credit_eligible(self):
        text = draft_remediation_plan("critical", True, severity_policy_verified=True, llm=None)
        assert "Remediation Plan" in text
        assert "credit-eligible" in text.lower()
        assert "requires contract-manager determination" not in text.lower()

    def test_fallback_without_llm_not_credit_eligible(self):
        text = draft_remediation_plan("minor", False, severity_policy_verified=True, llm=None)
        assert "not flagged as credit-eligible" in text.lower() or "not credit-eligible" in text.lower()

    def test_llm_used_when_available(self):
        class StubLLM:
            def complete(self, messages, **kwargs):
                return {"content": "LLM-drafted remediation section."}

        text = draft_remediation_plan("major", True, severity_policy_verified=True, llm=StubLLM())
        assert "LLM-drafted remediation section." in text
        # prior design review M2: the Credit Eligibility line is always appended
        # deterministically — never delegated to (or overridable by) the LLM.
        assert "credit-eligible" in text.lower()

    def test_llm_prohibited_content_discarded_fail_safe(self):
        class LeakLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Employee John Smith must pay a penalty of $50,000."}

        text = draft_remediation_plan("critical", True, severity_policy_verified=True, llm=LeakLLM())
        assert "John Smith" not in text
        assert "$50,000" not in text
        assert "Remediation Plan" in text


class TestDraftRemediationPlanUnverifiedPolicy:
    def test_fallback_without_llm_requires_contract_manager_determination(self):
        # prior design review M2: shipped illustrative defaults must not present a
        # credit-eligibility conclusion until the policy is attested.
        text = draft_remediation_plan("critical", True, severity_policy_verified=False, llm=None)
        assert "requires contract-manager determination" in text.lower()
        assert "this breach is flagged as credit-eligible" not in text.lower()

    def test_credit_eligible_value_ignored_when_unverified(self):
        eligible_text = draft_remediation_plan("critical", True, severity_policy_verified=False, llm=None)
        not_eligible_text = draft_remediation_plan("critical", False, severity_policy_verified=False, llm=None)
        # Same hedged wording regardless of the underlying (unverified) boolean.
        assert eligible_text.split("**Credit Eligibility:**")[1] == not_eligible_text.split("**Credit Eligibility:**")[
            1
        ]

    def test_llm_cannot_bypass_unverified_gate(self):
        # An LLM instructed only about corrective actions/timeline/KPIs
        # (never told credit_eligible) cannot emit a credit-eligibility
        # determination — even if it tries to, the deterministic hedge text
        # is appended afterward, and this test simply confirms that hedge
        # text is present regardless of LLM output.
        class StubLLM:
            def complete(self, messages, **kwargs):
                return {"content": "LLM-drafted remediation section."}

        text = draft_remediation_plan("critical", True, severity_policy_verified=False, llm=StubLLM())
        assert "requires contract-manager determination" in text.lower()

    def test_llm_prohibited_content_discarded_fail_safe(self):
        class LeakLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Employee John Smith must pay a penalty of $50,000."}

        text = draft_remediation_plan("critical", True, severity_policy_verified=False, llm=LeakLLM())
        assert "John Smith" not in text
        assert "$50,000" not in text
        assert "requires contract-manager determination" in text.lower()
