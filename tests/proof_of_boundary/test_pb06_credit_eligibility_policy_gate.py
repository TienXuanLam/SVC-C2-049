# PB-06 (domain): Credit-eligibility policy-verification gate — full-report
# regression (prior design review round 2 M2 / round 3 M3).
#
# Round 2 found that build_classification_rationale() still baked a raw
# "credit-eligible"/"not credit-eligible" determination into the
# classification_rationale text, which report_assemble_service inserted
# verbatim — bypassing the severity_policy_verified gate that the
# Executive Summary/Breach Detail/Remediation Plan surfaces already
# honored. Existing tests exercised each node/service in isolation with a
# stubbed classification_rationale and therefore could not catch this —
# only a full pre_process -> main pipeline run (the real generation path)
# would. This file is that regression test.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.main_node import MainNode
from src.nodes.pre_process_node import PreProcessNode

_SEVERITY_THRESHOLDS = {"critical": 0.20, "major": 0.05}
_CREDIT_ELIGIBLE_TIERS = ("critical", "major")

_APPROVED_HEDGE_PHRASE = "credit eligibility requires contract-manager determination"


def _invoke_pre_then_main(user_input: str, severity_policy_verified: bool) -> dict:
    full_state = {"user_input": user_input, "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value}
    pre = PreProcessNode(
        severity_thresholds=_SEVERITY_THRESHOLDS,
        credit_eligible_tiers=_CREDIT_ELIGIBLE_TIERS,
        severity_policy_verified=severity_policy_verified,
    )
    full_state.update(pre(full_state))
    assert full_state["status"] == AgentStatus.SUCCESS.value
    main = MainNode()
    full_state.update(main(full_state))
    return full_state


def _case_payload(**overrides) -> str:
    # threshold=100.0, actual_value=75.0, higher_is_better -> breach_ratio
    # 0.25 -> "critical" -> is_credit_eligible("critical", ("critical",
    # "major")) -> True. This makes the underlying credit_eligible boolean
    # True, so an unverified-policy leak would read "credit-eligible" if
    # the gate were bypassed.
    payload = {
        "metric_name": "uptime",
        "threshold": 100.0,
        "actual_value": 75.0,
        "metric_direction": "higher_is_better",
        "breach_period": "2026-06-01 to 2026-06-30",
        "service_category": "hosting",
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestCreditEligibilityPolicyGateEndToEnd:
    def test_underlying_credit_eligible_is_true(self):
        # Sanity check on the fixture itself.
        state = _invoke_pre_then_main(_case_payload(), severity_policy_verified=True)
        assert state["credit_eligible"] is True
        assert state["severity_tier"] == "critical"

    def test_verified_policy_states_credit_eligible_everywhere(self):
        state = _invoke_pre_then_main(_case_payload(), severity_policy_verified=True)
        report = state["report_draft"]
        assert "This breach is flagged as credit-eligible." in report
        assert "credit-eligible" in state["classification_rationale"]

    def test_unverified_policy_never_leaks_a_raw_determination_anywhere_in_the_report(self):
        # prior design review M2 (round 2) / M3 (round 3): the full assembled report
        # — including the classification_rationale text embedded in it —
        # must not contain "credit-eligible" or "not credit-eligible"
        # outside the approved hedge phrase, even though the underlying
        # credit_eligible boolean is True.
        state = _invoke_pre_then_main(_case_payload(), severity_policy_verified=False)
        assert state["credit_eligible"] is True  # underlying boolean unchanged
        report = state["report_draft"]

        assert _APPROVED_HEDGE_PHRASE in report
        # "credit eligibility requires contract-manager determination" does
        # not itself contain the substring "credit-eligible" (hyphenated) —
        # stripping every occurrence of the approved phrase and checking
        # what remains proves nothing else asserts eligibility.
        residual = report.replace(_APPROVED_HEDGE_PHRASE, "")
        assert "credit-eligible" not in residual
        assert "not credit-eligible" not in residual

    def test_unverified_policy_hedges_within_classification_rationale_specifically(self):
        # Narrower than the full-report test above: isolates the exact
        # field round 2 found leaking.
        state = _invoke_pre_then_main(_case_payload(), severity_policy_verified=False)
        assert _APPROVED_HEDGE_PHRASE in state["classification_rationale"]
        assert "credit-eligible" not in state["classification_rationale"]
