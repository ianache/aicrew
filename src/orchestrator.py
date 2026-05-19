"""
PlanAndExecuteOrchestrator — Deterministic Multi-Agent Coordinating Orchestrator (PRD-004).
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from google.adk.agents import LlmAgent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from src.config import Config
from src.models.plan import ExecutionPlan, TaskDefinition, TaskStatus, PlanStatus
from src.skills.plan_management import InMemoryPlanStore, CreatePlanTool, GetNextTasksTool, UpdateTaskStatusTool
from src.execution.subagents import SubagentPool

logger = logging.getLogger(__name__)


class PlanAndExecuteOrchestrator:
    """Deterministic Plan-and-Execute Coordinating Orchestrator.

    Features:
    1. Generates an ExecutionPlan DAG from user prompts using Gemini (Pass 1).
    2. Runs tasks in parallel using asyncio.gather (NFR-1.1).
    3. Isolates subagent execution context to avoid token contamination (FR-3.2, KPI 1.1).
    4. Automatically attempts micro-replanning on task failure up to 3 times (FR-4.1, FR-4.2).
    5. Synthesizes a premium markdown report for the user once complete (Pass 2).
    """

    def __init__(
        self,
        config: Config,
        store: InMemoryPlanStore = None,
        subagent_pool: SubagentPool = None,
        _runner: Runner = None,
    ) -> None:
        self._config = config
        self._store = store or InMemoryPlanStore()
        self._subagent_pool = subagent_pool or SubagentPool()

        # Tools
        self._create_tool = CreatePlanTool(self._store)
        self._get_tasks_tool = GetNextTasksTool(self._store)
        self._update_tool = UpdateTaskStatusTool(self._store)

        # ADK infrastructure
        if _runner is not None:
            self._session_service = _runner.session_service
            self._runner = _runner
            self._APP_NAME = getattr(_runner, "app_name", "plan_execute_orchestrator")
        else:
            self._APP_NAME = "plan_execute_orchestrator"
            self._session_service = InMemorySessionService()
            self._runner = Runner(
                app_name=self._APP_NAME,
                session_service=self._session_service,
            )

    def _build_planner_agent(self) -> LlmAgent:
        """Create the Pass 1 planning agent with structured ExecutionPlan output."""
        instruction = (
            "You are an expert project planner and software architect.\n"
            "Analyze the user's request and break it down into a highly optimized Directed Acyclic Graph (DAG) "
            "of tasks for specialized subagents.\n\n"
            "Rules for plan generation:\n"
            "1. Identify tasks that can run in parallel (independent tasks with no shared dependencies).\n"
            "2. Define dependencies clearly (a task must depend on another if it needs its output).\n"
            "3. Choose the appropriate specialist subagent for each task:\n"
            "   - Use 'DataAnalystAgent' for extracting metrics, consolidation, summarizing, and telemetry.\n"
            "   - Use 'ReporterAgent' for policy audits, compliance checks, or detailed rule validation.\n"
            "4. Specify realistic instructions in the 'description' field of each task.\n"
            "5. Generate a unique 'plan_id' (e.g. plan_<random_hex>) and realistic 'task_id's (e.g. task_01, task_02).\n"
            "6. Populate 'input_data' with any inputs extracted from the user's prompt.\n\n"
            "Ensure the generated plan strictly conforms to the ExecutionPlan JSON schema."
        )
        return LlmAgent(
            name="planner_agent",
            model=self._config.model_version,
            instruction=instruction,
            output_schema=ExecutionPlan,
            output_key="plan",
            include_contents="none",
        )

    def _build_replanner_agent(self) -> LlmAgent:
        """Create a lightweight agent to fix/re-evaluate failed task instructions."""
        instruction = (
            "You are a project recovery agent. A subagent failed to execute a task in the plan.\n"
            "Your job is to analyze the error message and the original task details, then output a modified "
            "task description or instruction that can bypass the issue or achieve the goal.\n"
            "Return the updated TaskDefinition matching the schema."
        )
        return LlmAgent(
            name="replanner_agent",
            model=self._config.model_version,
            instruction=instruction,
            output_schema=TaskDefinition,
            output_key="replanned_task",
            include_contents="none",
        )

    def _build_synthesis_agent(self) -> LlmAgent:
        """Create the Pass 2 synthesis agent for generating final user-facing responses."""
        instruction = (
            "You are a master reporter and coordinator.\n"
            "A complex plan has just finished executing. Review the complete log of all tasks, "
            "their descriptions, specialist subagents, inputs, outputs, and status.\n\n"
            "Synthesize a premium, professional, and elegant markdown report summarizing the work done.\n"
            "Rules:\n"
            "1. Highlight the overall success status of the plan.\n"
            "2. Show a summary of each task including the subagent type, status, and key results.\n"
            "3. Consolidate all telemetry and audit results into clean sections.\n"
            "4. Maintain a formal, high-impact Spanish tone (e.g. 'Informe Ejecutivo de Ejecución').\n"
            "5. Do NOT include raw JSON logs in the final text; present it beautifully."
        )
        return LlmAgent(
            name="synthesis_agent",
            model=self._config.model_version,
            instruction=instruction,
            include_contents="none",
        )

    async def generate_plan(self, prompt: str) -> ExecutionPlan:
        """Pass 1: Generate a valid ExecutionPlan using Gemini."""
        agent = self._build_planner_agent()
        session = await self._session_service.create_session(
            app_name=self._APP_NAME,
            user_id="default",
        )
        session_id = session.id
        
        new_message = types.Content(
            role="user",
            parts=[types.Part(text=prompt)],
        )
        
        self._runner.agent = agent
        async for event in self._runner.run_async(
            user_id="default",
            session_id=session_id,
            new_message=new_message,
        ):
            pass
            
        updated_session = await self._session_service.get_session(
            app_name=self._APP_NAME,
            user_id="default",
            session_id=session_id,
        )
        plan_dict = updated_session.state.get("plan")
        if not plan_dict:
            raise ValueError("Failed to generate plan structure from LLM.")
            
        # Force/inject correct timestamps and statuses
        plan = ExecutionPlan.model_validate(plan_dict)
        plan.global_status = PlanStatus.PENDING
        plan.created_at = datetime.now(timezone.utc).isoformat()
        plan.updated_at = datetime.now(timezone.utc).isoformat()
        return plan

    async def run(self, prompt: str, *, status_cb=None) -> str:
        """Run the full Plan-and-Execute pipeline: Plan, Parallel A2A, Re-plan, Synthesize."""
        # 1. Generate plan
        if status_cb is not None:
            status_cb.update("Orquestador: Planificando grafo de ejecución (Pass 1)...")
        logger.info(f"Generating plan for prompt: {prompt}")
        plan = await self.generate_plan(prompt)
        plan_id = plan.plan_id
        
        # Check if plan approval is enabled (approve_plan = True)
        if self._config.approve_plan:
            if status_cb is not None:
                status_cb.stop()
                
            from rich.console import Console
            from rich.table import Table
            
            c = Console()
            c.print("\n[bold gold1]========================================================================[/bold gold1]")
            c.print("[bold gold1]                  PROPUESTA DE PLAN DE EJECUCIÓN MULTIAGENTE            [/bold gold1]")
            c.print("[bold gold1]========================================================================[/bold gold1]")
            c.print(f"[bold cyan]ID del Plan:[/bold cyan] {plan.plan_id}")
            c.print(f"[bold cyan]Estado Global:[/bold cyan] {plan.global_status.value}")
            c.print("\n[bold]Tareas en el Grafo de Ejecución (DAG):[/bold]")
            
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("ID", style="dim", width=10)
            table.add_column("Nombre", style="bold", width=20)
            table.add_column("Especialista", style="magenta", width=18)
            table.add_column("Dependencias", style="yellow", width=15)
            table.add_column("Descripción", width=40)
            
            for t in plan.tasks:
                deps = ", ".join(t.dependencies) if t.dependencies else "-"
                table.add_row(t.task_id, t.name, t.agent_type, deps, t.description)
                
            c.print(table)
            c.print("[bold gold1]========================================================================[/bold gold1]")
            
            try:
                user_choice = input("\n[?] ¿Desea aprobar y ejecutar este plan? (s/n) [s]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                user_choice = "n"
                
            if user_choice not in ("", "s", "si", "y", "yes"):
                c.print("[red]✗ Ejecución del plan cancelada por el usuario.[/red]\n")
                return "### ✗ Plan de Ejecución Cancelado\n\nEl plan de ejecución multiagente propuesto fue rechazado por el usuario. No se realizaron cambios ni ejecuciones de subagentes."
                
            c.print("[green]✓ Plan aprobado. Iniciando ejecución de tareas...[/green]\n")
            
            if status_cb is not None:
                status_cb.start()

        # 2. Register plan via CreatePlanTool
        class DummySession:
            state: dict = {}
        class DummyInvocationContext:
            session = DummySession()
            
        tool_ctx = ToolContext(DummyInvocationContext())
        init_res = await self._create_tool.run_async(args={"plan": plan.model_dump()}, tool_context=tool_ctx)
        if "error" in init_res:
            raise ValueError(f"Plan initialization failed: {init_res['error']}")
            
        logger.info(f"Initialized plan {plan_id} with {len(plan.tasks)} tasks.")

        # 3. Deterministic execution loop
        while True:
            # Check for executable tasks
            get_res = await self._get_tasks_tool.run_async(args={"plan_id": plan_id}, tool_context=tool_ctx)
            if "error" in get_res:
                logger.error(f"Failed to fetch executable tasks: {get_res['error']}")
                break
                
            tasks_to_run = get_res.get("tasks", [])
            
            # If no tasks are ready, check if we are finished
            if not tasks_to_run:
                current_plan = await self._store.get_plan(plan_id)
                if current_plan.global_status in (PlanStatus.COMPLETED, PlanStatus.FAILED):
                    break
                # Guard against infinite deadlock/wait state
                all_done_or_failed = all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for t in current_plan.tasks)
                if all_done_or_failed:
                    break
                await asyncio.sleep(0.1)
                continue

            if status_cb is not None:
                task_names = ", ".join(t["name"] for t in tasks_to_run)
                status_cb.update(f"Orquestador: Ejecutando en paralelo: {task_names}...")
            logger.info(f"Dispatching {len(tasks_to_run)} tasks in parallel...")
            
            # Dispatch all executable tasks in parallel using asyncio.gather (NFR-1.1)
            async def run_single_task(task_dict: dict):
                t_id = task_dict["task_id"]
                agent_type = task_dict["agent_type"]
                desc = task_dict["description"]
                inputs = task_dict.get("input_data", {})

                # FR-3.2: Gather outputs from completed dependency tasks to feed as input
                # Fetch fresh plan state to read completed parent outputs
                fresh_plan = await self._store.get_plan(plan_id)
                for parent_id in task_dict.get("dependencies", []):
                    parent_task = next((pt for pt in fresh_plan.tasks if pt.task_id == parent_id), None)
                    if parent_task and parent_task.status == TaskStatus.COMPLETED and parent_task.output_data:
                        inputs.update(parent_task.output_data)

                try:
                    # Isolated A2A context dispatch (FR-3.1, FR-3.2, FR-3.3)
                    logger.info(f"[{t_id}] Spawning subagent {agent_type}...")
                    output = await self._subagent_pool.dispatch(
                        agent_type=agent_type,
                        task_id=t_id,
                        prompt=desc,
                        inputs=inputs,
                    )
                    
                    # Update status to COMPLETED
                    await self._update_tool.run_async(
                        args={
                            "plan_id": plan_id,
                            "task_id": t_id,
                            "status": "COMPLETED",
                            "output_data": output,
                        },
                        tool_context=tool_ctx,
                    )
                    logger.info(f"[{t_id}] Task completed successfully.")

                except Exception as ex:
                    logger.warning(f"[{t_id}] Task failed with error: {str(ex)}")
                    # Read retry count
                    current_plan = await self._store.get_plan(plan_id)
                    failed_task = next(pt for pt in current_plan.tasks if pt.task_id == t_id)
                    
                    if failed_task.retry_count < 3:
                        # Attempt automatic micro-replanning recovery (FR-4.1, FR-4.2)
                        failed_task.retry_count += 1
                        if status_cb is not None:
                            status_cb.update(f"Orquestador: Replanificando tarea fallida {t_id} (Intento {failed_task.retry_count}/3)...")
                        logger.info(f"[{t_id}] Attempting replanning retry {failed_task.retry_count}/3...")
                        
                        replanned = await self._replan_failed_task(failed_task, str(ex))
                        failed_task.description = replanned.description
                        failed_task.status = TaskStatus.PENDING  # Reset to pending for retry
                        
                        await self._store.save_plan(current_plan)
                    else:
                        # Max retries exceeded, fail task
                        await self._update_tool.run_async(
                            args={
                                "plan_id": plan_id,
                                "task_id": t_id,
                                "status": "FAILED",
                                "error_message": str(ex),
                            },
                            tool_context=tool_ctx,
                        )
                        logger.error(f"[{t_id}] Task failed permanently after 3 retries.")

            # Concurrently await all independent tasks
            await asyncio.gather(*(run_single_task(t) for t in tasks_to_run))

        # 4. Pass 2: Final response synthesis
        if status_cb is not None:
            status_cb.update("Orquestador: Sintetizando reporte ejecutivo final (Pass 2)...")
        final_plan = await self._store.get_plan(plan_id)
        logger.info(f"Execution finished with global status: {final_plan.global_status}")
        
        synthesis_agent = self._build_synthesis_agent()
        synth_session = await self._session_service.create_session(
            app_name=self._APP_NAME,
            user_id="default",
        )
        synth_session_id = synth_session.id
        
        # Compile complete execution context into synthesis prompt
        execution_log = json.dumps(final_plan.model_dump(), indent=2)
        synthesis_prompt = (
            f"El plan original del usuario fue: '{prompt}'\n\n"
            f"A continuación se detalla el log de ejecución completo del plan:\n"
            f"```json\n{execution_log}\n```\n\n"
            f"Genera el informe final del orquestador."
        )

        synth_message = types.Content(
            role="user",
            parts=[types.Part(text=synthesis_prompt)],
        )

        response_parts = []
        self._runner.agent = synthesis_agent
        async for event in self._runner.run_async(
            user_id="default",
            session_id=synth_session_id,
            new_message=synth_message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and not part.thought:
                        response_parts.append(part.text)

        return "".join(response_parts)

    async def _replan_failed_task(self, task: TaskDefinition, error: str) -> TaskDefinition:
        """Call Gemini to replan a failed task and generate improved instructions."""
        replanner = self._build_replanner_agent()
        session = await self._session_service.create_session(
            app_name=self._APP_NAME,
            user_id="default",
        )
        session_id = session.id
        
        prompt = (
            f"Tarea Fallida:\n"
            f"ID: {task.task_id}\n"
            f"Nombre: {task.name}\n"
            f"Descripción: {task.description}\n"
            f"Subagente: {task.agent_type}\n\n"
            f"Error Técnico de Ejecución:\n"
            f"{error}\n\n"
            f"Genera una versión mejorada de esta tarea con instrucciones detalladas para solucionar el problema."
        )
        
        new_message = types.Content(
            role="user",
            parts=[types.Part(text=prompt)],
        )

        self._runner.agent = replanner
        async for _ in self._runner.run_async(
            user_id="default",
            session_id=session_id,
            new_message=new_message,
        ):
            pass

        updated_session = await self._session_service.get_session(
            app_name=self._APP_NAME,
            user_id="default",
            session_id=session_id,
        )
        replanned_dict = updated_session.state.get("replanned_task")
        if not replanned_dict:
            # Fallback to original task details on replanning error
            return task
            
        return TaskDefinition.model_validate(replanned_dict)
