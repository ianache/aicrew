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
    
    async def faulty_dispatch(agent_type, task_id, prompt, inputs, telemetry=None, *args, **kwargs):
        nonlocal task_01_runs
        if task_id == "task_01":
            task_01_runs += 1
            if task_01_runs == 1:
                raise ValueError("GitLab connection error (simulated)")
        return await original_dispatch(agent_type, task_id, prompt, inputs, telemetry=telemetry, *args, **kwargs)
        
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


# ---------------------------------------------------------------------------
# TestPlanApproval — tests interactive plan approval and rejection (PRD-004)
# ---------------------------------------------------------------------------

async def test_orchestrator_approval_flow_approved(sample_config):
    """If approve_plan=True and user inputs 's', plan is executed successfully."""
    from unittest.mock import patch, AsyncMock
    from src.orchestrator import PlanAndExecuteOrchestrator
    from src.models.plan import ExecutionPlan, PlanStatus
    import dataclasses
    
    custom_config = dataclasses.replace(sample_config, approve_plan=True)
    mock_runner = MagicMock()
    mock_session_service = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "session_123"
    mock_session.state = {"plan": {}}
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_session_service.get_session = AsyncMock(return_value=mock_session)
    mock_runner.session_service = mock_session_service
    
    orchestrator = PlanAndExecuteOrchestrator(config=custom_config, _runner=mock_runner)
    
    # Mock planning and execution methods to isolate approval test
    plan_to_approve = ExecutionPlan(
        plan_id="plan_appr_01",
        global_status=PlanStatus.PENDING,
        created_at="2026-05-19T02:00:00Z",
        updated_at="2026-05-19T02:00:00Z",
        tasks=[]
    )
    orchestrator.generate_plan = AsyncMock(return_value=plan_to_approve)
    
    # Mock the store's get_plan to return COMPLETED so the execution loop exits immediately
    orchestrator._store.get_plan = AsyncMock(return_value=ExecutionPlan(
        plan_id="plan_appr_01",
        global_status=PlanStatus.COMPLETED,
        created_at="2026-05-19T02:00:00Z",
        updated_at="2026-05-19T02:00:00Z",
        tasks=[]
    ))
    
    # Mock synthesis to prevent hitting live system
    mock_synth_res = AsyncMock()
    mock_synth_res.is_final_response.return_value = True
    mock_synth_res.content.parts = [MagicMock(text="Plan Executed and Synthesized", thought=False)]
    
    async def dummy_run_async(*args, **kwargs):
        yield mock_synth_res
        
    orchestrator._runner.run_async = dummy_run_async
    
    # Test approval path by mocking input to return 's' (approved)
    with patch("builtins.input", return_value="s"):
        result = await orchestrator.run("Test prompt")
        
    assert "Plan Executed and Synthesized" in result


async def test_orchestrator_approval_flow_rejected(sample_config):
    """If approve_plan=True and user inputs 'n', execution is aborted instantly."""
    from unittest.mock import patch, AsyncMock
    from src.orchestrator import PlanAndExecuteOrchestrator
    from src.models.plan import ExecutionPlan, PlanStatus
    import dataclasses
    
    custom_config = dataclasses.replace(sample_config, approve_plan=True)
    mock_runner = MagicMock()
    mock_session_service = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "session_123"
    mock_session_service.create_session = AsyncMock(return_value=mock_session)
    mock_session_service.get_session = AsyncMock(return_value=mock_session)
    mock_runner.session_service = mock_session_service
    
    orchestrator = PlanAndExecuteOrchestrator(config=custom_config, _runner=mock_runner)
    
    orchestrator.generate_plan = AsyncMock(return_value=ExecutionPlan(
        plan_id="plan_appr_02",
        global_status=PlanStatus.PENDING,
        created_at="2026-05-19T02:00:00Z",
        updated_at="2026-05-19T02:00:00Z",
        tasks=[]
    ))
    
    # Test rejection path by mocking input to return 'n' (rejected)
    with patch("builtins.input", return_value="n"):
        result = await orchestrator.run("Test prompt")
        
    assert "Plan de Ejecución Cancelado" in result
    assert "rechazado por el usuario" in result

