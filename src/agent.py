"""
CoordinatingAgent — Two-pass routing orchestrator for the AI Agents Crew platform.

Routes user prompts through a confidence-gated two-pass flow:
  Pass 1: LlmAgent with output_schema=TagExtractionResult extracts {confidence, tags}
           constrained to the catalog's actual tag vocabulary.
  High-confidence path (confidence >= threshold): Run a direct-answer LlmAgent (no schema,
           no tools) to produce a natural-language response.
  Low-confidence path (confidence < threshold): Call CatalogExplorer.find(tags).
    - Skill found: Build Pass 2 LlmAgent with injected skill tool + SKILL.md context.
    - No skill found: Return hardcoded 'no skill found' message.

Every run() call appends a JSONL record to logs/routing.jsonl with:
  prompt_hash, tags, confidence, decision, skill_name, ts

Design constraints (from CLAUDE.md and RESEARCH.md):
- One Runner per CoordinatingAgent instance — Runner.__init__ is expensive
- Fresh InMemorySessionService per run() call — prevents unbounded memory growth (Pitfall 5)
- Always create a fresh LlmAgent for each pass — never mutate agent.tools (Pitfall 4)
- Always include_contents='none' on all agents — prevent history contamination (Pitfall 2)
- Read session.state AFTER async for loop completes — not during iteration (Pitfall 2)
- Always use routing.get('confidence', 0.0) — dict access, not attribute access (Pitfall 3)
- Pass 1 ONLY does structured extraction — never returns natural language (Pitfall 1)
- NEVER use global_instruction — deprecated in ADK 1.33.0, use instruction field

Anti-patterns avoided:
- Never append to agent.tools — always create fresh LlmAgent for each pass
- Never read session.state['routing'] inside async for loop
- Never access routing.confidence — use routing.get('confidence', 0.0)
- Never create Runner per run() call (expensive __init__)
- Never use proc.wait() (deadlocks) — but that is DenoRunner's concern
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.config import Config
from src.skill_injector import SkillInjector
from src.orchestrator import PlanAndExecuteOrchestrator


# ---------------------------------------------------------------------------
# Routing log path — monkeypatched in tests via src.agent._LOG_PATH
# ---------------------------------------------------------------------------

_LOG_PATH = Path("logs/routing.jsonl")


# ---------------------------------------------------------------------------
# TagExtractionResult — structured output schema for Pass 1
# ---------------------------------------------------------------------------

class TagExtractionResult(BaseModel):
    """Pydantic model for structured output from Pass 1 tag extraction agent.

    ADK stores this as a dict in session.state['routing'] — access via .get(),
    not attribute access (validate_schema returns dict, not Pydantic instance).
    """

    confidence: float
    """Self-reported confidence (0.0-1.0) that the prompt can be answered directly."""

    tags: list[str]
    """1-3 intent tags from the catalog's tag vocabulary."""


# ---------------------------------------------------------------------------
# _write_routing_log — append one JSONL record per run() call
# ---------------------------------------------------------------------------

def _write_routing_log(
    prompt: str,
    tags: list[str],
    confidence: float,
    decision: str,
    skill_name: str | None,
) -> None:
    """Append one JSON-lines record to logs/routing.jsonl.

    Creates the logs/ directory if it does not exist.
    Always appends — never overwrites. JSONL format: one JSON object per line.

    Args:
        prompt: The original user prompt (hashed to 12-char hex for privacy).
        tags: Extracted intent tags from Pass 1.
        confidence: Self-reported confidence score from Pass 1.
        decision: Routing outcome — 'direct_answer', 'catalog_route', or 'no_skill_found'.
        skill_name: Name of matched skill (or None for direct-answer and no-skill-found paths).
    """
    record = {
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12],
        "tags": tags,
        "confidence": confidence,
        "decision": decision,
        "skill_name": skill_name,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# _extract_final_text — extract natural language from event stream
# ---------------------------------------------------------------------------

def _extract_final_text(events) -> str:
    """Extract final text from an iterable of ADK events (synchronous helper).

    This function is not async — it operates on an already-collected list of events
    or is called inline within the async for loop. Filters out thought parts.
    """
    # Not used directly — text extraction is done inline in run() for async iteration
    raise NotImplementedError("Use inline extraction inside async for loop")


# ---------------------------------------------------------------------------
# CoordinatingAgent — public API
# ---------------------------------------------------------------------------

class CoordinatingAgent:
    """Two-pass routing orchestrator that delegates to CatalogExplorer and SkillInjector.

    Construction injects all dependencies (no globals, no env reads here).
    One Runner per instance — Runner.__init__ is expensive, do not recreate per run().
    Pass 1 agent is built once at construction time (static vocabulary populated lazily).
    Pass 2 agent is built fresh for each low-confidence run() call.

    Usage:
        config = Config.from_env()
        agent = CoordinatingAgent(catalog_explorer, skill_injector, config)
        response = await agent.run("Evaluate this test case")
    """

    _APP_NAME = "coordinating_agent"
    _USER_ID = "default"

    def __init__(
        self,
        catalog_explorer,
        skill_injector: SkillInjector,
        config: Config,
        *,
        _runner: Runner | None = None,
        _session_service: InMemorySessionService | None = None,
    ) -> None:
        """Initialize CoordinatingAgent with injected dependencies.

        Args:
            catalog_explorer: Duck-typed CatalogExplorer — must expose find(tags) and get_all_tags().
            skill_injector: SkillInjector instance for building ADK tools from SkillDefinitions.
            config: Frozen Config dataclass with threshold, model version, and API key.
            _runner: Optional Runner override for testing (avoids expensive Runner.__init__).
            _session_service: Optional InMemorySessionService override for testing.
        """
        self._catalog_explorer = catalog_explorer
        self._skill_injector = skill_injector
        self._config = config

        # Pass 1 agent — static; built once at construction.
        # Tag vocabulary is injected lazily in run() after get_all_tags() resolves.
        # The instruction template is formatted per run() call.
        self._pass1_agent = LlmAgent(
            name="coordinating_agent_pass1",
            model=config.model_version,
            instruction=self._build_pass1_instruction([]),  # placeholder — updated in run()
            output_schema=TagExtractionResult,
            output_key="routing",
            include_contents="none",
        )

        # Session service — one fresh service per run() (see Pitfall 5)
        # Overridable for testing via _session_service parameter.
        self._session_service = _session_service or InMemorySessionService()

        # Runner — one per instance; expensive to create
        self._runner = _runner or Runner(
            app_name=self._APP_NAME,
            agent=self._pass1_agent,
            session_service=self._session_service,
        )

        # Plan-and-Execute Orchestrator (PRD-004)
        self._orchestrator = PlanAndExecuteOrchestrator(
            config=config,
            _runner=self._runner,
        )

    @staticmethod
    def _build_pass1_instruction(tag_vocabulary: list[str]) -> str:
        """Build the Pass 1 system instruction with the tag vocabulary constraint.

        The tag vocabulary is injected into the prompt so the LLM produces only
        catalog-valid tags — no open-vocabulary mismatch (DISC-02 requirement).
        """
        vocab_str = ", ".join(tag_vocabulary) if tag_vocabulary else "(none available)"
        return (
            f"You are a routing agent. Analyze the user prompt and extract routing metadata.\n"
            f"Return a JSON object with exactly these fields:\n"
            f"- confidence: float between 0.0 and 1.0 — how confident you are that you can "
            f"answer the prompt DIRECTLY from your training knowledge, WITHOUT executing any "
            f"external tool, API call, database query, or automated process\n"
            f"- tags: list of 1-3 tags from this vocabulary ONLY: [{vocab_str}]\n\n"
            f"Confidence calibration:\n"
            f"- HIGH (>= 0.72): factual questions, explanations, general knowledge "
            f"(e.g. 'What is Python?', 'Explain REST APIs')\n"
            f"- LOW (< 0.72): requests that require executing a process, fetching external data, "
            f"evaluating a specific artifact, creating/registering something in a system, or "
            f"performing domain-specific automated analysis "
            f"(e.g. 'evalúa el test case 1', 'registra esta historia de usuario', "
            f"'analyze issue #42', 'run the quality check')\n\n"
            f"Tag selection rules (CRITICAL — intent determines tags):\n"
            f"- 'evalúa', 'evaluar', 'evaluate', 'review', 'check quality' → use 'assessment' or 'quality'; do NOT use 'specification'\n"
            f"- 'especifica', 'especificar', 'crea', 'crear', 'define', 'write', 'redacta' → use 'specification'\n"
            f"- 'test case', 'caso de prueba' → use 'test case'\n"
            f"- 'historia de usuario', 'user story' → use 'user story'\n"
            f"- The ACTION verb (evaluar vs especificar) determines the intent tag — read it carefully\n\n"
            f"Rules:\n"
            f"- If the prompt asks to DO something in an external system → confidence < 0.72\n"
            f"- If the prompt asks to EVALUATE a specific artifact → confidence < 0.72\n"
            f"- If you can answer from knowledge alone → confidence >= 0.72\n"
            f"- Only use tags from the provided vocabulary — do not invent tags\n"
            f"- Always return valid JSON matching the schema"
        )

    @staticmethod
    def _build_pass2_instruction(skill_md: str) -> str:
        """Build the Pass 2 system instruction, optionally appending the SKILL.md guide."""
        base = (
            "You are an execution agent. Use the available tool to fulfill the user's request.\n\n"
            "Once you execute the tool and receive the results, you MUST use that information to "
            "fully address and answer the user's original request. If the user asked you to evaluate, "
            "analyze, critique, or summarize the fetched data, perform a thorough, professional, "
            "and complete evaluation or analysis in your final response rather than just outputting the "
            "raw tool results.\n\n"
            "IMPORTANT — error relay rule: if the tool returns a message that starts with "
            "'Skill failed', 'Skill timed out', or 'Skill validation failed', relay that exact "
            "message to the user WITHOUT rewording or wrapping it in a generic error explanation. "
            "Show the technical detail as-is so the user can diagnose the problem."
        )
        if skill_md.strip():
            return f"{base}\n\n---\n{skill_md}"
        return base

    async def run(self, prompt: str, *, status_cb=None) -> str:
        """Route a user prompt through the two-pass confidence-gated loop.

        Returns a natural language response string in all cases.

        Routing paths:
        1. Pass 1 extracts confidence + tags (always runs)
        2. confidence >= threshold → direct-answer agent (no schema, no tools)
        3. confidence < threshold → catalog_explorer.find(tags)
           a. Skill found → Pass 2 with injected tool
           b. No skill found → hardcoded 'no skill found' message

        JSONL log record is written at end of every run() regardless of decision.
        """
        # Step 0: Route to orchestrator if approve_plan is enabled OR if prompt has planning/multi-agent keywords
        planning_keywords = ["orquestar", "orquestacion", "orquestación", "plan", "multiagente", "crew", "flow", "flujo", "dag"]
        prompt_lower = prompt.lower()
        if self._config.approve_plan or any(kw in prompt_lower for kw in planning_keywords):
            _write_routing_log(prompt, [], 0.0, "plan_and_execute", None)
            return await self._orchestrator.run(prompt, status_cb=status_cb)

        # Step 1: Fetch tag vocabulary and update Pass 1 agent instruction
        tag_vocabulary = await self._catalog_explorer.get_all_tags()
        self._pass1_agent.instruction = self._build_pass1_instruction(tag_vocabulary)

        # Step 2: Create fresh session per run() call
        session = await self._session_service.create_session(
            app_name=self._APP_NAME,
            user_id=self._USER_ID,
        )
        session_id = session.id

        new_message = types.Content(
            role="user",
            parts=[types.Part(text=prompt)],
        )

        # Step 3: Run Pass 1 — structured tag + confidence extraction
        self._runner.agent = self._pass1_agent
        async for _event in self._runner.run_async(
            user_id=self._USER_ID,
            session_id=session_id,
            new_message=new_message,
        ):
            pass  # state_delta applied during iteration; read state AFTER loop

        # Step 4: Read routing state AFTER loop completes (Pitfall 2)
        updated_session = await self._session_service.get_session(
            app_name=self._APP_NAME,
            user_id=self._USER_ID,
            session_id=session_id,
        )
        routing: dict = updated_session.state.get("routing", {})
        confidence: float = routing.get("confidence", 0.0)  # dict access, not .confidence
        tags: list[str] = routing.get("tags", [])

        final_text = ""
        skill_name: str | None = None
        decision = "direct_answer"

        # Step 5: Route based on confidence threshold
        if confidence < self._config.confidence_threshold:
            # Low-confidence path: delegate to catalog
            skill_def = await self._catalog_explorer.find(tags)
            if skill_def is not None:
                # Skill found: build fresh Pass 2 agent with injected tool
                tool, skill_md = await self._skill_injector.build_tool(skill_def)
                skill_name = skill_def.name
                decision = "catalog_route"

                if status_cb is not None:
                    status_cb.update(f"Running skill: {skill_def.name}...")

                pass2_agent = LlmAgent(
                    name="coordinating_agent_pass2",
                    model=self._config.model_version,
                    instruction=self._build_pass2_instruction(skill_md),
                    tools=[tool],
                    include_contents="none",
                )
                self._runner.agent = pass2_agent

                async for event in self._runner.run_async(
                    user_id=self._USER_ID,
                    session_id=session_id,
                    new_message=new_message,
                ):
                    if event.is_final_response() and event.content and event.content.parts:
                        text = "".join(
                            p.text
                            for p in event.content.parts
                            if p.text and not p.thought
                        )
                        if text.strip():
                            final_text = text
            else:
                # No skill found
                decision = "no_skill_found"
                final_text = "No matching skill found for your request."
        else:
            # High-confidence path: run direct-answer agent (no schema, no tools)
            decision = "direct_answer"
            direct_agent = LlmAgent(
                name="coordinating_agent_direct",
                model=self._config.model_version,
                instruction="Answer the user's prompt directly and helpfully.",
                include_contents="none",
            )
            self._runner.agent = direct_agent

            async for event in self._runner.run_async(
                user_id=self._USER_ID,
                session_id=session_id,
                new_message=new_message,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    text = "".join(
                        p.text
                        for p in event.content.parts
                        if p.text and not p.thought
                    )
                    if text.strip():
                        final_text = text

        # Step 6: Write JSONL routing log — always, regardless of decision
        _write_routing_log(prompt, tags, confidence, decision, skill_name)

        return final_text
