"""
Unit and integration tests for PlanAndExecuteOrchestrator (PRD-004).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from src.config import Config
from src.orchestrator import PlanAndExecuteOrchestrator
from src.models.plan import PlanStatus, TaskStatus
from src.skills.plan_management import InMemoryPlanStore
from src.execution.subagents import SubagentPool


@pytest.fixture
def sample_plan_data() -> dict:
    return {
        "plan_id": "orchestrator_plan_123",
        "global_status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [
            {
                "task_id": "task_01",
                "name": "Extract GitLab Telemetry",
                "description": "Extract raw telemetría data from GitLab Repo",
                "agent_type": "DataAnalystAgent",
                "dependencies": [],
                "status": "PENDING",
                "input_data": {}
            },
            {
                "task_id": "task_02",
                "name": "Audit Compliance",
                "description": "Audit policy compliance",
                "agent_type": "ReporterAgent",
                "dependencies": [],
                "status": "PENDING",
                "input_data": {}
            },
            {
                "task_id": "task_03",
                "name": "Consolidate Report",
                "description": "Consolidate telemetry and policies into a Summary report",
                "agent_type": "DataAnalystAgent",
                "dependencies": ["task_01", "task_02"],
                "status": "PENDING",
                "input_data": {}
            }
        ]
    }


def _make_mock_event(text: str):
    """Return a mock ADK stream event yielding final text response."""
    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_part = MagicMock()
    mock_part.text = text
    mock_part.thought = False
    mock_event.content = MagicMock()
    mock_event.content.parts = [mock_part]
    return mock_event


async def test_orchestrator_successful_execution_flow(sample_config, sample_plan_data):
    """Test 1: PlanAndExecuteOrchestrator successfully plans, runs tasks in parallel, and synthesizes final response."""
    store = InMemoryPlanStore()
    subagent_pool = SubagentPool()
    
    mock_runner = MagicMock()
    
    # Simplified mock generator for runner.run_async
    async def mock_run_async(user_id, session_id, new_message=None, **kwargs):
        agent = orchestrator._runner.agent
        if agent.name == "synthesis_agent":
            yield _make_mock_event("# Informe de Ejecución\nOperación exitosa.")
        else:
            yield _make_mock_event("")
            
    mock_runner.run_async = mock_run_async
    
    # Mock session
    mock_session = MagicMock()
    mock_session.id = "session_123"
    mock_session.state = {"plan": sample_plan_data}
    
    orchestrator = PlanAndExecuteOrchestrator(
        config=sample_config,
        store=store,
        subagent_pool=subagent_pool,
        _runner=mock_runner
    )
    
    # Patch session service on orchestrator
    orchestrator._session_service.create_session = AsyncMock(return_value=mock_session)
    orchestrator._session_service.get_session = AsyncMock(return_value=mock_session)
    
    result = await orchestrator.run("Extraer métricas y realizar auditoría de GitLab")
    
    assert "Informe de Ejecución" in result
    assert "Operación exitosa" in result

    # Check store state post-execution
    final_plan = await store.get_plan("orchestrator_plan_123")
    assert final_plan is not None
    assert final_plan.global_status == PlanStatus.COMPLETED
    assert final_plan.tasks[0].status == TaskStatus.COMPLETED
    assert final_plan.tasks[1].status == TaskStatus.COMPLETED
    assert final_plan.tasks[2].status == TaskStatus.COMPLETED
    assert "telemetry_data" in final_plan.tasks[0].output_data
    assert "policy_audit" in final_plan.tasks[1].output_data
    assert "summary_report" in final_plan.tasks[2].output_data


async def test_orchestrator_task_failure_and_replanning_loop(sample_config, sample_plan_data):
    """Test 2: A failed task is replanned and successfully retried up to completion."""
    store = InMemoryPlanStore()
    subagent_pool = SubagentPool()
    
    # Monkeypatch/mock subagent dispatch to fail ONCE for task_01, then succeed
    task_01_runs = 0
    original_dispatch = subagent_pool.dispatch
    
    async def faulty_dispatch(agent_type, task_id, prompt, inputs):
        nonlocal task_01_runs
        if task_id == "task_01":
            task_01_runs += 1
            if task_01_runs == 1:
                raise ValueError("GitLab connection error (simulated)")
        return await original_dispatch(agent_type, task_id, prompt, inputs)
        
    subagent_pool.dispatch = faulty_dispatch

    mock_runner = MagicMock()
    
    async def mock_run_async(user_id, session_id, new_message=None, **kwargs):
        agent = orchestrator._runner.agent
        if agent.name == "synthesis_agent":
            yield _make_mock_event("# Recovery Success")
        else:
            yield _make_mock_event("")
            
    mock_runner.run_async = mock_run_async
    
    # Mock sessions
    planner_session = MagicMock()
    planner_session.id = "session_planner"
    planner_session.state = {"plan": sample_plan_data}
    
    replanner_session = MagicMock()
    replanner_session.id = "session_replanner"
    replanner_session.state = {
        "replanned_task": {
            "task_id": "task_01",
            "name": "Extract GitLab Telemetry - Retry",
            "description": "Extract raw telemetría metrics from GitLab Repo using backup endpoint",
            "agent_type": "DataAnalystAgent",
            "dependencies": [],
            "status": "PENDING"
        }
    }
    
    synthesis_session = MagicMock()
    synthesis_session.id = "session_synth"
    synthesis_session.state = {}

    orchestrator = PlanAndExecuteOrchestrator(
        config=sample_config,
        store=store,
        subagent_pool=subagent_pool,
        _runner=mock_runner
    )
    
    async def mock_create_session(app_name, user_id):
        agent_name = orchestrator._runner.agent.name
        if agent_name == "planner_agent":
            return planner_session
        elif agent_name == "replanner_agent":
            return replanner_session
        return synthesis_session
        
    async def mock_get_session(app_name, user_id, session_id):
        agent_name = orchestrator._runner.agent.name
        if agent_name == "planner_agent":
            return planner_session
        elif agent_name == "replanner_agent":
            return replanner_session
        return synthesis_session
        
    orchestrator._session_service.create_session = mock_create_session
    orchestrator._session_service.get_session = mock_get_session
    
    result = await orchestrator.run("Extraer métricas y realizar auditoría de GitLab")
    
    assert "# Recovery Success" in result
    assert task_01_runs == 2  # Proves the retry loop ran!
    
    final_plan = await store.get_plan("orchestrator_plan_123")
    assert final_plan.global_status == PlanStatus.COMPLETED
    assert final_plan.tasks[0].status == TaskStatus.COMPLETED
    assert final_plan.tasks[0].retry_count == 1
