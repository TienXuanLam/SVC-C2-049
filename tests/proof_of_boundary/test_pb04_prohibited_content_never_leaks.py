# PB-04 (domain): "No prohibited content" guarantee (proposal §3/§10 —
# employee names, contract values, penalty amounts). No LLM-generated
# section (RCA, impact, remediation, classification rationale) may ship
# such content, regardless of what an adversarial/misbehaving LLM returns.
# Includes both a behavioral battery (adversarial LLM stubs) and a static
# scan of this template's own fallback template strings.

import ast
import pathlib

from src.services.breach_classify_service import build_classification_rationale
from src.services.impact_assess_service import draft_impact_assessment
from src.services.remediation_draft_service import draft_remediation_plan
from src.services.report_assemble_service import assemble_report
from src.services.root_cause_analyze_service import draft_root_cause


class _AdversarialLLM:
    def __init__(self, text: str):
        self._text = text

    def complete(self, messages: list, **kwargs) -> dict:
        return {"content": self._text}


ADVERSARIAL_OUTPUTS = [
    "Reported by John Smith, who caused this breach.",
    "The penalty assessed was $50,000.",
    "A fine of 50000 yen was imposed on the manager.",
    "担当者は山田太郎です。",
]


class TestAdvisoryOnlyBehavioral:
    def test_no_adversarial_llm_output_survives_into_assembled_report(self):
        for adversarial_text in ADVERSARIAL_OUTPUTS:
            llm = _AdversarialLLM(adversarial_text)
            root_cause_section = draft_root_cause("uptime", "hosting", "critical", llm=llm)
            impact_section = draft_impact_assessment("hosting", "critical", llm=llm)
            remediation_section = draft_remediation_plan("critical", True, severity_policy_verified=True, llm=llm)
            classification_rationale = build_classification_rationale(
                "critical", True, severity_policy_verified=True, llm=llm
            )

            report = assemble_report(
                metric_name="uptime",
                threshold=99.9,
                actual_value=50.0,
                metric_direction="higher_is_better",
                breach_period="2026-06-01 to 2026-06-30",
                service_category="hosting",
                severity_tier="critical",
                credit_eligible=True,
                severity_policy_verified=True,
                classification_rationale=classification_rationale,
                root_cause_section=root_cause_section,
                impact_section=impact_section,
                remediation_section=remediation_section,
            )
            assert adversarial_text not in report, f"adversarial text leaked via '{adversarial_text}'"


class TestAdvisoryOnlyStaticScan:
    def test_fallback_templates_contain_no_hardcoded_prohibited_content(self):
        # Self-check: none of this template's own deterministic fallback
        # strings may themselves contain a name/money/Japanese pattern.
        from src.services.breach_event_ingest_service import (
            JAPANESE_SCRIPT_RE,
            MONEY_SYMBOL_RE,
            MONEY_WORD_RE,
            NAME_CUE_RE,
        )

        src_dir = pathlib.Path(__file__).parents[2] / "src" / "services"
        offenders = []
        for path in src_dir.glob("*.py"):
            if path.name == "breach_event_ingest_service.py":
                # Excluded: this module defines the detection patterns
                # themselves and its docstrings/tests reference example
                # matches — a self-reference, not a leak.
                continue
            source = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source, filename=str(path))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value
                    if (
                        NAME_CUE_RE.search(text)
                        or MONEY_SYMBOL_RE.search(text)
                        or MONEY_WORD_RE.search(text)
                        or JAPANESE_SCRIPT_RE.search(text)
                    ):
                        offenders.append(f"{path.name}:{node.lineno} contains prohibited-content-shaped text")
        assert offenders == [], "\n".join(offenders)
