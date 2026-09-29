# SVC-C2-049 — Unit Tests: breach_classify_service (step 2)

import inspect
import json
import math

from src.services.breach_classify_service import (
    build_classification_rationale,
    classify_severity,
    compute_breach_ratio,
    is_credit_eligible,
)
from src.services.breach_event_ingest_service import parse_breach_event

_THRESHOLDS = {"critical": 0.20, "major": 0.05}


class TestComputeBreachRatio:
    def test_deviation_ratio(self):
        assert compute_breach_ratio(100.0, 90.0) == 0.1

    def test_zero_threshold_uses_absolute_value(self):
        assert compute_breach_ratio(0.0, 5.0) == 5.0

    def test_non_finite_input_propagates_non_finite_ratio(self):
        # prior design review M3/H1: compute_breach_ratio itself has no finite guard
        # — it is a pure arithmetic helper. The finiteness contract is
        # enforced exactly once, upstream, at ingest
        # (breach_event_ingest_service.parse_breach_event, math.isfinite()).
        # This test documents that division of responsibility directly: if
        # a non-finite value ever reached this function despite that guard,
        # it would silently propagate rather than raise — which is exactly
        # why H1's fix belongs at the ingest boundary, not here.
        assert math.isnan(compute_breach_ratio(math.nan, 90.0))
        assert math.isinf(compute_breach_ratio(100.0, math.inf))


class TestNonFiniteAndDirectionalityNeverReachClassification:
    # prior design review M3: end-to-end regression proving the H1/M1 ingest guards
    # actually prevent non-finite/non-breach values from ever reaching
    # classify_severity, not just that parse_breach_event rejects them in
    # isolation (see test_breach_event_ingest_service.py for the exhaustive
    # per-case ingest tests).
    def _payload(self, **overrides) -> str:
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

    def test_nan_actual_value_rejected_before_classification(self):
        breach_event, error = parse_breach_event(self._payload(actual_value="nan"))
        assert breach_event is None
        assert error is not None

    def test_infinite_threshold_rejected_before_classification(self):
        breach_event, error = parse_breach_event(self._payload(threshold="Infinity"))
        assert breach_event is None
        assert error is not None

    def test_non_breach_direction_rejected_before_classification(self):
        # actual_value above threshold for a higher-is-better metric is
        # better-than-required performance, not a breach.
        breach_event, error = parse_breach_event(
            self._payload(metric_direction="higher_is_better", threshold=99.9, actual_value=100.0)
        )
        assert breach_event is None
        assert error is not None

    def test_valid_breach_direction_reaches_classification(self):
        breach_event, error = parse_breach_event(
            self._payload(metric_direction="higher_is_better", threshold=99.9, actual_value=75.0)
        )
        assert error is None
        severity_tier = classify_severity(breach_event["threshold"], breach_event["actual_value"], _THRESHOLDS)
        assert severity_tier == "critical"


class TestClassifySeverityDeterminism:
    def test_no_llm_parameter_in_signature(self):
        assert "llm" not in inspect.signature(classify_severity).parameters

    def test_critical_when_ratio_at_or_above_critical_threshold(self):
        assert classify_severity(100.0, 75.0, _THRESHOLDS) == "critical"

    def test_major_when_ratio_between_major_and_critical(self):
        assert classify_severity(100.0, 90.0, _THRESHOLDS) == "major"

    def test_minor_when_ratio_below_major_threshold(self):
        assert classify_severity(100.0, 98.0, _THRESHOLDS) == "minor"

    def test_boundary_at_exact_critical_threshold(self):
        assert classify_severity(100.0, 80.0, _THRESHOLDS) == "critical"

    def test_deterministic(self):
        args = (100.0, 90.0, _THRESHOLDS)
        assert classify_severity(*args) == classify_severity(*args)


class TestIsCreditEligible:
    def test_no_llm_parameter_in_signature(self):
        assert "llm" not in inspect.signature(is_credit_eligible).parameters

    def test_critical_is_eligible(self):
        assert is_credit_eligible("critical", ("critical", "major")) is True

    def test_minor_is_not_eligible(self):
        assert is_credit_eligible("minor", ("critical", "major")) is False


class TestClassificationRationaleVerifiedPolicy:
    def test_fallback_without_llm(self):
        rationale = build_classification_rationale("critical", True, severity_policy_verified=True, llm=None)
        assert "critical" in rationale
        assert "credit-eligible" in rationale

    def test_llm_failure_falls_back(self):
        class BrokenLLM:
            def complete(self, messages, **kwargs):
                raise RuntimeError("boom")

        rationale = build_classification_rationale("major", False, severity_policy_verified=True, llm=BrokenLLM())
        assert "major" in rationale

    def test_llm_rationale_used_when_available(self):
        class StubLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Custom rationale text."}

        rationale = build_classification_rationale("major", False, severity_policy_verified=True, llm=StubLLM())
        # prior design review M2 (round 2): the credit-eligibility clause is always
        # appended deterministically — never delegated to (or overridable
        # by) the LLM.
        assert "Custom rationale text." in rationale
        assert "not credit-eligible" in rationale

    def test_llm_prohibited_content_discarded_fail_safe(self):
        class NameLeakLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Reported by John Smith, this is a major breach."}

        rationale = build_classification_rationale(
            "major", False, severity_policy_verified=True, llm=NameLeakLLM()
        )
        assert "John Smith" not in rationale
        assert "major" in rationale

    def test_llm_empty_response_falls_back(self):
        class EmptyLLM:
            def complete(self, messages, **kwargs):
                return {"content": ""}

        rationale = build_classification_rationale("minor", False, severity_policy_verified=True, llm=EmptyLLM())
        assert "minor" in rationale


class TestClassificationRationaleUnverifiedPolicy:
    # prior design review M2 (round 2): the classification rationale is inserted
    # verbatim into the released report — it must not leak a raw
    # credit-eligible/not-credit-eligible determination when the severity
    # policy is unverified, even though the underlying boolean still exists.
    def test_fallback_hedges_credit_eligibility(self):
        rationale = build_classification_rationale("critical", True, severity_policy_verified=False, llm=None)
        assert "credit eligibility requires contract-manager determination" in rationale
        assert "credit-eligible" not in rationale

    def test_underlying_boolean_does_not_change_wording(self):
        eligible_rationale = build_classification_rationale(
            "critical", True, severity_policy_verified=False, llm=None
        )
        not_eligible_rationale = build_classification_rationale(
            "critical", False, severity_policy_verified=False, llm=None
        )
        assert eligible_rationale == not_eligible_rationale

    def test_llm_cannot_bypass_unverified_gate(self):
        class StubLLM:
            def complete(self, messages, **kwargs):
                return {"content": "This is a major severity breach based on the deviation magnitude."}

        rationale = build_classification_rationale(
            "major", True, severity_policy_verified=False, llm=StubLLM()
        )
        assert "credit eligibility requires contract-manager determination" in rationale
        assert "credit-eligible" not in rationale

    def test_llm_prohibited_content_discarded_fail_safe(self):
        class NameLeakLLM:
            def complete(self, messages, **kwargs):
                return {"content": "Reported by John Smith, this is a major breach."}

        rationale = build_classification_rationale(
            "major", True, severity_policy_verified=False, llm=NameLeakLLM()
        )
        assert "John Smith" not in rationale
        assert "credit eligibility requires contract-manager determination" in rationale
