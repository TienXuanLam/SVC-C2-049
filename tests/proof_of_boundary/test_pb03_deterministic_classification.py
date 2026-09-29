# PB-03 (domain): Deterministic-vs-LLM authority boundary
# (IMPLEMENTATION_LOG.md A4 / docs/02_design.md Design Decision Record).
#
# Legally/financially significant decisions (severity classification,
# credit eligibility) must never accept an `llm` parameter — confirmed here
# by inspecting the function signatures directly, not just by behavioral
# testing (a future edit could add an `llm` param without changing observed
# behavior in a small test matrix).

import inspect

from src.services.breach_classify_service import classify_severity, is_credit_eligible

_THRESHOLDS = {"critical": 0.20, "major": 0.05}


class TestDeterministicAuthorityBoundary:
    def test_classify_severity_has_no_llm_parameter(self):
        assert "llm" not in inspect.signature(classify_severity).parameters

    def test_is_credit_eligible_has_no_llm_parameter(self):
        assert "llm" not in inspect.signature(is_credit_eligible).parameters

    def test_classify_severity_is_pure_deterministic(self):
        args = (100.0, 90.0, _THRESHOLDS)
        assert classify_severity(*args) == classify_severity(*args)

    def test_is_credit_eligible_is_pure_deterministic(self):
        args = ("critical", ("critical", "major"))
        assert is_credit_eligible(*args) == is_credit_eligible(*args)
