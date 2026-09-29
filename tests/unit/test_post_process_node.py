# SVC-C2-049 — Unit Tests: PostProcessNode (step 7: OutputValidate — S-3
# belt-and-suspenders re-scan + mandatory disclaimer)

import inspect
import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.post_process_node import PostProcessNode


class TestPostProcessNodeExecute:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_clean_report_attaches_disclaimer(self):
        state = {"report_draft": "# Report\n\nClean content.", "severity_tier": "major", "credit_eligible": True}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["output_pii_violations"] == "[]"
        assert "AI DRAFT" in result["formatted_output"]["report_markdown"]

    def test_leaked_name_blocks_release(self):
        state = {"report_draft": "Reported by John Smith during the review."}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        violations = json.loads(result["output_pii_violations"])
        assert violations
        assert "formatted_output" not in result

    def test_leaked_money_blocks_release(self):
        state = {"report_draft": "Penalty amount is $50,000."}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_execute_method_signature(self):
        sig = inspect.signature(PostProcessNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2
        assert params[1] == "state"
        assert "_invoke_impl" not in PostProcessNode.__dict__


class TestPostProcessNodeOutputGateHook:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_gate_hook_raises_on_leaked_content_in_formatted_output(self):
        result = {"formatted_output": {"report_markdown": "Penalty of ¥1,000,000 was assessed."}}
        try:
            self.node._extra_security_gate_output(result)
            raised = False
        except RuntimeError:
            raised = True
        assert raised

    def test_gate_hook_passes_clean_output(self):
        result = {"formatted_output": {"report_markdown": "Clean report content."}}
        assert self.node._extra_security_gate_output(result) == result
