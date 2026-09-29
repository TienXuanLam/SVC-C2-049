"""AgentCore Platform v1.0"""

# Step 1 — BreachEventIngest. Pure Python, no framework imports (per the node contract:
# service modules must not depend on the agenticstar SDK or on framework
# security-gate code directly).
#
# Custom pre-processing check (proposal §3/§10): reject employee names and
# monetary values in the free-text input fields (metric_name, breach_period,
# service_category). Proposal §10 labels this check "S-1" — per the
# AgentCore 5-layer security model, S-1 is the framework's trust-gate layer
# (cannot itself do content rejection); this domain-specific rejection is
# implemented as a custom S-2 input-content check (_extra_security_gate_input),
# consistent with the precedent for this class of proposal
# terminology mismatch.
#
# Detection scope and honest limitation (per an earlier prior design review
# finding H1 — applied proactively here from the start): the checks below
# cover three concrete, testable patterns — (1) cue-gated ASCII personal
# names, (2) monetary-value patterns (currency symbol/code + amount), (3)
# embedded Japanese-script (kanji/kana) runs. This is a best-effort,
# defense-in-depth heuristic layer, not a guarantee of detecting arbitrary
# free-text PII/financial content in every script or phrasing. Primary
# responsibility for submitting genuinely anonymized breach data rests with
# the calling vendor-management system (proposal §3); this layer is a
# secondary check, not a substitute for anonymization at the source.

from __future__ import annotations

import json
import math
import re

REQUIRED_FIELDS = ("metric_name", "threshold", "actual_value", "metric_direction", "breach_period", "service_category")

# prior design review M1: severity classification must not accept a non-breach input
# (e.g. actual_value above threshold for an uptime-style metric). Directional
# semantics are metric-specific, so the trusted caller (vendor-management
# system) must declare them explicitly per event rather than this template
# guessing from metric_name text.
VALID_METRIC_DIRECTIONS = ("higher_is_better", "lower_is_better")

# Public (not underscore-prefixed): reused by output_validate_service.py for
# the independent step-7 belt-and-suspenders re-scan — one shared
# prohibited-content-shape definition instead of two to maintain.
#
# Cue-gated ASCII name detection (IMPLEMENTATION_LOG.md A8): a bare "two
# capitalized words" pattern false-positives on legitimate headings/labels
# this template itself generates (e.g. "Service Category", "Breach Period").
# Requires a name-introducing cue word immediately before the candidate name.
#
# Input-side redundancy note (empirically confirmed against the real
# framework): the platform's own default S-2 scan (detect_pii()) already
# masks ANY 2+ consecutive Title-Case word run as type "name" — the exact
# same shape NAME_CUE_RE targets. On the INPUT side this means a genuine
# employee name is virtually always pre-masked to "[MASKED]" by the platform
# before this hook ever runs, making NAME_CUE_RE effectively a redundant
# safety net there (harmless to keep — e.g. it still covers a future
# platform-behavior change). On the OUTPUT side (step 7,
# output_validate_service.py), the platform's masking does NOT apply
# (report_draft/formatted_output are not in the platform's PII_SCAN_FIELDS),
# so NAME_CUE_RE is the PRIMARY defense there. MONEY_*_RE and
# JAPANESE_SCRIPT_RE below are non-redundant on both sides — the platform's
# detect_pii() does not check for monetary values or Japanese script at all
# (confirmed empirically).
NAME_CUE_RE = re.compile(r"(?i:name|employee|contact|reported by|manager|owner)\s*[:\-]?\s+([A-Z][a-z]+\s[A-Z][a-z]+)")

# Monetary value detection: currency symbol + amount, or amount + currency
# code/word (English and Japanese). Covers proposal §3/§10's "contract
# values, and penalty amounts" / "no ... monetary values" requirement.
MONEY_SYMBOL_RE = re.compile(r"[¥$€£]\s?\d[\d,]*(?:\.\d+)?")
MONEY_WORD_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?(?:yen|USD|JPY|EUR|GBP|dollars?|円|万円)\b", re.IGNORECASE)

# Japanese-script detection: unlike NAME_CUE_RE (which must be cue-gated
# because bare "two capitalized words" false-positives on this template's
# own English headings), a bare run of 2+ kanji/hiragana/katakana characters
# carries no such false-positive risk — every string this template itself
# generates (headings, disclaimer, fallback templates) is pure ASCII
# English. metric_name/breach_period/service_category are documented as
# English free text; any embedded CJK-script run is therefore inherently
# suspicious untranslated content (commonly a name) and is rejected without
# needing a cue word.
JAPANESE_SCRIPT_RE = re.compile(r"[一-鿿぀-ゟ゠-ヿ]{2,}")

# Literal token the platform's default S-2 PII scan substitutes in place of
# a detected identifier.
#
# Design decision — NOT treated as an automatic rejection signal here,
# see docs/02_design.md "S-1/S-3 Detection Scope" Design
# Decision Record for the full rationale): empirically confirmed against the
# real platform detect_pii(), ordinary multi-word service-category values
# ("Data Center Hosting", "Help Desk Support", "Network Operations Center",
# "Payroll Processing") are themselves flagged and masked by the platform's
# generic bare-capitalized-word-run heuristic — this domain's structured/
# categorical fields collide with that heuristic far more often than
# a narrative free-text evidence_description would. Treating every
# platform mask as a rejection would auto-reject most legitimate breach
# reports. The masked value itself is already safe (no original content
# leaks through "[MASKED]"), so this template relies only on its own precise
# domain patterns (NAME_CUE_RE / MONEY_*_RE / JAPANESE_SCRIPT_RE) to decide
# rejection.
PLATFORM_MASK_TOKEN = "[MASKED]"


def parse_breach_event(raw: str) -> tuple[dict[str, object] | None, str | None]:
    """Parse the caller-supplied JSON breach-event string.

    Returns (breach_event, None) on success or (None, error_message) on
    failure. threshold/actual_value are coerced to float; a non-numeric
    value is a validation error (proposal §11 Risk #2).
    """
    if not raw or not raw.strip():
        return None, "BreachEventIngest: user_input is empty"

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, "BreachEventIngest: user_input is not valid JSON"

    if not isinstance(payload, dict):
        return None, "BreachEventIngest: user_input JSON must be an object"

    missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
    if missing:
        return None, f"BreachEventIngest: missing required field(s): {', '.join(missing)}"

    try:
        threshold = float(payload["threshold"])
        actual_value = float(payload["actual_value"])
    except (TypeError, ValueError):
        return None, "BreachEventIngest: threshold and actual_value must be numeric"

    # prior design review H1: Python's float() happily converts "nan"/"Infinity"/
    # "-Infinity" (and JSON-native NaN/Infinity when a permissive parser
    # allows them) to non-finite floats. A non-finite threshold/actual_value
    # would silently produce a non-finite breach_ratio downstream
    # (breach_classify_service.compute_breach_ratio) and fall through to
    # 'minor' — reject explicitly instead of letting malformed evidence
    # reach classification/report generation.
    if not math.isfinite(threshold) or not math.isfinite(actual_value):
        return None, "BreachEventIngest: threshold and actual_value must be finite numbers (not NaN/Infinity)"

    metric_direction = payload.get("metric_direction")
    if metric_direction not in VALID_METRIC_DIRECTIONS:
        return None, f"BreachEventIngest: metric_direction must be one of {VALID_METRIC_DIRECTIONS}"

    # prior design review M1: the proposal is for an already-known breach — this
    # template must reject a non-breach condition rather than classify one.
    # Directionality-aware check: for a higher-is-better metric (e.g.
    # uptime), only actual_value < threshold is an adverse breach; for a
    # lower-is-better metric (e.g. response time), only actual_value >
    # threshold is adverse. Exact equality is not a breach either way.
    is_breach = actual_value < threshold if metric_direction == "higher_is_better" else actual_value > threshold
    if not is_breach:
        return None, (
            "BreachEventIngest: actual_value does not represent an adverse breach of "
            f"threshold given metric_direction='{metric_direction}'"
        )

    return {
        "metric_name": str(payload["metric_name"]).strip(),
        "threshold": threshold,
        "actual_value": actual_value,
        "metric_direction": metric_direction,
        "breach_period": str(payload["breach_period"]).strip(),
        "service_category": str(payload["service_category"]).strip(),
    }, None


def contains_disallowed_content(text: str) -> bool:
    """True if `text` appears to carry an employee name (cue-word gated,
    ASCII or Japanese) or a monetary value. Used to reject metric_name /
    breach_period / service_category free-text input fields. Deliberately
    does NOT treat the platform's PLATFORM_MASK_TOKEN as a rejection signal
    — see the module-level note above PLATFORM_MASK_TOKEN for why (differs
    by design, not oversight).

    Scope note (per an earlier prior design review): this is a best-effort
    heuristic layer over a fixed set of concrete patterns, not an
    exhaustive free-text detector — see module docstring "Detection scope
    and honest limitation".
    """
    if not text:
        return False
    return (
        bool(NAME_CUE_RE.search(text))
        or bool(MONEY_SYMBOL_RE.search(text))
        or bool(MONEY_WORD_RE.search(text))
        or bool(JAPANESE_SCRIPT_RE.search(text))
    )
