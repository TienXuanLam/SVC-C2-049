# SVC-C2-049 — OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent

> **Category**: Cat 2 (Orchestrates multiple steps to accomplish a specific use case)
> **Industry**: SVC
> **Inherits**: `AgentBaseGraph` (L1-direct) — Pattern: DocGenerationAgent
> **Status**: Draft

## Overview

Generates ITIL4/ISO 20000-aligned SLA breach report drafts from anonymized
breach data (metric name, threshold, actual value, breach period, service
category). Runs a seven-step pipeline — breach event ingest with employee-name
and monetary-value rejection, severity classification + credit eligibility,
root cause analysis (immediate/contributing/systemic), business impact
assessment, remediation plan drafting, report assembly, and output
validation — producing a structured Markdown draft for contract manager and
legal review before formal vendor submission. No employee names, contract
values, or penalty amounts are held at any stage.

## Why This Template Exists

This template is **one production unit of the Agent 1000 line** — not a standalone
deliverable. The project goal is to make us *capable of producing* 1,000+ templates
per FY26 September capacity. That capability is what unlocks AGENTIC STAR as the
global de facto platform for enterprise agent development.

Of every design decision in this template, ask:

> "Does this make the next template faster, or only this one better?"

If your answer is the latter, reconsider — generalize at Level 2, or refactor the
pattern. A template that is technically beautiful but cannot be replicated quickly
across industries fails the mission. See the project charter for the three-layer
vision and full purpose context.

## Requirements

- Python 3.11+
- Optional: an `ANTHROPIC_API_KEY` secret to enable LLM-drafted report sections

### Behaviour without the platform

Without `ANTHROPIC_API_KEY` configured, the standalone server still boots and
every invocation reaches `status=success` — every drafting step (root cause,
impact assessment, remediation plan, classification rationale) falls back to a
deterministic template. No employee names, contract values, or penalty amounts
are ever held or emitted at any stage, LLM-configured or not.

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Project Structure

```
config/
  agent.yaml          # AgentRegistry manifest
  config.yaml         # runtime parameters (severity thresholds, credit tiers)
deploy/
  invoke_payload.json # sample /invoke payload
  local-stg.yml       # local STG-equivalent deploy config
src/
  api/server.py       # standalone HTTP entry point
  graph/graph.py       # AgentBaseGraph wiring
  nodes/               # pre_process / main / post_process
  schemas/state.py     # flat TypedDict state
  services/            # pure domain logic (7-step pipeline helpers)
tests/
  unit/                # per-node/per-service unit tests
  proof_of_boundary/   # framework-contract boundary tests
docs/
  02_design.md         # design specification
  03_test_spec.md      # test specification
cli.py                 # Marketplace Pod entrypoint
```

## Customising

- `config/config.yaml`: `max_retry`, `memory_enabled`, `timeout_s`,
  `severity_thresholds`, `credit_eligible_tiers`, `severity_policy_verified`
  (see docs/07_operation_guide.md "Severity Threshold Setup" before production
  use — the shipped values are illustrative defaults, not a calibrated policy).
- `config/agent.yaml`'s `requires.secrets`/`requires.extras`: adjust if the
  LLM provider changes.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This is a template under active development within the Agent 1000 line. It is
provided as-is, with no warranty, and may change without notice.
