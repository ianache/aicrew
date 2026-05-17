"""
AI Agents Crew — CLI REPL entry point.

Wires all platform components into a terminal REPL with a two-phase Rich spinner:
- Phase 1 (always): "Thinking..." spinner while the agent extracts tags and routes
- Phase 2 (catalog route only): spinner updates to "Running skill..." when Deno executes

Usage:
    uv run python main.py

Requires:
    GEMINI_API_KEY set in .env or environment (loaded via python-dotenv)
    GITHUB_TOKEN recommended (raises GitHub rate limit from 60 to 5000 req/hr)

Design decisions (from CONTEXT.md):
- load_dotenv() is the FIRST statement in main() — before any Config or os.environ reads
- console.print() is called AFTER the with console.status() block exits — not inside it
- KeyboardInterrupt and EOFError are caught at the input() call, not as bare Exception
- sys.exit() is NOT used — return from async main() for error exits
- One Console() instance reused for all output (not recreated inside loop)
"""
import asyncio
from dotenv import load_dotenv
from rich.console import Console

from src.config import Config
from src.agent import CoordinatingAgent
from src.catalog_explorer import CatalogExplorer
from src.skill_injector import SkillInjector
from src.execution.deno_runner import DenoRunner


console = Console()

# Error response prefixes — used to route output to red-colored display
ERROR_PREFIXES = (
    "Skill timed out",
    "Skill failed",
    "Skill validation failed",
    "No matching skill",
    "Skill domain validation",
)


async def main() -> None:
    """Entry point: load env, wire dependencies, run REPL loop."""
    # FIRST: load .env before any Config or os.environ reads (CLAUDE.md constraint)
    load_dotenv()

    # Config construction — raises KeyError if GEMINI_API_KEY not set
    try:
        config = Config.from_env()
    except KeyError:
        console.print("[red]Error: GEMINI_API_KEY not set. Add it to .env or export it.[/red]")
        return

    # Dependency wiring (matching architecture layer diagram from CLAUDE.md)
    runner = DenoRunner()
    injector = SkillInjector(runner)
    explorer = CatalogExplorer(config)
    agent = CoordinatingAgent(explorer, injector, config)

    # Banner
    console.print("AI Agents Crew v1.0")
    console.print("Type exit to quit.")

    # REPL loop
    while True:
        try:
            prompt = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        prompt = prompt.strip()

        # Silent skip for empty/whitespace-only input
        if not prompt:
            continue

        # Exit commands
        if prompt.lower() in ("exit", "quit"):
            console.print("Bye.")
            break

        # Agent invocation — spinner wraps the full agent.run() call
        # console.print() is called AFTER the with block exits (pitfall 3 from research)
        with console.status("Thinking...") as status:
            response = await agent.run(prompt, status_cb=status)

        # Blank line for visual separation
        console.print("")

        # Error vs. success display
        if any(response.startswith(p) for p in ERROR_PREFIXES):
            console.print(f"[red]{response}[/red]")
        else:
            console.print(response)


if __name__ == "__main__":
    asyncio.run(main())
