"""
PlanManagementSkill — Native ADK Skill Toolset managing deterministic ExecutionPlan state transitions.
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from google.adk.tools import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from src.models.plan import ExecutionPlan, TaskDefinition, TaskStatus, PlanStatus


# ---------------------------------------------------------------------------
# InMemoryPlanStore — Thread-safe in-memory state manager
# ---------------------------------------------------------------------------

class InMemoryPlanStore:
    """Thread-safe, in-memory repository for storing and retrieving ExecutionPlans."""

    def __init__(self) -> None:
        self._plans: Dict[str, ExecutionPlan] = {}
        self._lock = asyncio.Lock()

    async def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        async with self._lock:
            plan = self._plans.get(plan_id)
            if plan is not None:
                # Return a deep-copy/model_validate duplicate to prevent external mutation
                return ExecutionPlan.model_validate(plan.model_dump())
            return None

    async def save_plan(self, plan: ExecutionPlan) -> None:
        async with self._lock:
            # Save a duplicate to isolate database state from in-memory references
            self._plans[plan.plan_id] = ExecutionPlan.model_validate(plan.model_dump())


# ---------------------------------------------------------------------------
# CreatePlanTool
# ---------------------------------------------------------------------------

class CreatePlanTool(BaseTool):
    """Tool that initializes the deterministic ExecutionPlan DAG."""

    def __init__(self, store: InMemoryPlanStore) -> None:
        super().__init__(
            name="create_plan",
            description="Initializes the ExecutionPlan DAG. Validates the plan and registers it in the state store."
        )
        self._store = store

    def _get_declaration(self) -> types.FunctionDeclaration:
        # Schema for create_plan(plan: dict)
        schema = {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "object",
                    "description": "The complete execution plan object containing plan_id, global_status, tasks list, created_at, and updated_at.",
                    "properties": {
                        "plan_id": {"type": "string", "description": "Unique identifier representing the plan"},
                        "global_status": {"type": "string", "description": "Global status of the plan (e.g. PENDING, RUNNING)"},
                        "tasks": {
                            "type": "array",
                            "description": "List of task definitions forming the DAG",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "task_id": {"type": "string", "description": "Unique ID of the task"},
                                    "name": {"type": "string", "description": "Short title of the task"},
                                    "description": {"type": "string", "description": "Instructions for the subagent"},
                                    "agent_type": {"type": "string", "description": "Specialist subagent type to execute the task"},
                                    "dependencies": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "IDs of parent tasks that must complete first"
                                    },
                                    "status": {"type": "string", "description": "Task status (PENDING)"},
                                    "input_data": {"type": "object", "description": "Input variables for the task"}
                                },
                                "required": ["task_id", "name", "description", "agent_type"]
                            }
                        },
                        "created_at": {"type": "string", "description": "ISO timestamp"},
                        "updated_at": {"type": "string", "description": "ISO timestamp"}
                    },
                    "required": ["plan_id", "tasks", "created_at", "updated_at"]
                }
            },
            "required": ["plan"]
        }
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema.model_validate(schema)
        )

    async def run_async(self, *, args: dict, tool_context: ToolContext) -> dict:
        """Initialize plan, validate model, and save to store."""
        plan_data = args.get("plan")
        if not plan_data:
            return {"error": "Missing required field 'plan'"}

        try:
            plan = ExecutionPlan.model_validate(plan_data)
            # Ensure initialized global state is RUNNING once execution starts
            plan.global_status = PlanStatus.RUNNING
            for task in plan.tasks:
                task.status = TaskStatus.PENDING
                task.retry_count = 0
            
            await self._store.save_plan(plan)
            return plan.model_dump()
        except Exception as e:
            return {"error": f"Plan validation failed: {str(e)}"}


# ---------------------------------------------------------------------------
# GetNextTasksTool
# ---------------------------------------------------------------------------

class GetNextTasksTool(BaseTool):
    """Tool that returns a list of independent tasks ready to execute."""

    def __init__(self, store: InMemoryPlanStore) -> None:
        super().__init__(
            name="get_next_executable_tasks",
            description="Returns a list of tasks in PENDING state whose parent dependency tasks are strictly COMPLETED."
        )
        self._store = store

    def _get_declaration(self) -> types.FunctionDeclaration:
        schema = {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Unique identifier of the execution plan to fetch tasks for."
                }
            },
            "required": ["plan_id"]
        }
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema.model_validate(schema)
        )

    async def run_async(self, *, args: dict, tool_context: ToolContext) -> dict:
        plan_id = args.get("plan_id")
        if not plan_id:
            return {"error": "Missing required field 'plan_id'"}

        plan = await self._store.get_plan(plan_id)
        if not plan:
            return {"error": f"Plan with ID {plan_id} not found."}

        if plan.global_status in (PlanStatus.COMPLETED, PlanStatus.FAILED):
            return {"tasks": []}

        completed_tasks = {t.task_id for t in plan.tasks if t.status == TaskStatus.COMPLETED}
        executable_tasks: List[dict] = []

        for task in plan.tasks:
            if task.status == TaskStatus.PENDING:
                if all(dep in completed_tasks for dep in task.dependencies):
                    task.status = TaskStatus.RUNNING
                    executable_tasks.append(task.model_dump())

        if executable_tasks:
            await self._store.save_plan(plan)  # Commit RUNNING transitions

        return {"tasks": executable_tasks}


# ---------------------------------------------------------------------------
# UpdateTaskStatusTool
# ---------------------------------------------------------------------------

class UpdateTaskStatusTool(BaseTool):
    """Tool that updates a task's state, output data, or failure details."""

    def __init__(self, store: InMemoryPlanStore) -> None:
        super().__init__(
            name="update_task_status",
            description="Updates status, outputs, or error details of a specific task. Updates global plan state."
        )
        self._store = store

    def _get_declaration(self) -> types.FunctionDeclaration:
        schema = {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Unique ID of the plan"},
                "task_id": {"type": "string", "description": "ID of the task to update"},
                "status": {"type": "string", "description": "New status for the task (COMPLETED or FAILED)"},
                "output_data": {"type": "object", "description": "Optional output variables returned by the subagent"},
                "error_message": {"type": "string", "description": "Optional error message if status is FAILED"}
            },
            "required": ["plan_id", "task_id", "status"]
        }
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema.model_validate(schema)
        )

    async def run_async(self, *, args: dict, tool_context: ToolContext) -> dict:
        plan_id = args.get("plan_id")
        task_id = args.get("task_id")
        status = args.get("status")
        output_data = args.get("output_data")
        error_message = args.get("error_message")

        if not all([plan_id, task_id, status]):
            return {"error": "Missing one of the required fields: 'plan_id', 'task_id', or 'status'"}

        plan = await self._store.get_plan(plan_id)
        if not plan:
            return {"error": f"Plan with ID {plan_id} not found."}

        task = next((t for t in plan.tasks if t.task_id == task_id), None)
        if not task:
            return {"error": f"Task with ID {task_id} not found in plan."}

        try:
            task.status = TaskStatus(status)
            if output_data is not None:
                task.output_data = output_data
            if error_message is not None:
                task.error_message = error_message

            # Recalculate global status
            all_tasks = plan.tasks
            if any(t.status == TaskStatus.FAILED for t in all_tasks):
                # Global failure only if max retries exceeded for all failed tasks
                if all(t.retry_count >= 3 for t in all_tasks if t.status == TaskStatus.FAILED):
                    plan.global_status = PlanStatus.FAILED
            elif all(t.status == TaskStatus.COMPLETED for t in all_tasks):
                plan.global_status = PlanStatus.COMPLETED

            plan.updated_at = datetime.now(timezone.utc).isoformat()
            await self._store.save_plan(plan)
            return plan.model_dump()
        except Exception as e:
            return {"error": f"Failed to update task status: {str(e)}"}


# ---------------------------------------------------------------------------
# PlanManagementSkill — BaseToolset Packaging
# ---------------------------------------------------------------------------

class PlanManagementSkill(BaseToolset):
    """Native ADK Toolset packaging plan management tools into a discoverable skill."""

    def __init__(self, store: InMemoryPlanStore) -> None:
        self.store = store
        self.create_plan_tool = CreatePlanTool(store)
        self.get_next_tasks_tool = GetNextTasksTool(store)
        self.update_task_status_tool = UpdateTaskStatusTool(store)

    async def get_tools(self) -> list:
        """Expose core tools to the ADK Agent."""
        return [self.create_plan_tool, self.get_next_tasks_tool, self.update_task_status_tool]

    async def close(self) -> None:
        """Teardown hook (noop)."""
        pass
