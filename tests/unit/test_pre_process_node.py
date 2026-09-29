# SVC-C2-049 — Unit Tests: PreProcessNode (steps 1-2: BreachEventIngest + BreachClassify)

import inspect
import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.pre_process_node import PreProcessNode

_SEVERITY_THRESHOLDS = {"critical": 0.20, "major": 0.05}
_CREDIT_ELIGIBLE_TIERS = ("critical", "major")


def _valid_payload(**overrides) -> str:
    payload = {
        "metric_name": "uptime",
        "threshold": 99.9,
        "actual_value": 95.0,
        "metric_direction": "higher_is_better",
        "breach_period": "2026-06-01 to 2026-06-30",
        "service_category": "hosting",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _node() -> PreProcessNode:
    return PreProcessNode(severity_thresholds=_SEVERITY_THRESHOLDS, credit_eligible_tiers=_CREDIT_ELIGIBLE_TIERS)


class TestPreProcessNodeExecute:
    def setup_method(self):
        self.node = _node()

    def test_success_path(self):
        state = {"user_input": _valid_payload()}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["metric_name"] == "uptime"
        assert result["severity_tier"] in ("critical", "major", "minor")

    def test_severity_and_credit_computed_deterministically(self):
        state = {"user_input": _valid_payload(threshold=100.0, actual_value=75.0)}
        result = self.node.execute(state)
        assert result["severity_tier"] == "critical"
        assert result["credit_eligible"] is True

    def test_execute_method_signature(self):
        sig = inspect.signature(PreProcessNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2
        assert params[1] == "state"
        assert "_invoke_impl" not in PreProcessNode.__dict__

    def test_severity_policy_verified_defaults_to_false(self):
        # prior design review M2: fail-safe default — an unverified/illustrative
        # policy must not silently present as calibrated.
        state = {"user_input": _valid_payload()}
        result = self.node.execute(state)
        assert result["severity_policy_verified"] is False

    def test_severity_policy_verified_true_flows_into_state(self):
        node = PreProcessNode(
            severity_thresholds=_SEVERITY_THRESHOLDS,
            credit_eligible_tiers=_CREDIT_ELIGIBLE_TIERS,
            severity_policy_verified=True,
        )
        result = node.execute({"user_input": _valid_payload()})
        assert result["severity_policy_verified"] is True


class TestPreProcessNodeSecurityGate:
    def setup_method(self):
        self.node = _node()

    def _call(self, user_input: str, trust=TrustLevel.VERIFIED_EXTERNAL):
        state = {"user_input": user_input, "caller_trust_level": trust.value}
        return self.node(state)  # via __call__ — exercises the full gate pipeline

    def test_trust_gate_denies_anonymous_caller(self):
        result = self._call(_valid_payload(), trust=TrustLevel.ANONYMOUS)
        assert result["status"] == AgentStatus.ERROR.value

    def test_employee_name_in_metric_name_is_pre_masked_by_platform_and_succeeds_safely(self):
        # Empirically confirmed against the real framework: the platform's
        # own default S-2 scan masks any 2+ consecutive Title-Case word run
        # (the exact shape of a typical employee name) to "[MASKED]" BEFORE
        # this node's custom hook runs — see breach_event_ingest_service.py
        # NAME_CUE_RE docstring. The case therefore proceeds safely (no name
        # leaks — the field is already redacted) rather than being rejected
        # by this node's own check. This is a deliberate, documented design
        # trade-off (docs/02_design.md Design Decision Record), not a gap.
        result = self._call(_valid_payload(metric_name="Reported by John Smith"))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "John Smith" not in result["metric_name"]

    def test_rejects_monetary_value_in_service_category(self):
        result = self._call(_valid_payload(service_category="penalty of $50,000"))
        assert result["status"] == AgentStatus.ERROR.value

    def test_rejects_japanese_script_in_breach_period(self):
        result = self._call(_valid_payload(breach_period="担当者は山田太郎です"))
        assert result["status"] == AgentStatus.ERROR.value

    def test_rejects_malformed_json(self):
        result = self._call("not-json")
        assert result["status"] == AgentStatus.ERROR.value

    def test_accepts_clean_title_case_service_category(self):
        # Design decision (docs/02_design.md): Title-Case category values
        # like "Data Center Hosting" are NOT auto-rejected here, even though
        # the platform's own default S-2 scan will mask them — this
        # template relies only on its own precise patterns.
        result = self._call(_valid_payload(service_category="Data Center Hosting"))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "PreProcessNode" in result["node_history"]

    def test_accepts_clean_payload(self):
        result = self._call(_valid_payload())
        assert result["status"] == AgentStatus.SUCCESS.value
