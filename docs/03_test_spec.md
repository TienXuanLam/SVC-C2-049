# Test Specification

## Test Strategy
- Coverage target: 100% of `src/services/*.py` and `src/nodes/*.py` (all deterministic
  domain logic and node dispatch paths)
- Test types: Unit (`tests/unit/`) + Proof-of-Boundary (`tests/proof_of_boundary/`).
  No integration tests — severity thresholds are institution-configurable local
  YAML config (proposal §10/§12), not a remote service; LLM is optional with a
  deterministic fallback for every drafting step.
- Verified against the real `agenticstar-agentcore` framework throughout
  development (not only a local stub) — including empirical confirmation of
  the platform's own `detect_pii()` masking behavior, which directly shaped
  two design decisions (see "Platform Interaction Findings" below).

## Platform Interaction Findings (confirmed empirically against the real framework)

1. **The platform's default S-2 scan (`detect_pii()`) masks ANY 2+ consecutive
   Title-Case word run as a "name"** — not just genuine personal names. This
   means:
   - Ordinary service-category values ("Data Center Hosting", "Help Desk
     Support", "Network Operations Center", "Payroll Processing") are
     themselves masked to `"[MASKED]"` before this template's own code runs.
   - A genuine employee name in an input field is therefore virtually always
     pre-masked by the platform before this template's own `NAME_CUE_RE`
     check gets a chance to independently reject it — see
     `test_pre_process_node.py::test_employee_name_in_metric_name_is_pre_masked_by_platform_and_succeeds_safely`.
   - Design consequence: this template does **not** treat
     the platform's mask token as an automatic rejection signal (it would
     auto-reject most legitimate breach reports) — see
     `docs/02_design.md` Design Decision Record.
2. **The platform's `detect_pii()` does NOT detect monetary values or
   Japanese script at all** — confirmed by direct testing. This template's
   own `MONEY_SYMBOL_RE`/`MONEY_WORD_RE`/`JAPANESE_SCRIPT_RE` checks are
   therefore the *primary*, non-redundant defense for those two categories,
   on both the input and output side.
3. Because of (1), a service-category value that ends up as `"[MASKED]"` in
   an otherwise-successful report is expected, documented behavior, not a
   defect — see `docs/07_operation_guide.md` "Title-Case Collision".

## S-1/S-3 Detection Scope Statement

The S-2 custom pre-processing check (`src/services/breach_event_ingest_service.py`)
and the S-3 output re-scan (`src/services/output_validate_service.py`) cover
three concrete, testable patterns: (1) cue-gated ASCII personal names, (2)
monetary-value patterns (symbol or code/word, English and Japanese), (3)
embedded Japanese-script runs — no cue word required. **This is a
best-effort, defense-in-depth heuristic layer, not an exhaustive free-text
detector** (applied proactively from the start). See `docs/02_design.md` "S-1/S-3 Detection Scope" for
the full policy statement.

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict (`src/schemas/state.py`) | Type check pass, no Pydantic/dataclass — confirmed by `tests/proof_of_boundary/test_state_safety.py` | PASS |
| TC-02 | Invalid/malformed input rejected | `PreProcessNode` custom S-2 gate rejects malformed JSON / missing fields / non-numeric, non-finite (NaN/Infinity/-Infinity — prior design review H1), and non-breach-direction (prior design review M1) `threshold`/`actual_value` — `tests/unit/test_pre_process_node.py`, `tests/unit/test_breach_event_ingest_service.py` | PASS |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | PASS — confirmed both locally (`check-security.sh` S-5 dependency/credential-pattern scan, 8/8 checks) and in CI. See the repository's CI pipeline for the latest commit's job results — do not hardcode a specific commit hash here, since a fixed hash goes stale the moment a new commit lands |
| TC-04 | InvocationContext via `from_state()` only | No node in this template constructs `InvocationContext` directly (confirmed by code review — no secret-gated dependency required; every drafting step has a deterministic fallback) | PASS |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from all 3 `execute()` bodies (confirmed by code review) | PASS |
| TC-06 | S-2: `_security_gate_input()` not overridden | `FunctionNode.__init_subclass__` raises `TypeError` if overridden — none of the 3 nodes override it (only `_extra_security_gate_input()` on `PreProcessNode`) | PASS |
| TC-07 | S-3: `_security_gate_output()` not overridden | Same as TC-06 — only `_extra_security_gate_output()` on `PostProcessNode` | PASS |
| TC-08 | `required_trust_level` enforced (via `__call__`, not `execute()`) | `tests/unit/test_pre_process_node.py::test_trust_gate_denies_anonymous_caller` (calls `node(state)`) | PASS |
| TC-09 | S-2 `_extra_security_gate_input()` non-trivial | `PreProcessNode` rejects monetary value/Japanese-script identifier — `tests/unit/test_pre_process_node.py` | PASS |
| TC-10 | S-3 `_extra_security_gate_output()` non-trivial | `PostProcessNode` independently re-scans for prohibited content, may raise — `tests/unit/test_post_process_node.py::TestPostProcessNodeOutputGateHook` | PASS |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` per node | `breach_classified` (pre_process), `llm_call` × 3 when an LLM is configured (main), `output_content_scan` (post_process) — confirmed by code review | PASS |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → AuditLogger | `emit_trace_event()` fires on every node (see TC-11) | No silent failures | PASS |
| PB-2 | State serialization | `test_state_safety.py` | No Pydantic/dataclass/credential fields in `src/schemas/state.py` | PASS |
| PB-3 | L1 → External service | N/A — severity thresholds are local YAML config (not a remote service call); LLM is optional, not required | Not applicable | N/A |
| PB-4 | Import isolation | `test_import_isolation.py` (encoding="utf-8" fix applied — Japanese-script source content breaks the Windows cp1252 default read) | AST scan: 0 violations across `src/` (including `src/services/`, which import neither `framework` nor `shared`) | PASS |
| PB-5 | Checkpoint safety | Covered by PB-2 (same state definition) | No JWT/Pydantic in checkpoint | PASS |
| PB-6 | Invoke execution order | `test_pb_invoke_order.py` (state customized with a valid breach-event JSON `user_input` so `PreProcessNode`'s custom S-2 gate does not short-circuit before `execute()`) | S-1 → `node_start` → S-2 → `execute()` → S-3 → `node_complete`, for all 3 nodes | PASS |
| PB-7 | HITL interrupt propagation | Not applicable — `config/config.yaml` does not set `hitl.enabled: true` (legal/contract-manager review is an out-of-band human process, not a technical `interrupt()` checkpoint; see `docs/02_design.md`) | **Auto-waived — non-HITL** | SKIPPED (2 tests, by design) |

## Domain Proof-of-Boundary Tests

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-01 | Custom S-2 pre-processing check (BreachEventIngest → MainNode) | `test_pb01_custom_content_rejection.py` | A case with a leaked monetary value or Japanese-script identifier never produces `report_draft`/`severity_tier` state — rejected before reaching `main`. A Title-Case category (platform-masked, not template-rejected) safely reaches `main` | PASS |
| PB-02 | S-3 output gate (belt-and-suspenders re-scan) | `test_pb02_s3_output_content_block.py` | A report with a leaked name/monetary value/Japanese identifier is blocked via the real `__call__()` pipeline, and independently via the gate hook even if the execute()-level check is bypassed | PASS |
| PB-03 | Deterministic-vs-LLM authority | `test_pb03_deterministic_classification.py` | `classify_severity()` / `is_credit_eligible()` signatures have no `llm` parameter; both are pure functions | PASS |
| PB-04 | No-prohibited-content guarantee (proposal §3/§10) | `test_pb04_prohibited_content_never_leaks.py` | No adversarial LLM output (name/money/Japanese) survives into the assembled report across all 4 LLM-touched sections; this template's own fallback templates contain no hardcoded prohibited content | PASS |
| PB-05 | Severity-threshold config governance + deployment config-loading path | `test_pb05_severity_config_governance.py` | Default config compiles; a missing required threshold key fails `agent.compile()` (fail-closed); a custom `severity_thresholds`/`credit_eligible_tiers` genuinely overrides the default **via the real deployment loading path** (`src.api.server._load_runtime_config()` reading a temp `config.yaml`, not only constructor injection); importing `src.api.server` itself compiles successfully against the real repo files; the STG `deploy/invoke_payload.json` produces `status: success` | PASS |
| PB-06 | Credit-eligibility policy-verification gate — full `pre_process`→`main` pipeline regression (prior design review round 2 M2 / round 3 M3) | `test_pb06_credit_eligibility_policy_gate.py` | With `severity_policy_verified=False` and an underlying `credit_eligible=True` case run through the REAL generation path (`PreProcessNode` → `MainNode`, not a stubbed `classification_rationale` fixture), the entire assembled report — including the `classification_rationale` text — contains only the approved "requires contract-manager determination" hedge phrase, never a raw "credit-eligible"/"not credit-eligible" assertion | PASS |

> **Pre-CoE gate checklist:** PB-1 through PB-6 are mandatory (PB-3 N/A per
> above). PB-7 is auto-waived — non-HITL. PB-01 through PB-06 are
> domain-specific additions covering this template's highest proposal risks
> (§11 Risk #1: LLM hallucination risk; and the S-1/S-3 no-prohibited-content
> requirement), applying every relevant lesson from an earlier prior design review
> from the start rather than as a post-review fix. PB-06 specifically exists
> because round 2's M2 fix was verified only at the per-surface/per-node unit
> level, which could not catch a leak in a field (`classification_rationale`)
> that a different node/service actually generates — a lesson now generalized:
> any "gate every surface" claim needs a full-pipeline regression, not only
> unit tests with a stubbed value for the surface itself.

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Severity classification — critical/major/minor | Breach ratios at/above/below configured thresholds | Correct severity tier returned deterministically | PASS (`test_breach_classify_service.py`) |
| BL-02 | Credit eligibility | Severity tier in/out of configured `credit_eligible_tiers` | Correct boolean returned deterministically | PASS (`test_breach_classify_service.py`) |
| BL-03 | Breach ratio computation, including zero-threshold edge case | `threshold=0` | Falls back to `abs(actual_value)` instead of raising `ZeroDivisionError` | PASS (`test_breach_classify_service.py::TestComputeBreachRatio`) |
| BL-04 | Report assembly — all sections present | Full set of drafted sections | Markdown report contains Executive Summary, Breach Detail, Root Cause Analysis, Business Impact Assessment, Remediation Plan, Next Review Date | PASS (`test_report_assemble_service.py`) |
| BL-05 | Mandatory disclaimer on every released report | Clean report draft | Output is prefixed with the "AI DRAFT — NOT A FINAL DETERMINATION" disclaimer | PASS (`test_output_validate_service.py`) |
| BL-06 | Bare-capitalization false-positive regression (A8) | Text containing this template's own heading labels ("Service Category", "Breach Period") | Not flagged as a prohibited-content violation | PASS (`test_output_validate_service.py::test_own_heading_not_false_positive`) |
| BL-07 | Prohibited-content fail-safe filter on every LLM-touched section | Adversarial LLM stub returning name/money/Japanese-shaped text | Discarded in favor of the deterministic fallback, for RCA, impact, remediation, and classification rationale alike | PASS (`test_*_service.py::test_llm_prohibited_content_discarded_fail_safe`, `test_pb04_prohibited_content_never_leaks.py`) |
| BL-08 | Non-finite input rejection (prior design review H1) | `threshold`/`actual_value` = `"nan"`, `"Infinity"`, `"-Infinity"`, and JSON-native bare `Infinity` | Rejected at ingest with a `finite` error message — never reaches `classify_severity()` | PASS (`test_breach_event_ingest_service.py::TestParseBreachEvent` NaN/Infinity cases, `test_breach_classify_service.py::TestNonFiniteAndDirectionalityNeverReachClassification`, `test_pb01_custom_content_rejection.py::test_non_finite_actual_value_never_reaches_main_node`) |
| BL-09 | Metric-directionality / non-breach rejection (prior design review M1) | `metric_direction="higher_is_better"` with `actual_value >= threshold` (and the symmetric `lower_is_better` case) | Rejected at ingest as "does not represent an adverse breach" — never classified as a breach severity | PASS (`test_breach_event_ingest_service.py::TestParseBreachEvent` directionality cases, `test_breach_classify_service.py::TestNonFiniteAndDirectionalityNeverReachClassification`, `test_pb01_custom_content_rejection.py::test_non_breach_direction_never_reaches_main_node`) |
| BL-10 | Credit-eligibility policy-verification gate (prior design review M2, rounds 1-2) | `severity_policy_verified=False` (shipped default) vs. `True`, across all four rendering surfaces (Executive Summary, Breach Detail, Remediation Plan, **Classification Rationale**) | Unverified: every surface renders "requires contract-manager determination" (or the equivalent hedge phrase), regardless of the underlying boolean, and an LLM cannot override this on any surface — each hedge/determination clause is appended deterministically, never generated by the LLM. Verified: renders the normal boolean-based determination everywhere | PASS (`test_remediation_draft_service.py::TestDraftRemediationPlanUnverifiedPolicy`, `test_report_assemble_service.py::test_report_hedges_credit_eligibility_when_policy_unverified`, `test_breach_classify_service.py::TestClassificationRationaleUnverifiedPolicy`, `test_pre_process_node.py::test_severity_policy_verified_*`, `test_main_node.py::test_unverified_policy_hedges_credit_eligibility_in_report`, and the full-pipeline `test_pb06_credit_eligibility_policy_gate.py`) |

## Test Execution Summary
- Execution date: 2026-07-19 (prior design review round 4 fix pass — round 2 M2 regression:
  `build_classification_rationale()` leak closed, PB-06 added)
- Total tests: 141 (139 passed, 2 skipped — PB-7, auto-waived non-HITL)
- CI evidence: see the repository's CI pipeline for the current commit's job
  results (this section intentionally does not hardcode a commit hash, since
  a fixed hash goes stale the moment a new commit lands)
- Verified against the real `agenticstar-agentcore` framework throughout
  development, including the "Platform Interaction Findings" above
- Local gates: `ruff check src/ tests/ scripts/` PASS; `check_cat_consistency.py`,
  `check_dep_pinning.py`, `check_stub_tests.py`, `check_trust_level.py` — 4/4 PASS
  (`check_stub_tests.py` required the same `encoding="utf-8"` fix as
  `test_import_isolation.py` — both scan this template's Japanese-script source);
  `check-security.sh` 8/8 PASS; `check-local.sh` green incl. Stage 5 STG invoke
  evidence (`overall: PASS`)
- Coverage: 100% of `src/services/*.py` (7/7 modules) and `src/nodes/*.py` (3/3 modules)
  have dedicated unit tests, plus 6 domain proof-of-boundary tests (PB-01 through PB-06).
  prior design review round 3 (H1/M1/M2/M3) added: non-finite-input rejection tests (BL-08),
  metric-directionality rejection tests (BL-09), and credit-eligibility
  policy-verification gate tests (BL-10). prior design review round 4 (M2 regression on
  `classification_rationale`) added `test_pb06_credit_eligibility_policy_gate.py` —
  a full `pre_process`→`main` pipeline regression, since the leak occurred in a
  field generated by a different node than the one round-3 tests exercised — see
  Business Logic Tests and Domain Proof-of-Boundary Tests above.
