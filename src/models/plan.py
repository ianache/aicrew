"""
Pydantic data models for deterministic Plan-and-Execute multi-agent orchestration (PRD-004).
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PlanStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskDefinition(BaseModel):
    task_id: str = Field(..., description="Unique alphanumeric identifier (e.g. task_01)")
    name: str = Field(..., description="Short, descriptive title of the task")
    description: str = Field(..., description="Detailed instructions for the subagent explaining what to achieve")
    agent_type: str = Field(..., description="Target specialist subagent type (e.g. DataAnalystAgent, SQLGeneratorAgent)")
    dependencies: List[str] = Field(
        default_factory=list,
        description="List of task_ids that MUST be COMPLETED before this task can start execution"
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    input_data: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Key-value inputs required for task execution"
    )
    output_data: Optional[Dict[str, Any]] = Field(None, description="Detailed JSON output returned upon completion")
    error_message: Optional[str] = Field(None, description="Error logs if the task fails")
    retry_count: int = Field(default=0, description="Counter tracking automatic replanning retries (max 3)")


class ExecutionPlan(BaseModel):
    plan_id: str = Field(..., description="Unique identifier representing the execution plan")
    global_status: PlanStatus = Field(default=PlanStatus.PENDING)
    tasks: List[TaskDefinition] = Field(..., description="Directed Acyclic Graph (DAG) of task definitions")
    created_at: str = Field(..., description="ISO timestamp")
    updated_at: str = Field(..., description="ISO timestamp")
