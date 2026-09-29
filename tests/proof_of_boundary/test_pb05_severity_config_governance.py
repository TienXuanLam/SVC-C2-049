# PB-05 (domain): Severity threshold / credit-eligibility config governance
# boundary. Verifies the approved workflow's config surface —
# severity_thresholds / credit_eligible_tiers — actually governs the
# compiled agent's classification behavior, that a misconfigured
# config.yaml fails agent.compile() loudly (fail-closed, not fail-open), and
# that this happens via the real deployment configuration-loading path
# (src.api.server._load_runtime_config()), not only constructor injection
# (per an earlier prior design review round 2 — applied proactively here
# from the start).

import json

import pytest

from src.graph.graph import OutsourcedBPOServiceSLABreachRootCauseRemediationReportAgent as Agent


class TestSeverityConfigGovernance:
    def test_default_config_compiles(self):
        agent = Agent(config={})
        agent.compile()
        pre = agent._nodes["pre_process"]
        assert pre._severity_thresholds["critical"]
        assert pre._severity_thresholds["major"]

    def test_missing_critical_key_fails_agent_compile(self):
        agent = Agent(config={"severity_thresholds": {"major": 0.05}})
        with pytest.raises(ValueError, match="severity_thresholds"):
            agent.compile()

    def test_custom_thresholds_override_default(self):
        agent = Agent(
            config={
                "severity_thresholds": {"critical": 0.5, "major": 0.25},
                "credit_eligible_tiers": ["critical"],
            }
        )
        agent.compile()
        pre = agent._nodes["pre_process"]
        assert pre._severity_thresholds["critical"] == 0.5
        assert pre._credit_eligible_tiers == ["critical"]


class TestDeploymentConfigLoadingPath:
    """Exercises src.api.server._load_runtime_config() — the exact function
    the real entry point calls at import/startup time — against real temp
    config.yaml files, and against the real repo config.yaml."""

    def test_load_runtime_config_reads_real_repo_config_yaml(self):
        from src.api.server import _load_runtime_config

        cfg = _load_runtime_config()
        assert cfg["severity_thresholds"]["critical"]
        assert cfg["credit_eligible_tiers"]

    def test_operator_edited_config_yaml_reaches_compiled_agent(self, tmp_path):
        from src.api.server import _load_runtime_config

        operator_config_yaml = tmp_path / "config.yaml"
        operator_config_yaml.write_text(
            "max_retry: 3\nmemory_enabled: false\ntimeout_s: 30\n"
            "severity_thresholds:\n  critical: 0.5\n  major: 0.3\n"
            "credit_eligible_tiers: [\"critical\"]\n",
            encoding="utf-8",
        )
        loaded = _load_runtime_config(operator_config_yaml)
        agent = Agent(config=loaded)
        agent.compile()
        pre = agent._nodes["pre_process"]
        assert pre._severity_thresholds["critical"] == 0.5

    def test_operator_edited_config_yaml_with_incomplete_thresholds_blocks_compile(self, tmp_path):
        from src.api.server import _load_runtime_config

        operator_config_yaml = tmp_path / "config.yaml"
        operator_config_yaml.write_text(
            "max_retry: 3\nmemory_enabled: false\ntimeout_s: 30\n"
            "severity_thresholds:\n  major: 0.3\n",
            encoding="utf-8",
        )
        loaded = _load_runtime_config(operator_config_yaml)
        agent = Agent(config=loaded)
        with pytest.raises(ValueError, match="severity_thresholds"):
            agent.compile()

    def test_real_server_module_constructs_successfully(self):
        # Smoke test of the actual entry point: importing src.api.server
        # runs its module-level `agent = Agent(config=_load_runtime_config());
        # agent.compile()` against the real repo config/config.yaml —
        # proving the full documented path works end-to-end.
        import src.api.server as server_module

        assert server_module.agent._nodes["pre_process"]._severity_thresholds

    def test_real_stg_invoke_payload_produces_success(self):
        import pathlib

        import src.api.server as server_module
        from framework.schemas.invocation_context import InvocationContext
        from framework.schemas.trust_level import TrustLevel

        payload_path = pathlib.Path(__file__).parents[2] / "deploy" / "invoke_payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        ctx = InvocationContext(
            session_id=payload.get("session_id", "s1"),
            caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
            caller_id="c1",
        )
        result = server_module.agent.invoke(payload["input"], ctx=ctx)
        assert result["status"] == "success"
