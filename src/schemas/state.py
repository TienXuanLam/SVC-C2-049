"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.
#
# Node-count reconciliation: the proposal's Agent Workflow (§4) describes a
# 7-step pipeline, but AgentBaseGraph only exposes 3 domain slots
# (pre_process/main/post_process). The 7 steps are pure-Python step helpers
# invoked in sequence inside the 3 real FunctionNode dispatchers — see
# docs/02_design.md "Architecture Overview" for the full mapping.

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent.

    No field ever holds an employee name, contract value, or penalty amount —
    proposal §3/§10 S-1/S-3 requirement (see docs/02_design.md
    "S-1/S-3 Detection Scope").
    """

    # Step 1 — BreachEventIngest (parsed from user_input, a JSON string with
    # keys: metric_name, threshold, actual_value, metric_direction,
    # breach_period, service_category)
    metric_name: str
    threshold: float
    actual_value: float
    metric_direction: str  # higher_is_better | lower_is_better (prior design review M1)
    breach_period: str
    service_category: str

    # Step 2 — BreachClassify (deterministic; see docs/02_design.md Design
    # Decision Record — severity/credit determination is legally and
    # financially significant and must not be LLM-authoritative)
    severity_tier: str  # critical | major | minor
    credit_eligible: bool
    # prior design review M2: whether config.yaml's severity_thresholds/
    # credit_eligible_tiers have been attested as institution-calibrated
    # (not the shipped illustrative defaults). Gates whether the report
    # presents credit_eligible as a determination or as a contract-manager
    # question — see report_assemble_service.py / remediation_draft_service.py.
    severity_policy_verified: bool
    classification_rationale: str  # narrative-only; never overrides the two fields above

    # Step 3 — RootCauseAnalyze
    root_cause_section: str

    # Step 4 — ImpactAssess
    impact_section: str

    # Step 5 — RemediationDraft
    remediation_section: str

    # Step 6 — ReportAssemble
    report_draft: str

    # Step 7 — OutputValidate (S-3: belt-and-suspenders re-scan, independent
    # of the input-side custom check)
    output_pii_violations: str  # JSON-encoded list[str] (ADR-005) — "[]" when clean
