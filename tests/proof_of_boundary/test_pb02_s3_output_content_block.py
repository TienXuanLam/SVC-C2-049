# PB-02 (domain): S-3 output gate boundary — the most important test in this
# suite. Verifies that a
# report containing a leaked employee name, monetary value, or Japanese
# identifier is blocked at the _extra_security_gate_output() boundary via
# the real __call__() pipeline — not just by calling the service function
# directly.

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.post_process_node import PostProcessNode


class TestS3OutputGateBoundary:
    def test_call_blocks_leaked_name_via_execute_level_check(self):
        node = PostProcessNode()
        state = {
            "report_draft": "Reported by John Smith during the review.",
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        }
        result = node(state)  # via __call__ — full S-1/S-2/execute/S-3 pipeline
        assert result["status"] == AgentStatus.ERROR.value
        assert "formatted_output" not in result

    def test_call_blocks_leaked_money_via_execute_level_check(self):
        node = PostProcessNode()
        state = {
            "report_draft": "The vendor owes a penalty of $50,000.",
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        }
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert "formatted_output" not in result

    def test_call_blocks_leaked_japanese_identifier_via_execute_level_check(self):
        node = PostProcessNode()
        state = {
            "report_draft": "担当者は山田太郎です。",
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        }
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert "formatted_output" not in result

    def test_call_releases_clean_report(self):
        node = PostProcessNode()
        state = {
            "report_draft": "# Report\n\nNo prohibited content here.",
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        }
        result = node(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "AI DRAFT" in result["formatted_output"]["report_markdown"]

    def test_gate_hook_independently_blocks_even_if_execute_level_check_is_bypassed(self):
        # Defense-in-depth: directly exercise the gate hook with a result dict
        # that execute() would never normally produce (simulating a future
        # bug where the execute()-level check is bypassed) — the hook must
        # still catch it independently.
        node = PostProcessNode()
        forged_result = {
            "formatted_output": {"report_markdown": "Penalty of ¥1,000,000 was assessed."},
            "status": AgentStatus.SUCCESS.value,
        }
        raised = False
        try:
            node._extra_security_gate_output(forged_result)
        except RuntimeError:
            raised = True
        assert raised, "S-3 gate hook must independently block leaked prohibited content"
