# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent`
- **L1 Base**: `AgentBaseGraph` (Cat 2 — fixed multi-step domain workflow, not an
  autonomous think→act→observe loop; see docs/01_proposal.md Cat Judgment Rationale)
- **Pattern**: `DocGenerationAgent` (Level 2 label; mechanism is always
  L1-direct `AgentBaseGraph` inheritance )
- **Three-Layer Separation**:
  - State: flat `TypedDict` composition (`src/schemas/state.py`, extends `AgentState`)
  - Node: L1 inheritance (Template Method: `execute(self, state) -> dict` override only)
  - Graph: composition (`register_nodes()` wires 3 real `FunctionNode` instances)

## Architecture Overview

### Node-count reconciliation (proposal §4 → framework 3-slot limit)

The proposal's Agent Workflow describes **7 steps**. `AgentBaseGraph`
exposes exactly **3** domain slots — `pre_process`, `main`, `post_process` —
with no way to register a fourth. The 7 steps are therefore implemented as
**pure-Python step-helper functions** (`src/services/*.py`, plain
functions/no framework imports, no `BaseNode` inheritance) invoked in
sequence inside the 3 real `FunctionNode` dispatchers (`src/nodes/*.py`).
`IMPLEMENTATION_LOG.md` §A2.

```
pre_process (PreProcessNode — real FunctionNode)
  → BreachEventIngest      (step 1 — breach_event_ingest_service.parse_breach_event +
                                      contains_disallowed_content, also wired into
                                      _extra_security_gate_input as the custom S-2 check)
  → BreachClassify         (step 2 — breach_classify_service.classify_severity +
                                      is_credit_eligible [deterministic] +
                                      build_classification_rationale [LLM narrative
                                      only, optional])

main (MainNode — real FunctionNode)
  → RootCauseAnalyze       (step 3 — root_cause_analyze_service.draft_root_cause
                                      [LLM with deterministic fallback + prohibited-
                                      content filter])
  → ImpactAssess           (step 4 — impact_assess_service.draft_impact_assessment
                                      [LLM with deterministic fallback + filter])
  → RemediationDraft       (step 5 — remediation_draft_service.draft_remediation_plan
                                      [LLM with deterministic fallback + filter])
  → ReportAssemble         (step 6 — report_assemble_service.assemble_report
                                      [deterministic string assembly])

post_process (PostProcessNode — real FunctionNode)
  → OutputValidate         (step 7 — output_validate_service.find_prohibited_content_violations +
                                      attach_disclaimer; also wired into
                                      _extra_security_gate_output as a second,
                                      independent re-scan — defense in depth)
```

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | Standard state setup | — | `session_id`, `caller_trust_level`, `node_history=[]`, `error_log=[]` | `InitializeNode` (default) |
| pre_process | Parse+validate breach event (step 1); reject employee name/monetary value, non-finite values (prior design review H1), and non-breach-direction input (prior design review M1) (custom S-2); classify severity + credit eligibility (step 2, deterministic) | `user_input` (JSON string) | `metric_name`, `threshold`, `actual_value`, `metric_direction`, `breach_period`, `service_category`, `severity_tier`, `credit_eligible`, `severity_policy_verified`, `classification_rationale` | `FunctionNode` |
| main | Draft RCA (step 3) + impact assessment (step 4) + remediation plan (step 5); assemble report (step 6) | classification/breach fields | `root_cause_section`, `impact_section`, `remediation_section`, `report_draft` | `FunctionNode` |
| post_process | Re-scan assembled report for prohibited content (step 7, S-3 belt-and-suspenders); attach mandatory disclaimer | `report_draft` | `output_pii_violations`, `formatted_output` | `FunctionNode` |
| finalize | Assemble final output from state | `formatted_output` | response | `FinalizeNode` (default) |

### Step Detail (7 proposal steps → 3 node dispatchers)

| Step | Node | Service module | Deterministic / LLM |
|------|------|----------------|---------------------|
| 1. BreachEventIngest | pre_process | `breach_event_ingest_service.py` | Deterministic (JSON parse + numeric validation + regex content check) |
| 2. BreachClassify | pre_process | `breach_classify_service.py` | Severity/credit: deterministic breach-ratio-vs-config-threshold rule. Rationale text only: LLM (optional) |
| 3. RootCauseAnalyze | main | `root_cause_analyze_service.py` | LLM (optional) with deterministic template fallback; prohibited-content filter always active |
| 4. ImpactAssess | main | `impact_assess_service.py` | LLM (optional) with deterministic template fallback; filter always active |
| 5. RemediationDraft | main | `remediation_draft_service.py` | LLM (optional) with deterministic template fallback; filter always active; never states a specific monetary amount |
| 6. ReportAssemble | main | `report_assemble_service.py` | Deterministic string assembly |
| 7. OutputValidate | post_process | `output_validate_service.py` | Deterministic regex re-scan + disclaimer |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
```

No retry loop is expected in normal operation (no external I/O with transient
failure modes — no network/DB calls). `AgentStatus.ERROR` from `pre_process`
(malformed input / rejected content) routes directly to `finalize`, skipping
`main`/`post_process` — no report is drafted from rejected input.
`AgentStatus.ERROR` from `post_process` (prohibited-content re-scan hit) also
routes to `finalize` — a report that fails the final check is never released.

### S-1/S-3 Detection Scope

Proposal §3/§10 states the requirement as "reject/exclude employee names,
contract values, and penalty amounts" — labeled "S-1" in the proposal text.
Per the AgentCore 5-layer security model, S-1 is the framework's trust-gate
layer (cannot itself do content rejection); this domain-specific rejection
is implemented as a custom **S-2** input-content check
(`_extra_security_gate_input`) — consistent with the general pattern for
this proposal-terminology mismatch.

The custom check (`breach_event_ingest_service.contains_disallowed_content`)
and the output re-scan (`output_validate_service.find_prohibited_content_violations`)
enforce this via **three concrete, testable patterns**:

1. Cue-gated ASCII personal names — a name-introducing cue word
   (`name`/`employee`/`contact`/`reported by`/`manager`/`owner`) immediately
   followed by a two-capitalized-word pattern.
2. Monetary value patterns — a currency symbol (`¥`/`$`/`€`/`£`) + amount, or
   an amount followed by a currency code/word (English or Japanese: `yen`,
   `USD`, `JPY`, `EUR`, `GBP`, `dollars`, `円`, `万円`).
3. Embedded Japanese-script (kanji/hiragana/katakana) runs of 2+ characters —
   no cue word required (this template's own
   generated content is pure ASCII English).

**Honest limitation:** this is a best-effort, defense-in-depth heuristic
layer, not an exhaustive free-text detector (per an earlier prior design review
finding H1, applied proactively here from the start). Primary responsibility
for submitting genuinely anonymized breach data rests with the calling
vendor-management system (proposal §3).

### State Definition

| Field | Type | Producer | Consumer | Purpose |
|-------|------|----------|----------|---------|
| `metric_name` | `str` | pre_process (step 1) | main, post_process | SLA metric name (e.g. "Uptime %") |
| `threshold` | `float` | pre_process (step 1) | pre_process (step 2), main | Contracted SLA threshold value. Rejected at ingest (prior design review H1) if not `math.isfinite()` |
| `actual_value` | `float` | pre_process (step 1) | pre_process (step 2), main | Actual measured value during the breach period. Rejected at ingest (H1) if not finite; rejected (prior design review M1) if it does not represent an adverse breach given `metric_direction` |
| `metric_direction` | `str` | pre_process (step 1) | pre_process (step 2), main (report heading) | `higher_is_better` \| `lower_is_better` — caller-declared metric semantics (prior design review M1); required so ingest can reject a non-breach `actual_value`/`threshold` pairing instead of classifying one |
| `breach_period` | `str` | pre_process (step 1) | main | Anonymized period reference (e.g. a date range) |
| `service_category` | `str` | pre_process (step 1) | main (report heading) | Service category (e.g. "data center hosting") — see "Title-Case Collision" note below |
| `severity_tier` | `str` | pre_process (step 2) | main | One of `critical`/`major`/`minor` — deterministic |
| `credit_eligible` | `bool` | pre_process (step 2) | main | Deterministic, derived from `severity_tier` + configured `credit_eligible_tiers`. Rendering is gated by `severity_policy_verified` (prior design review M2) — see below |
| `severity_policy_verified` | `bool` | pre_process (step 2, from `config.yaml`) | main (report — gates credit-eligibility wording) | Whether an authorized reviewer has attested `severity_thresholds`/`credit_eligible_tiers` as institution-calibrated, not the shipped illustrative defaults (prior design review M2). Defaults to `False` (fail-safe) |
| `classification_rationale` | `str` | pre_process (step 2) | main (report heading) | Narrative-only text; never overrides severity/eligibility |
| `root_cause_section` | `str` | main (step 3) | main (step 6) | Drafted Markdown subsection |
| `impact_section` | `str` | main (step 4) | main (step 6) | Drafted Markdown subsection |
| `remediation_section` | `str` | main (step 5) | main (step 6) | Drafted Markdown subsection |
| `report_draft` | `str` | main (step 6) | post_process (step 7) | Full assembled Markdown, pre-disclaimer |
| `output_pii_violations` | `str` (JSON-encoded `list[str]`, ADR-005) | post_process (step 7) | audit / test assertions | `"[]"` when clean; non-empty blocks release |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types) — confirmed:
  `str`/`float`/`bool` only
- No JWT, API keys, credentials in State
- `InvocationContext` obtained via `InvocationContext.from_state(state)` inside `execute()` only — not stored in State (this template does not currently call any secret-gated dependency; the optional `llm` client manages its own secrets)
- No Pydantic models, dataclass, arbitrary Python objects
- **No employee name, contract value, or penalty amount in any field, within the documented detection scope** (prior design review L1: the proposal's absolute wording is narrowed to what is actually enforced — see "S-1/S-3 Detection Scope" above) — proposal §3/§10 requirement; enforced at ingest (custom S-2 check) and re-verified at output (S-3 belt-and-suspenders re-scan)

## Security Design (S-1 → S-4)

| Layer | Implementation | Risk mitigated (proposal §11) |
|-------|---------------|-------------------------------|
| S-1 | All 3 `FunctionNode` subclasses declare `required_trust_level = TrustLevel.VERIFIED_EXTERNAL` explicitly (no implicit `ANONYMOUS`) | Restricts invocation to authenticated vendor-management callers |
| S-2 (custom) | `PreProcessNode._extra_security_gate_input()` parses breach event and rejects (sets `status=ERROR`, does not raise) when `metric_name`/`breach_period`/`service_category` contains a cue-word-gated name pattern, a monetary value pattern, or an embedded Japanese-script run — separate from, and in addition to, the platform S-1 normalizer | Reduces risk of employee names/contract values/penalty amounts reaching downstream nodes, within the stated detection scope |
| S-3 | `PostProcessNode._extra_security_gate_output()` re-scans the assembled `formatted_output.report_markdown` independently of the step-7 execute()-level check (may raise to block entirely — defense in depth) | Belt-and-suspenders: reduces risk of prohibited content in output even if step 1's check is ever bypassed |
| S-4 | `emit_trace_event()` called at least once per node: `breach_classified` (pre_process), `llm_call` × 3 when an LLM is configured (main), `output_content_scan` (post_process) | Audit trail per invocation (proposal §10 S-4 requirement) |
| Risk #1 (LLM hallucination in RCA/remediation, 🔴 High) | Severity/credit eligibility are deterministic (never LLM-decided); every LLM-generated section (RCA, impact, remediation, classification rationale) discards any output containing a detected employee name or monetary value, falling back to a safe deterministic template; `output_validate_service.attach_disclaimer()` prepends "AI DRAFT — NOT A FINAL DETERMINATION" to every released report, explicitly noting output accuracy depends on input data quality | Mitigates fabricated/inaccurate RCA or remediation content; no code path ships prohibited content |
| Risk #2 (input data inconsistency, 🟡 Medium) | `parse_breach_event()` validates `threshold`/`actual_value` are numeric, finite (`math.isfinite()` — prior design review H1), represent an actual adverse breach given the required `metric_direction` field (prior design review M1), and that all 6 required fields are present; malformed input is rejected at the S-2 gate with a specific error | Bad input fails fast with a clear error instead of producing a misleading report; a non-finite or non-breach (better-than-threshold) value can never reach `classify_severity()`/the report |
| Risk #3 (response time, 🟡 Medium) | No external network I/O (no live LLM call required — deterministic fallback runs when `llm` is not configured); token volume bounded by fixed section templates | Predictable latency; no retry-inducing external dependency |
| prior design review M2 (illustrative severity policy presented as a determination, 🟡 Medium) | `severity_policy_verified` (from `config.yaml`, default `False`) gates every credit-eligibility rendering surface: Executive Summary sentence and Breach Detail field (`report_assemble_service.py`), Remediation Plan section (`remediation_draft_service.py`), **and the Classification Rationale text** (`breach_classify_service.build_classification_rationale()` — round 2 fix: the rationale previously baked a raw "credit-eligible"/"not credit-eligible" clause that bypassed the other three gates). When unverified, all four render "requires contract-manager determination" (or the equivalent hedge phrase) regardless of the underlying `credit_eligible` boolean. Every one of these hedge/determination clauses is computed deterministically and appended after any LLM-generated text — never generated by the LLM itself — so an LLM cannot bypass the gate on any of the four surfaces. See `tests/proof_of_boundary/test_pb06_credit_eligibility_policy_gate.py` for the full pre_process→main pipeline regression that specifically proves this end to end | A deployment running the shipped illustrative `severity_thresholds`/`credit_eligible_tiers` cannot produce a report that reads as a contractual credit-eligibility conclusion, on any of its four eligibility-adjacent surfaces |

> **S-2/S-3 gate behaviour (ADR-017):** all 3 nodes are `FunctionNode` subclasses — the
> framework `@final` gate always runs automatically; extended only via
> `_extra_security_gate_input()` / `_extra_security_gate_output()`, never by overriding the
> `@final` methods themselves.

## Framework Utilization

### Shared Components Used
- [x] `InvocationContext` — reserved access point for the optional `llm` client's own secret
      handling; this template does not itself call `ctx.secrets.require()` (no required-secret
      dependency — every drafting step has a deterministic fallback)
- [ ] ConnectionPolicy — not used (no external service calls)
- [x] S-2: `_extra_security_gate_input()` on `PreProcessNode` — custom employee-name/monetary-
      value rejection (see Security Design table above)
- [x] S-3: `_extra_security_gate_output()` on `PostProcessNode` — independent prohibited-content
      re-scan, may raise to block release entirely
- [x] S-4: `emit_trace_event()` — domain events on all 3 nodes (see Security Design table)

### Composition Pattern

- **Pattern**: Standalone (no `GraphNode`/`RemoteAgentNode` composition — this is a
  leaf Cat 2 template, not a composition of other templates)
- **Composition target**: n/a
- **Error propagation strategy**: n/a

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework/` and `shared/` only (no `agents/base/` required)
- [x] `src/services/*.py` import neither `framework` nor `shared` — pure Python domain logic only

## Class Name Consistency

| Source | Value |
|--------|-------|
| `config/agent.yaml` `agent.class` | `OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent` |
| `config/agent.yaml` `agent.module` | `src.graph` |
| `src/graph/graph.py` class name | `OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent` |
| `src/graph/graph.py` `name` property | `"OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent"` |
| `src/api/server.py` import | `from src.graph.graph import OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent` |

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | `AgentBaseGraph` | `AutonomousBaseGraph` | **A** | Fixed 7-step pipeline with deterministic termination — no autonomous think→act loop needed (Cat 2, not Cat 3) |
| Node-count reconciliation | Register 7 nodes directly | 7 pure-Python step helpers inside 3 real `FunctionNode`s | **B** | `AgentBaseGraph` only exposes 3 domain slots; registering a 4th+ node is not possible without bypassing the S-1/S-2/S-3 gate pipeline (`IMPLEMENTATION_LOG.md` A2) |
| BreachClassify authority | LLM decides severity/eligibility | Deterministic breach-ratio-vs-threshold rule decides; LLM only drafts a non-authoritative rationale sentence | **B** | Severity directly determines remediation urgency and the SLA credit claim basis — a legally/financially significant decision. `IMPLEMENTATION_LOG.md` A4: decisions with legal/financial consequence must be deterministic; LLM is narrative-only |
| Severity threshold source | Hardcoded Python constants | Institution-configurable via `config.yaml`'s `severity_thresholds`/`credit_eligible_tiers`, with `DEFAULT_*` constants only as a construction-time fallback | **B** | Proposal §10/§12 explicitly specifies thresholds "embeddable directly ... in YAML config" — an institution's actual SLA contract terms determine real thresholds, not a fixed in-code value. `register_nodes()` validates required keys at construction time (fail-loud, not fail-open) |
| Severity threshold provenance honesty | Present shipped defaults as authoritative ITIL4/ISO 20000-derived values | Label as illustrative defaults requiring institution calibration; no fabricated citation | **B** | ITIL4/ISO 20000 do not publish one universal numeric deviation threshold — presenting arbitrary numbers as standard-derived would be a false assurance for legally/financially consequential content (per an earlier prior design review M1, applied proactively here — see `docs/07_operation_guide.md` "Severity Threshold Setup") |
| `config.yaml` loading for the standalone entry point | Assume the framework auto-populates `self.config` from `config.yaml` at construction | `src/api/server.py` explicitly loads `config/config.yaml` (`_load_runtime_config()`) and passes it as `Agent(config=...)`, from the initial implementation | **B** | Empirically disproved in an earlier prior design review: `Agent()` with no `config=` argument leaves `self.config == {}` after `compile()` — this template's own entry point bypasses AgentRegistry, so it must load the file itself. Applied here from day 1 rather than as a post-review fix |
| Platform S-2 mask token as a rejection signal | Treat any platform-masked field as automatic rejection grounds | Do NOT treat platform masking as a rejection signal here; rely only on this template's own precise patterns | **B** | **Empirically confirmed against the real framework's `detect_pii()`:** ordinary multi-word Title-Case service-category values ("Data Center Hosting", "Help Desk Support", "Network Operations Center", "Payroll Processing") are themselves flagged and masked by the platform's generic bare-capitalized-word-run heuristic. Unlike a narrative free-text `evidence_description` (where an embedded real name is genuinely anomalous), this template's structured/categorical fields collide with that heuristic on ordinary, non-sensitive business terminology. Treating every platform mask as rejection grounds would auto-reject most legitimate breach reports. The masked value is already safe (no original content leaks through `"[MASKED]"`), so rejection here relies only on this template's own precise domain patterns. See "Title-Case Collision" operational note in `docs/07_operation_guide.md` |
| PII/prohibited-content re-scan location (step 7) | Only in `execute()` | Both in `execute()` (blocks release, sets `output_pii_violations`) and independently in `_extra_security_gate_output()` (may raise) | **B** | Defense in depth — independent of the step-1 ingest check |
| Non-finite `threshold`/`actual_value` handling (prior design review H1) | Accept whatever `float()` produces (Python's `float()` silently converts `"nan"`/`"Infinity"`/`"-Infinity"` to non-finite floats) | Reject with `math.isfinite()` immediately after the `float()` conversion, before the value ever reaches State or `classify_severity()` | **B** | A non-finite `breach_ratio` would silently fall through `classify_severity()`'s comparison chain to `"minor"` — the design's own "fail fast on malformed source data" requirement is violated by any code path that lets malformed evidence reach classification. Validated at the single ingest choke point, not duplicated at the classifier (`compute_breach_ratio` has no guard of its own — see `test_breach_classify_service.py::TestComputeBreachRatio::test_non_finite_input_propagates_non_finite_ratio`, which documents this division of responsibility directly) |
| Breach directionality (prior design review M1) | Classify any `abs(actual_value - threshold)` deviation as a breach, regardless of whether `actual_value` is better or worse than `threshold` | Require an explicit, validated `metric_direction` field (`higher_is_better` \| `lower_is_better`) per event; reject at ingest when `actual_value` does not represent an adverse breach given that direction | **B** | The proposal is scoped to reviewing an *already-known* breach (proposal §4) — accepting and classifying a non-breach (e.g. uptime *above* threshold) contradicts that scope and could produce a report asserting a severity/credit-eligibility outcome for input that was never actually a breach. Metric semantics are metric-specific and cannot be inferred from `metric_name` free text, so the trusted caller (vendor-management system) must declare direction explicitly, consistent with this template's "caller declares, template validates" pattern elsewhere (e.g. `charge_type` in later templates) |
| Credit-eligibility rendering when the severity policy is unverified (prior design review M2) | Present `credit_eligible` as a plain boolean/determination regardless of whether `severity_thresholds`/`credit_eligible_tiers` were ever calibrated against a real contract | Gate every credit-eligibility rendering surface behind a `severity_policy_verified` flag (`config.yaml`, default `False`); when unverified, render "requires contract-manager determination" (or the equivalent hedge phrase) instead of a boolean-based conclusion, on the Executive Summary, Breach Detail, Remediation Plan, **and Classification Rationale** surfaces alike, and compute this text deterministically (never delegated to the LLM prompt) | **B** | The config already labels `severity_thresholds`/`credit_eligible_tiers` as illustrative defaults (applied at design time) — but the *report itself* had no marker distinguishing a calibrated policy from an illustrative one, so a deployment running shipped defaults could still emit what reads as a contractual credit-eligibility conclusion. Computing the hedge text outside the LLM prompt closes the gap where an LLM, told `credit_eligible=True`, could otherwise restate it as a determination regardless of policy-verification status. **Round 2 finding**: the first fix pass gated 3 of 4 surfaces but missed `build_classification_rationale()`, whose fallback/LLM-prompt text still baked in the raw boolean — proving that "gate every surface" claims need an explicit enumeration and a full-pipeline regression test (`test_pb06_credit_eligibility_policy_gate.py`), not just per-surface unit tests with a stubbed rationale input |
| Composition pattern | Standalone | `GraphNode` wrapping an inner workflow | **A** | No existing template to compose; this is itself the leaf domain-workflow template (proposal §5: establishes the pattern for future SVC vendor governance document templates) |
