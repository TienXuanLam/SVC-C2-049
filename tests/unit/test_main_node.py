# SVC-C2-049 — Unit Tests: MainNode (steps 3-6: draft RCA + impact + remediation, assemble report)
#
# Rewritten from the scaffold stub (IMPLEMENTATION_LOG.md A7) — the original
# stub tested a generic "process input" MainNode that no longer matches this
# template's real business logic.

import inspect

from framework.schemas.agent_status import AgentStatus
from src.nodes.main_node import MainNode


def _base_state(**overrides) -> dict:
    state = {
        "metric_name": "uptime",
        "threshold": 99.9,
        "actual_value": 95.0,
        "metric_direction": "higher_is_better",
        "breach_period": "2026-06-01 to 2026-06-30",
        "service_category": "hosting",
        "severity_tier": "major",
        "credit_eligible": True,
        "severity_policy_verified": True,
        "classification_rationale": "Matched major severity keywords.",
    }
    state.update(overrides)
    return state


class TestMainNode:
    def setup_method(self):
        self.node = MainNode()

    def test_success_path_without_llm(self):
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "Root Cause Analysis" in result["root_cause_section"]
        assert "Business Impact Assessment" in result["impact_section"]
        assert "Remediation Plan" in result["remediation_section"]
        assert "uptime" in result["report_draft"]

    def test_success_path_with_llm(self):
        class StubLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Stub LLM narrative text."}

        node = MainNode(llm=StubLLM())
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "Stub LLM narrative text." in result["root_cause_section"]

    def test_report_never_contains_prohibited_content_even_with_leaking_llm(self):
        class LeakLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Reported by John Smith who owes a penalty of $50,000."}

        node = MainNode(llm=LeakLLM())
        result = node.execute(_base_state())
        assert "John Smith" not in result["report_draft"]
        assert "$50,000" not in result["report_draft"]

    def test_execute_method_signature(self):
        sig = inspect.signature(MainNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2
        assert params[1] == "state"
        assert "_invoke_impl" not in MainNode.__dict__

    def test_unverified_policy_hedges_credit_eligibility_in_report(self):
        # prior design review M2.
        result = self.node.execute(_base_state(severity_policy_verified=False))
        assert "requires contract-manager determination" in result["report_draft"].lower()

    def test_metric_direction_rendered_in_report(self):
        # prior design review M1.
        result = self.node.execute(_base_state(metric_direction="lower_is_better"))
        assert "lower_is_better" in result["report_draft"]
