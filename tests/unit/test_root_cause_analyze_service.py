# SVC-C2-049 — Unit Tests: root_cause_analyze_service (step 3)

from src.services.root_cause_analyze_service import draft_root_cause


class TestDraftRootCause:
    def test_fallback_without_llm(self):
        text = draft_root_cause("uptime", "hosting", "critical", llm=None)
        assert "Root Cause Analysis" in text
        assert "uptime" in text
        assert "hosting" in text

    def test_llm_used_when_available(self):
        class StubLLM:
            def complete(self, messages, **kwargs):
                return {"content": "LLM-drafted RCA section."}

        text = draft_root_cause("uptime", "hosting", "major", llm=StubLLM())
        assert text == "LLM-drafted RCA section."

    def test_llm_failure_falls_back(self):
        class BrokenLLM:
            def complete(self, messages, **kwargs):
                raise RuntimeError("boom")

        text = draft_root_cause("uptime", "hosting", "major", llm=BrokenLLM())
        assert "Root Cause Analysis" in text

    def test_llm_empty_response_falls_back(self):
        class EmptyLLM:
            def complete(self, messages, **kwargs):
                return {"content": ""}

        text = draft_root_cause("uptime", "hosting", "minor", llm=EmptyLLM())
        assert "Root Cause Analysis" in text

    def test_llm_prohibited_content_discarded_fail_safe(self):
        class LeakLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Reported by John Smith who caused a $50,000 penalty."}

        text = draft_root_cause("uptime", "hosting", "critical", llm=LeakLLM())
        assert "John Smith" not in text
        assert "$50,000" not in text
        assert "Root Cause Analysis" in text
