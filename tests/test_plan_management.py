"""
Unit tests for the native PlanManagementSkill and InMemoryPlanStore (PRD-004).
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from src.models.plan import ExecutionPlan, TaskDefinition, TaskStatus, PlanStatus
from src.skills.plan_management import InMemoryPlanStore, CreatePlanTool, GetNextTasksTool, UpdateTaskStatusTool
from google.adk.tools.tool_context import ToolContext


@pytest.fixture
def plan_store() -> InMemoryPlanStore:
    return InMemoryPlanStore()


@pytest.fixture
def sample_plan_data() -> dict:
    return {
        "plan_id": "test_plan_123",
        "global_status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [
            {
                "task_id": "task_01",
                "name": "Extract Telemetry",
                "description": "Extract raw data from GitLab",
                "agent_type": "DataAnalystAgent",
                "dependencies": [],
                "status": "PENDING",
                "input_data": {}
            },
            {
                "task_id": "task_02",
                "name": "Audit Policies",
                "description": "Audit policy rules in parallel",
                "agent_type": "ReporterAgent",
                "dependencies": [],
                "status": "PENDING",
                "input_data": {}
            },
            {
                "task_id": "task_03",
                "name": "Generate Summary Report",
                "description": "Consolidate telemetry and policies",
                "agent_type": "DataAnalystAgent",
                "dependencies": ["task_01", "task_02"],
                "status": "PENDING",
                "input_data": {}
            }
        ]
    }


async def test_in_memory_plan_store(plan_store, sample_plan_data):
    """Test 1: store gets and saves clean deep copies of plans."""
    plan = ExecutionPlan.model_validate(sample_plan_data)
    await plan_store.save_plan(plan)

    retrieved = await plan_store.get_plan("test_plan_123")
    assert retrieved is not None
    assert retrieved.plan_id == "test_plan_123"
    assert len(retrieved.tasks) == 3

    # Mutation test: modifying in-memory retrieved plan shouldn't affect store
    retrieved.global_status = PlanStatus.COMPLETED
    second_retrieved = await plan_store.get_plan("test_plan_123")
    assert second_retrieved.global_status == PlanStatus.PENDING


async def test_create_plan_tool(plan_store, sample_plan_data):
    """Test 2: CreatePlanTool initializes plan and saves to store."""
    tool = CreatePlanTool(plan_store)
    context = MagicMock(spec=ToolContext)

    result = await tool.run_async(args={"plan": sample_plan_data}, tool_context=context)
    assert "error" not in result
    assert result["global_status"] == PlanStatus.RUNNING
    assert result["tasks"][0]["status"] == TaskStatus.PENDING

    saved_plan = await plan_store.get_plan("test_plan_123")
    assert saved_plan is not None
    assert saved_plan.global_status == PlanStatus.RUNNING


async def test_get_next_tasks_tool(plan_store, sample_plan_data):
    """Test 3: GetNextTasksTool returns tasks with met dependencies and moves them to RUNNING."""
    create_tool = CreatePlanTool(plan_store)
    get_tasks_tool = GetNextTasksTool(plan_store)
    context = MagicMock(spec=ToolContext)

    await create_tool.run_async(args={"plan": sample_plan_data}, tool_context=context)

    # Initially, task_01 and task_02 have no dependencies, so both are executable
    result = await get_tasks_tool.run_async(args={"plan_id": "test_plan_123"}, tool_context=context)
    assert "error" not in result
    tasks = result["tasks"]
    assert len(tasks) == 2
    task_ids = {t["task_id"] for t in tasks}
    assert task_ids == {"task_01", "task_02"}

    # In-store tasks should now be in RUNNING status
    plan = await plan_store.get_plan("test_plan_123")
    assert plan.tasks[0].status == TaskStatus.RUNNING
    assert plan.tasks[1].status == TaskStatus.RUNNING
    assert plan.tasks[2].status == TaskStatus.PENDING  # task_03 still waiting for dependencies


async def test_update_task_status_tool(plan_store, sample_plan_data):
    """Test 4: UpdateTaskStatusTool transitions task states and plan global status."""
    create_tool = CreatePlanTool(plan_store)
    get_tasks_tool = GetNextTasksTool(plan_store)
    update_tool = UpdateTaskStatusTool(plan_store)
    context = MagicMock(spec=ToolContext)

    await create_tool.run_async(args={"plan": sample_plan_data}, tool_context=context)
    await get_tasks_tool.run_async(args={"plan_id": "test_plan_123"}, tool_context=context)

    # 1. Complete task_01
    res1 = await update_tool.run_async(
        args={"plan_id": "test_plan_123", "task_id": "task_01", "status": "COMPLETED", "output_data": {"telemetry": "ok"}},
        tool_context=context
    )
    assert res1["global_status"] == PlanStatus.RUNNING
    assert res1["tasks"][0]["status"] == TaskStatus.COMPLETED

    # 2. Get executable tasks — task_03 should STILL be waiting because task_02 is RUNNING
    res_next = await get_tasks_tool.run_async(args={"plan_id": "test_plan_123"}, tool_context=context)
    assert len(res_next["tasks"]) == 0

    # 3. Complete task_02
    res2 = await update_tool.run_async(
        args={"plan_id": "test_plan_123", "task_id": "task_02", "status": "COMPLETED", "output_data": {"policies": "ok"}},
        tool_context=context
    )
    assert res2["global_status"] == PlanStatus.RUNNING

    # 4. Get executable tasks — task_03 should now be ready
    res_next2 = await get_tasks_tool.run_async(args={"plan_id": "test_plan_123"}, tool_context=context)
    assert len(res_next2["tasks"]) == 1
    assert res_next2["tasks"][0]["task_id"] == "task_03"

    # 5. Complete task_03 — plan should transition to COMPLETED globally
    res3 = await update_tool.run_async(
        args={"plan_id": "test_plan_123", "task_id": "task_03", "status": "COMPLETED", "output_data": {"summary": "done"}},
        tool_context=context
    )
    assert res3["global_status"] == PlanStatus.COMPLETED
