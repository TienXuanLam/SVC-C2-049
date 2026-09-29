# SVC-C2-049 — Unit Tests: breach_event_ingest_service (step 1)

import json

from src.services.breach_event_ingest_service import contains_disallowed_content, parse_breach_event


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


class TestParseBreachEvent:
    def test_valid_payload(self):
        breach_event, error = parse_breach_event(_valid_payload())
        assert error is None
        assert breach_event["metric_name"] == "uptime"
        assert breach_event["threshold"] == 99.9
        assert breach_event["actual_value"] == 95.0
        assert breach_event["metric_direction"] == "higher_is_better"

    def test_empty_input(self):
        breach_event, error = parse_breach_event("")
        assert breach_event is None
        assert "empty" in error

    def test_invalid_json(self):
        breach_event, error = parse_breach_event("not-json")
        assert breach_event is None
        assert "not valid JSON" in error

    def test_json_not_object(self):
        breach_event, error = parse_breach_event(json.dumps(["a", "b"]))
        assert breach_event is None
        assert "must be an object" in error

    def test_missing_required_field(self):
        raw = json.dumps({"metric_name": "uptime", "threshold": 99.9, "actual_value": 95.0, "breach_period": "x"})
        breach_event, error = parse_breach_event(raw)
        assert breach_event is None
        assert "service_category" in error

    def test_non_numeric_threshold_rejected(self):
        breach_event, error = parse_breach_event(_valid_payload(threshold="not-a-number"))
        assert breach_event is None
        assert "numeric" in error

    def test_non_numeric_actual_value_rejected(self):
        breach_event, error = parse_breach_event(_valid_payload(actual_value="not-a-number"))
        assert breach_event is None
        assert "numeric" in error

    def test_nan_threshold_rejected(self):
        # prior design review H1: Python's float() converts "nan" to a non-finite
        # float — must be rejected before reaching classification.
        breach_event, error = parse_breach_event(_valid_payload(threshold="nan"))
        assert breach_event is None
        assert "finite" in error

    def test_nan_actual_value_rejected(self):
        breach_event, error = parse_breach_event(_valid_payload(actual_value="nan"))
        assert breach_event is None
        assert "finite" in error

    def test_positive_infinity_threshold_rejected(self):
        breach_event, error = parse_breach_event(_valid_payload(threshold="Infinity"))
        assert breach_event is None
        assert "finite" in error

    def test_negative_infinity_actual_value_rejected(self):
        breach_event, error = parse_breach_event(_valid_payload(actual_value="-Infinity"))
        assert breach_event is None
        assert "finite" in error

    def test_json_native_infinity_rejected(self):
        # json.loads (stdlib) accepts NaN/Infinity/-Infinity as bare tokens
        # by default (non-standard JSON extension) — these must also be
        # rejected, not just the quoted-string variants.
        raw = (
            '{"metric_name": "uptime", "threshold": Infinity, "actual_value": 95.0, '
            '"metric_direction": "higher_is_better", "breach_period": "x", "service_category": "hosting"}'
        )
        breach_event, error = parse_breach_event(raw)
        assert breach_event is None
        assert "finite" in error

    def test_missing_metric_direction_rejected(self):
        payload = json.loads(_valid_payload())
        del payload["metric_direction"]
        breach_event, error = parse_breach_event(json.dumps(payload))
        assert breach_event is None
        assert "metric_direction" in error

    def test_invalid_metric_direction_rejected(self):
        breach_event, error = parse_breach_event(_valid_payload(metric_direction="sideways"))
        assert breach_event is None
        assert "metric_direction" in error

    def test_higher_is_better_non_breach_rejected(self):
        # prior design review M1: actual_value >= threshold for a higher-is-better
        # metric is NOT an adverse breach — must be rejected, not classified.
        breach_event, error = parse_breach_event(
            _valid_payload(metric_direction="higher_is_better", threshold=99.9, actual_value=100.0)
        )
        assert breach_event is None
        assert "does not represent an adverse breach" in error

    def test_higher_is_better_exact_threshold_rejected(self):
        breach_event, error = parse_breach_event(
            _valid_payload(metric_direction="higher_is_better", threshold=99.9, actual_value=99.9)
        )
        assert breach_event is None
        assert "does not represent an adverse breach" in error

    def test_lower_is_better_breach_accepted(self):
        # e.g. response time (ms): higher actual value than threshold is
        # the adverse direction.
        breach_event, error = parse_breach_event(
            _valid_payload(metric_direction="lower_is_better", threshold=200.0, actual_value=350.0)
        )
        assert error is None
        assert breach_event["metric_direction"] == "lower_is_better"

    def test_lower_is_better_non_breach_rejected(self):
        breach_event, error = parse_breach_event(
            _valid_payload(metric_direction="lower_is_better", threshold=200.0, actual_value=150.0)
        )
        assert breach_event is None
        assert "does not represent an adverse breach" in error


class TestContainsDisallowedContent:
    def test_clean_text_passes(self):
        assert contains_disallowed_content("data center hosting") is False

    def test_cue_gated_name_detected(self):
        assert contains_disallowed_content("Reported by John Smith during the review.") is True

    def test_bare_capitalization_not_flagged(self):
        # A8 lesson: bare "two capitalized words" must NOT be treated as a
        # name without a cue word.
        assert contains_disallowed_content("Data Center Hosting") is False

    def test_money_symbol_detected(self):
        assert contains_disallowed_content("penalty of $50,000") is True

    def test_money_word_detected(self):
        assert contains_disallowed_content("penalty of 50000 yen") is True

    def test_japanese_money_word_detected(self):
        assert contains_disallowed_content("50000円のペナルティ") is True

    def test_bare_japanese_name_detected_without_cue(self):
        assert contains_disallowed_content("担当者は山田太郎です") is True

    def test_short_digit_run_not_flagged(self):
        assert contains_disallowed_content("2026-06-01 to 2026-06-30") is False

    def test_empty_text(self):
        assert contains_disallowed_content("") is False

    def test_platform_mask_token_not_treated_as_rejection_signal(self):
        # Design decision (docs/02_design.md Design Decision Record):
        # the platform mask token is NOT itself a
        # rejection signal here — see module docstring for the empirically
        # confirmed rationale (ordinary Title-Case category names collide
        # with the platform's generic name detector).
        assert contains_disallowed_content("[MASKED]") is False
