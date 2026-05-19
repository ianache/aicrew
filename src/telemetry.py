"""
Telemetry — Dynamic real-time terminal dashboard visualization using rich.live (PRD-004 compliance).
"""
import time
from datetime import datetime
from typing import List, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.live import Live


class CrewTelemetry:
    """Manages execution state and paints a flicker-free dynamic terminal dashboard using rich.live."""

    def __init__(self, target_goal: str) -> None:
        self.target_goal = target_goal
        self.status = "RUNNING"  # RUNNING | COMPLETED | FAILED
        self.pipeline: List[Dict[str, Any]] = []
        self.logs: List[str] = []
        self.console = Console()
        self._live: Live | None = None

    def register_task(self, task_id: str, step_num: int, task_name: str, agent_role: str) -> None:
        """Register a new task in the pipeline with PENDING status."""
        self.pipeline.append({
            "id": task_id,
            "step": step_num,
            "task_name": task_name,
            "agent": agent_role,
            "skill_applied": "-",
            "status": "PENDING",  # PENDING | RUNNING | COMPLETED | FAILED
            "started_at": None,
            "finished_at": None,
        })

    def start_task(self, task_id: str) -> None:
        """Set task status to RUNNING and record start time."""
        for task in self.pipeline:
            if task["id"] == task_id:
                task["status"] = "RUNNING"
                task["started_at"] = time.time()
                self.add_log(f"Iniciando tarea: {task['task_name']} (con {task['agent']})")
                break
        self.refresh()

    def complete_task(self, task_id: str) -> None:
        """Set task status to COMPLETED and record finish time."""
        for task in self.pipeline:
            if task["id"] == task_id:
                task["status"] = "COMPLETED"
                task["finished_at"] = time.time()
                self.add_log(f"✓ Tarea completada: {task['task_name']}")
                break
        self.refresh()

    def fail_task(self, task_id: str, error: str) -> None:
        """Set task status to FAILED, record finish time, and mark global state as FAILED."""
        for task in self.pipeline:
            if task["id"] == task_id:
                task["status"] = "FAILED"
                task["finished_at"] = time.time()
                self.add_log(f"❌ Tarea falló: {task['task_name']} - Error: {error}")
                break
        self.status = "FAILED"
        self.refresh()

    def update_agent_step(self, task_id: str, skill: str, thought: str) -> None:
        """Update active skill and append agent thought/log."""
        for task in self.pipeline:
            if task["id"] == task_id:
                task["skill_applied"] = skill
                break
        if thought:
            self.add_log(thought)
        self.refresh()

    def add_log(self, text: str) -> None:
        """Add log entry with timestamp, keeping only the last 4 logs."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {text}")
        if len(self.logs) > 4:
            self.logs.pop(0)

    def build_dashboard(self) -> Layout:
        """Construct the rich Layout showing cabecera, body table, progress bar, and logs feed."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body", minimum_size=8),
            Layout(name="progress", size=3),
            Layout(name="footer", size=7)
        )

        status_colors = {"RUNNING": "bold yellow", "COMPLETED": "bold green", "FAILED": "bold red"}
        status_emoji = {"RUNNING": "⏳ EN EJECUCIÓN", "COMPLETED": "✅ COMPLETADO", "FAILED": "❌ FALLIDO"}

        header_text = (
            f"[bold cyan]🎯 Objetivo Global:[/bold cyan] {self.target_goal}\n"
            f"[bold cyan]📊 Estado General:[/bold cyan] [{status_colors[self.status]}]{status_emoji[self.status]}[/]"
        )
        layout["header"].update(Panel(header_text, title="🤖 CrewAI Execution Telemetry", border_style="blue"))

        table = Table(expand=True, show_edge=False, box=None)
        table.add_column("ID", style="dim", width=8)
        table.add_column("Paso", width=6, justify="center")
        table.add_column("Tarea / Paso", ratio=2)
        table.add_column("Agente", style="magenta", ratio=1)
        table.add_column("Skill Aplicado", style="green", ratio=1)
        table.add_column("Estado", justify="center", width=15)

        status_styles = {
            "PENDING": "[grey50]💤 PENDING[/]",
            "RUNNING": "[bold yellow]⏳ RUNNING[/]",
            "COMPLETED": "[bold green]✅ COMPLETED[/]",
            "FAILED": "[bold red]❌ FAILED[/]"
        }

        for task in self.pipeline:
            table.add_row(
                task["id"],
                str(task["step"]),
                task["task_name"],
                task["agent"],
                task["skill_applied"],
                status_styles[task["status"]]
            )
        layout["body"].update(Panel(table, title="📋 Pipeline de Ejecución", border_style="grey30"))

        # Progress bar
        completed = sum(1 for t in self.pipeline if t["status"] == "COMPLETED")
        total = len(self.pipeline) or 1

        progress = Progress(
            TextColumn("[bold cyan]Progreso Global:[/]"),
            BarColumn(bar_width=40, complete_style="green", finished_style="bold green"),
            TextColumn("[bold green]{task.percentage:>3.0f}%[/]"),
        )
        p_task = progress.add_task("tasks", total=total)
        progress.update(p_task, completed=completed)
        layout["progress"].update(Panel(progress, border_style="grey30"))

        feed_content = "\n".join(self.logs) if self.logs else "[dim]Esperando eventos de agentes...[/dim]"
        layout["footer"].update(Panel(feed_content, title="💬 Pensamiento de los Agentes en Vivo", border_style="grey30"))

        return layout

    def start(self) -> None:
        """Start the dynamic live render display capturing the terminal screen."""
        self._live = Live(self.build_dashboard(), refresh_per_second=4, screen=True)
        self._live.start()

    def refresh(self) -> None:
        """Force dashboard refresh update in live display."""
        if self._live:
            self._live.update(self.build_dashboard())

    def stop(self) -> None:
        """Stop the live display and restore the original terminal screen."""
        if self._live:
            self._live.stop()
            self._live = None
