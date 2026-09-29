"""AgentCore Platform v1.0"""

# Cat 2 — 7-step SLA breach report pipeline reconciled into the fixed 3-slot
# AgentBaseGraph backbone (docs/02_design.md "Architecture Overview"). No
# add_edges() override — the default
# START -> initialize -> pre_process -> main -> {route} -> post_process -> finalize -> END
# pipeline is correct for this template (no HITL, no non-standard routing).

from framework.graph.agent_base_graph import AgentBaseGraph

from src.nodes.main_node import MainNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State
from src.services.breach_classify_service import (
    DEFAULT_CREDIT_ELIGIBLE_TIERS,
    DEFAULT_SEVERITY_THRESHOLDS,
)


class OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent(AgentBaseGraph):
    """Generates ITIL4/ISO 20000-aligned SLA breach report drafts from
    anonymized breach data."""

    @property
    def name(self) -> str:
        return "OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        # llm is optional — every drafting step has a deterministic fallback
        # (IMPLEMENTATION_LOG.md B5 pattern). A6 wiring checklist: both
        # PreProcessNode and MainNode take llm; verify both are wired here
        # whenever a new dependency is added to either constructor.
        llm = self.config.get("llm")

        # Institution-configurable severity classification (proposal §10/§12
        # + docs/02_design.md Design Decision Record) — config.yaml carries
        # the actual values; the DEFAULT_* constants here are only a
        # fallback for construction without an explicit config (e.g. local
        # dev/tests). Validated at construction time (fail-loud, not
        # fail-open) so a misconfigured config.yaml fails agent.compile()
        # rather than degrading silently at invoke time.
        severity_thresholds = self.config.get("severity_thresholds", DEFAULT_SEVERITY_THRESHOLDS)
        credit_eligible_tiers = self.config.get("credit_eligible_tiers", DEFAULT_CREDIT_ELIGIBLE_TIERS)
        missing = [key for key in ("critical", "major") if key not in severity_thresholds]
        if missing:
            raise ValueError(
                f"config.yaml's severity_thresholds is missing required key(s): {missing}. "
                "See docs/07_operation_guide.md 'Severity Threshold Setup'."
            )

        # prior design review M2: defaults to False (unverified/illustrative) — a
        # deployment must explicitly attest calibration in config.yaml
        # before the report presents credit eligibility as a determination
        # rather than a contract-manager question. Fail-safe, not fail-open.
        severity_policy_verified = bool(self.config.get("severity_policy_verified", False))

        self._nodes["pre_process"] = PreProcessNode(
            severity_thresholds=severity_thresholds,
            credit_eligible_tiers=credit_eligible_tiers,
            severity_policy_verified=severity_policy_verified,
            llm=llm,
        )
        self._nodes["main"] = MainNode(llm=llm)
        self._nodes["post_process"] = PostProcessNode()
