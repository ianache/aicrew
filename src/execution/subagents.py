"""
Subagents — Specialist subagent pool simulating context-isolated Agent-to-Agent (A2A) task execution.
"""
import asyncio
from typing import Dict, Any


class MockSubagent:
    """Represents a simulated specialist subagent executing síncrona/asíncrona in an isolated context."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def execute_task(self, task_id: str, prompt: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate task execution with a short delay to model context processing."""
        await asyncio.sleep(0.05)  # Simulate network/inference latency
        
        prompt_lower = prompt.lower()
        
        if self.name == "DataAnalystAgent":
            if "extract" in prompt_lower or "telemetría" in prompt_lower:
                return {
                    "status": "SUCCESS",
                    "telemetry_data": "Extracted GitLab metrics for project_id 65: commits=15, pipelines=success, test_coverage=94.5%",
                    "timestamp": "2026-05-18T21:05:00Z"
                }
            elif "summary" in prompt_lower or "consolidate" in prompt_lower or "resumen" in prompt_lower:
                # Merge telemetry data if provided in input
                telemetry = input_data.get("telemetry_data", "No telemetry data found")
                policies = input_data.get("policy_audit", "No policies data found")
                return {
                    "status": "SUCCESS",
                    "summary_report": (
                        f"Executive Summary:\n"
                        f"- Telemetry Status: GitLab metrics are green (94.5% test coverage).\n"
                        f"- Audit Status: Passed policies checks successfully.\n"
                        f"- Combined Details: {telemetry} | {policies}"
                    )
                }
            return {"status": "SUCCESS", "result": f"DataAnalystAgent processed: {prompt}"}
            
        elif self.name == "ReporterAgent":
            if "audit" in prompt_lower or "policy" in prompt_lower or "politicas" in prompt_lower:
                return {
                    "status": "SUCCESS",
                    "policy_audit": "Audit PASS: All 3 policies (PRD-004 compliance, context isolation, deterministic execution) validated.",
                    "rules_checked": 5
                }
            return {"status": "SUCCESS", "result": f"ReporterAgent processed: {prompt}"}
            
        return {"status": "SUCCESS", "result": f"Agent {self.name} completed task successfully"}


class SubagentPool:
    """Dispatcher managing specialist subagents and routing A2A execution requests."""

    def __init__(self) -> None:
        self._agents = {
            "DataAnalystAgent": MockSubagent("DataAnalystAgent"),
            "ReporterAgent": MockSubagent("ReporterAgent")
        }

    async def dispatch(self, agent_type: str, task_id: str, prompt: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch task to target isolated subagent context."""
        agent = self._agents.get(agent_type)
        if not agent:
            raise ValueError(f"Subagent of type '{agent_type}' is not registered in the pool.")
        
        # Isolated context execution (FR-3.2, FR-3.3)
        return await agent.execute_task(task_id, prompt, inputs)
