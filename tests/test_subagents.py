"""
Unit tests for Mock Subagents and SubagentPool dispatcher (PRD-004).
"""
import pytest
from src.execution.subagents import SubagentPool


@pytest.fixture
def subagent_pool() -> SubagentPool:
    return SubagentPool()


async def test_data_analyst_agent_extract(subagent_pool):
    """DataAnalystAgent successfully processes extraction prompts."""
    res = await subagent_pool.dispatch(
        agent_type="DataAnalystAgent",
        task_id="task_01",
        prompt="Extract telemetría metrics from GitLab repo",
        inputs={}
    )
    assert res["status"] == "SUCCESS"
    assert "telemetry_data" in res
    assert "94.5%" in res["telemetry_data"]


async def test_reporter_agent_audit(subagent_pool):
    """ReporterAgent successfully audits policies."""
    res = await subagent_pool.dispatch(
        agent_type="ReporterAgent",
        task_id="task_02",
        prompt="Audit policy compliance for the project",
        inputs={}
    )
    assert res["status"] == "SUCCESS"
    assert "policy_audit" in res
    assert "Audit PASS" in res["policy_audit"]


async def test_data_analyst_agent_summary(subagent_pool):
    """DataAnalystAgent successfully consolidates inputs into a summary report."""
    telemetry = "Coverage: 95%"
    policies = "Audit: PASS"
    res = await subagent_pool.dispatch(
        agent_type="DataAnalystAgent",
        task_id="task_03",
        prompt="Consolidate telemetry and policies into a Summary report",
        inputs={"telemetry_data": telemetry, "policy_audit": policies}
    )
    assert res["status"] == "SUCCESS"
    assert "summary_report" in res
    assert telemetry in res["summary_report"]
    assert policies in res["summary_report"]


async def test_invalid_agent_type_raises_value_error(subagent_pool):
    """Invalid agent type raises a ValueError."""
    with pytest.raises(ValueError, match="is not registered in the pool"):
        await subagent_pool.dispatch(
            agent_type="NinjaAgent",
            task_id="task_99",
            prompt="Jump around",
            inputs={}
        )
