"""
Typed execution result models for the Deno execution channel.

All execution outcomes are modeled as Pydantic discriminated union members.
DenoRunner.execute() always returns ExecutionResult — never raises for execution outcomes.
Callers use isinstance() checks to dispatch on the result type.
"""
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field


class ExecutionSuccess(BaseModel):
    """Successful skill execution — stdout parsed as JSON."""
    type: Literal["success"] = "success"
    data: dict


class TimeoutError(BaseModel):
    """Skill execution exceeded the 5000ms hard timeout."""
    type: Literal["timeout"] = "timeout"
    elapsed_ms: int


class ExecutionError(BaseModel):
    """Skill exited non-zero, OR stdout could not be parsed as JSON."""
    type: Literal["execution_error"] = "execution_error"
    exit_code: int
    stderr: str


class ValidationFailure(BaseModel):
    """An invalid domain was passed before the subprocess was created."""
    type: Literal["validation_failure"] = "validation_failure"
    invalid_domain: str


ExecutionResult = Union[ExecutionSuccess, TimeoutError, ExecutionError, ValidationFailure]
