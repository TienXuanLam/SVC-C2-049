# PB-01 (domain): Custom S-2 pre-processing check boundary.
#
# Verifies the BreachEventIngest custom pre-processing check (proposal
# §3/§10 — a custom check *in addition to* the platform S-1 normalizer)
# blocks a case containing a monetary value or Japanese-script identifier
# before it can reach MainNode. Employee-name rejection at this boundary is
# NOT tested here — the platform's own default masking pre-empts our own
# name check for the common Title-Case shape (see
# breach_event_ingest_service.py NAME_CUE_RE docstring and
# test_pre_process_node.py); that specific behavior has its own dedicated
# test.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.main_node import MainNode
from src.nodes.pre_process_node import PreProcessNode

_SEVERITY_THRESHOLDS = {"critical": 0.20, "major": 0.05}
_CREDIT_ELIGIBLE_TIERS = ("critical", "major")


def _invoke_pre_then_main(user_input: str) -> dict:
    # A single BaseNode.__call__() only returns that node's own partial
    # update + framework bookkeeping — it does NOT re-include unrelated
    # pre-existing fields (caller_trust_level was
    # silently dropped between two raw node.__call__() invocations). Merge
    # each node's result into a persistent running state ourselves to
    # correctly simulate the pipeline here without a compiled graph.
    full_state = {"user_input": user_input, "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value}
    pre = PreProcessNode(severity_thresholds=_SEVERITY_THRESHOLDS, credit_eligible_tiers=_CREDIT_ELIGIBLE_TIERS)
    full_state.update(pre(full_state))
    if full_state.get("status") == AgentStatus.ERROR.value:
        return full_state  # AgentBaseGraph routes ERROR straight to finalize — main is skipped
    main = MainNode()
    full_state.update(main(full_state))
    return full_state


def _case_payload(**overrides) -> str:
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


class TestCustomContentRejectionBoundary:
    def test_leaked_money_never_reaches_main_node(self):
        state = _invoke_pre_then_main(_case_payload(service_category="penalty of $50,000"))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state
        assert "severity_tier" not in state

    def test_leaked_japanese_identifier_never_reaches_main_node(self):
        state = _invoke_pre_then_main(_case_payload(breach_period="担当者は山田太郎です"))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state

    def test_clean_case_reaches_main_node(self):
        state = _invoke_pre_then_main(_case_payload())
        assert state["status"] == AgentStatus.SUCCESS.value
        assert state["report_draft"]

    def test_title_case_service_category_reaches_main_node_masked_but_safe(self):
        # The platform pre-masks this to "[MASKED]" (empirically confirmed);
        # this template does not additionally reject it (docs/02_design.md
        # Design Decision Record) — the case proceeds successfully.
        state = _invoke_pre_then_main(_case_payload(service_category="Data Center Hosting"))
        assert state["status"] == AgentStatus.SUCCESS.value
        assert "Data Center Hosting" not in state["report_draft"]

    def test_non_finite_actual_value_never_reaches_main_node(self):
        # prior design review H1.
        state = _invoke_pre_then_main(_case_payload(actual_value="nan"))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state

    def test_non_breach_direction_never_reaches_main_node(self):
        # prior design review M1: actual_value >= threshold for a higher-is-better
        # metric is not an adverse breach.
        state = _invoke_pre_then_main(
            _case_payload(metric_direction="higher_is_better", threshold=99.9, actual_value=100.0)
        )
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state
