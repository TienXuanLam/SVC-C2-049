"""AgentCore Platform v1.0"""

# pre_process dispatcher — wraps step 1 (BreachEventIngest) and step 2
# (BreachClassify) per the node-count reconciliation in docs/02_design.md
# (7 proposal steps -> 3 AgentBaseGraph slots).

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.breach_classify_service import (
    DEFAULT_CREDIT_ELIGIBLE_TIERS,
    DEFAULT_SEVERITY_THRESHOLDS,
    build_classification_rationale,
    classify_severity,
    is_credit_eligible,
)
from src.services.breach_event_ingest_service import contains_disallowed_content, parse_breach_event


class PreProcessNode(FunctionNode):
    """Step 1 (BreachEventIngest) + Step 2 (BreachClassify)."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(
        self,
        severity_thresholds: dict[str, Any] | None = None,
        credit_eligible_tiers: list[str] | None = None,
        severity_policy_verified: bool = False,
        llm: Any = None,
    ) -> None:
        # Defaults so framework tooling that dynamically instantiates node
        # classes with no args (e.g. PB-6 invoke-order verification) can
        # construct this node — graph.py's register_nodes() always passes
        # its own validated config values explicitly, never relying on
        # these fallbacks in a real invocation.
        self._severity_thresholds = severity_thresholds or DEFAULT_SEVERITY_THRESHOLDS
        self._credit_eligible_tiers = credit_eligible_tiers or DEFAULT_CREDIT_ELIGIBLE_TIERS
        self._severity_policy_verified = severity_policy_verified
        self._llm = llm

    def _extra_security_gate_input(self, state: AgentState) -> AgentState:
        # S-2 custom pre-processing check (proposal §3/§10, labeled "S-1" in
        # the proposal — see docs/02_design.md "S-1/S-3 Detection Scope"):
        # reject employee names / monetary values in the free-text input
        # fields. Separate from, and in addition to, the platform S-1
        # normalizer. Must not raise — surface rejection via state["status"].
        #
        # Malformed/empty input is NOT rejected here — that is a structural
        # validation concern handled in execute() (parse_breach_event's error
        # path), not a security-content rejection. This keeps the S-2/S-3
        # invoke-order boundary (PB-6) exercised even when the caller-supplied
        # state has no user_input at all (e.g. a generic construction/dry-run
        # check), since a genuinely malformed payload here would otherwise
        # short-circuit execute() before it ever runs.
        state = dict(state)
        raw = state.get("user_input", "")
        breach_event, error = parse_breach_event(raw)
        if error or breach_event is None:
            return state

        for field in ("metric_name", "breach_period", "service_category"):
            if contains_disallowed_content(str(breach_event[field])):
                state["status"] = AgentStatus.ERROR.value
                state["error_log"] = [
                    f"BreachEventIngest: rejected — '{field}' appears to contain an "
                    "employee name or monetary value (custom S-2 pre-processing check)"
                ]
                return state

        return state

    def execute(self, state: AgentState) -> dict[str, Any]:
        breach_event, error = parse_breach_event(state.get("user_input", ""))
        if error or breach_event is None:
            return {"status": AgentStatus.ERROR.value, "error_log": [error or "unknown parse error"]}

        threshold = breach_event["threshold"]
        actual_value = breach_event["actual_value"]
        assert isinstance(threshold, (int, float)) and isinstance(actual_value, (int, float))
        severity_tier = classify_severity(float(threshold), float(actual_value), self._severity_thresholds)
        credit_eligible = is_credit_eligible(severity_tier, self._credit_eligible_tiers)
        rationale = build_classification_rationale(
            severity_tier, credit_eligible, self._severity_policy_verified, llm=self._llm
        )

        emit_trace_event(
            "breach_classified",
            {"severity_tier": severity_tier, "credit_eligible": credit_eligible},
            state,
        )

        return {
            "metric_name": breach_event["metric_name"],
            "threshold": breach_event["threshold"],
            "actual_value": breach_event["actual_value"],
            "metric_direction": breach_event["metric_direction"],
            "breach_period": breach_event["breach_period"],
            "service_category": breach_event["service_category"],
            "severity_tier": severity_tier,
            "credit_eligible": credit_eligible,
            "severity_policy_verified": self._severity_policy_verified,
            "classification_rationale": rationale,
            "status": AgentStatus.SUCCESS.value,
        }
