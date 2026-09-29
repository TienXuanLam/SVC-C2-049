# SVC-C2-049 — Unit Tests: impact_assess_service (step 4)

from src.services.impact_assess_service import draft_impact_assessment


class TestDraftImpactAssessment:
    def test_fallback_without_llm(self):
        text = draft_impact_assessment("hosting", "critical", llm=None)
        assert "Business Impact Assessment" in text
        assert "hosting" in text

    def test_llm_used_when_available(self):
        class StubLLM:
            def complete(self, messages, **kwargs):
                return {"content": "LLM-drafted impact section."}

        text = draft_impact_assessment("hosting", "major", llm=StubLLM())
        assert text == "LLM-drafted impact section."

    def test_llm_failure_falls_back(self):
        class BrokenLLM:
            def complete(self, messages, **kwargs):
                raise RuntimeError("boom")

        text = draft_impact_assessment("hosting", "major", llm=BrokenLLM())
        assert "Business Impact Assessment" in text

    def test_llm_prohibited_content_discarded_fail_safe(self):
        class LeakLLM:
            def complete(self, messages, **kwargs):
                return {"content": "The manager Jane Doe estimated impact at ¥1,000,000."}

        text = draft_impact_assessment("hosting", "critical", llm=LeakLLM())
        assert "Jane Doe" not in text
        assert "1,000,000" not in text
