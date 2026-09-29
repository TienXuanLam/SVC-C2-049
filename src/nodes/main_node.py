"""AgentCore Platform v1.0"""

# main dispatcher — wraps step 3 (RootCauseAnalyze), step 4 (ImpactAssess),
# step 5 (RemediationDraft), and step 6 (ReportAssemble).

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.impact_assess_service import draft_impact_assessment
from src.services.remediation_draft_service import draft_remediation_plan
from src.services.report_assemble_service import assemble_report
from src.services.root_cause_analyze_service import draft_root_cause


class MainNode(FunctionNode):
    """Step 3-6: draft root cause analysis, impact assessment, remediation
    plan, and assemble the full SLA breach report draft."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def execute(self, state: AgentState) -> dict[str, Any]:
        metric_name = state.get("metric_name", "")
        service_category = state.get("service_category", "")
        severity_tier = state.get("severity_tier", "minor")
        credit_eligible = state.get("credit_eligible", False)
        severity_policy_verified = state.get("severity_policy_verified", False)

        root_cause_section = draft_root_cause(metric_name, service_category, severity_tier, llm=self._llm)
        if self._llm is not None:
            emit_trace_event("llm_call", {"step": "root_cause_analyze"}, state)

        impact_section = draft_impact_assessment(service_category, severity_tier, llm=self._llm)
        if self._llm is not None:
            emit_trace_event("llm_call", {"step": "impact_assess"}, state)

        remediation_section = draft_remediation_plan(
            severity_tier, credit_eligible, severity_policy_verified, llm=self._llm
        )
        if self._llm is not None:
            emit_trace_event("llm_call", {"step": "remediation_draft"}, state)

        report_draft = assemble_report(
            metric_name=metric_name,
            threshold=state.get("threshold", 0.0),
            actual_value=state.get("actual_value", 0.0),
            metric_direction=state.get("metric_direction", ""),
            breach_period=state.get("breach_period", ""),
            service_category=service_category,
            severity_tier=severity_tier,
            credit_eligible=credit_eligible,
            severity_policy_verified=severity_policy_verified,
            classification_rationale=state.get("classification_rationale", ""),
            root_cause_section=root_cause_section,
            impact_section=impact_section,
            remediation_section=remediation_section,
        )

        return {
            "root_cause_section": root_cause_section,
            "impact_section": impact_section,
            "remediation_section": remediation_section,
            "report_draft": report_draft,
            "status": AgentStatus.SUCCESS.value,
        }
