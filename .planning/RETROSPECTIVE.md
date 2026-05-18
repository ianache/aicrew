# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-05-17
**Phases:** 6 | **Plans:** 11 | **Sessions:** 2 (one build day + one resume)

### What Was Built
- `DenoRunner` — asyncio subprocess wrapper with 5000ms timeout, Windows process tree cleanup, typed result union
- `SkillInjector` — ADK `BaseTool` subclass converting `SkillDefinition` to live tool with JSON Schema validation and SKILL.md injection
- `CoordinatingAgent` — three-path ADK routing (Pass 1 tag extraction, direct answer, Pass 2 tool-injected) with JSONL decision log
- `CatalogExplorer` — GitHub catalog reader with OR-logic tag matching, description-word fallback, TTL cache
- `main.py` REPL — Rich spinner, structured error messages, `load_dotenv()` first pattern
- `SkillCache` — git clone lifecycle manager (lazy, 5-min TTL via `.last-sync`, partial-clone self-heal, soft-fail on pull)
- Full local execution: catalog reads from `.skills-cache/` clone; Deno executes local `.ts` files with `--allow-read` scoping

### What Worked
- **TDD-first on every module** — writing tests before implementation caught interface ambiguities early (especially ADK BaseTool vs FunctionTool)
- **Phase-by-phase independence** — each phase produced a testable artifact; nothing was wired E2E until Phase 5; made debugging straightforward
- **Deferred integration** — building DenoRunner with zero ADK dependency meant Windows process issues were isolated and fixable in isolation
- **Post-execution fixes** — catching the `additionalProperties` Gemini schema issue and `refs/heads/main` URL format after Phase 5 in a structured "fixes" block was cleaner than spreading them across phases
- **Research before planning** — the researcher agent catching the `skills.json` plural vs. `skill.json` singular discrepancy before any code was written saved a full debugging cycle

### What Was Inefficient
- **Live E2E test rate limit hit** — the `GOOGLE_API_KEY` vs `GEMINI_API_KEY` env var conflict was discovered late (post-Phase-5) and required manual fix; a pre-flight env var check in `main.py` would have surfaced this in Phase 3
- **Plan 06-03 rate limit** — execution hit the Claude rate limit mid-plan, requiring a manual resume; context was preserved well but the interruption added friction
- **`catalog.yaml` tag structure discovery** — the live catalog has no explicit `tags` field; the description-word fallback was invented in Phase 4 when the real catalog was first hit; earlier live catalog inspection in research would have avoided this
- **`skills.json` plural** — discovered only in Phase 4 live testing; a single `curl` during Phase 4 research would have caught it

### Patterns Established
- **`proc.communicate()` not `proc.wait()`** — mandatory on Windows for any subprocess with stdout; `proc.wait()` deadlocks at ~4KB pipe buffer
- **`BaseTool._get_declaration()` explicit schema** — `FunctionTool` drops `**kwargs` in ADK 1.33.0; always use explicit `BaseTool` subclass for dynamic tools
- **Three routing paths** — `output_schema` always returns structured JSON, not natural language; direct-answer path needs its own agent branch
- **`additionalProperties:false` strip before Gemini** — ADK `types.Schema` rejects unknown keys at `_get_declaration()` time; normalize before passing
- **`.last-sync` file for persistent TTL** — in-memory `time.monotonic()` cache resets on every process restart; file-based timestamp survives restarts with zero overhead
- **`entry_point` in `skills.json`** — multi-file skills need explicit entry point declaration; `index.ts` default is not enough for complex skills

### Key Lessons
1. **Inspect the live catalog before writing catalog code** — structure assumptions (tag fields, file naming) always differ from what you expect; a single HTTP request in research saves a phase of rework
2. **`google-genai` version upper bound is non-negotiable** — `<2` must be pinned; v2 breaks ADK 1.33.0 with no warning at install time
3. **Windows subprocess requires different patterns** — `taskkill /F /T /PID`, `communicate()` not `wait()`, `Path.as_posix()` for flags — these are not optional; verify on the actual target platform in Phase 1
4. **The plan checker's verify steps matter** — import-only verify steps missed behavioral changes (httpx removal, SkillCache wiring) in Phase 6; verify steps should check the actual behavioral guarantee, not just "module imports"
5. **Post-launch bug fixes belong in a named block, not a new phase** — the 8 post-Phase-5 fixes were cleaner as a named "fixes applied" block than as Phase 6 scope creep; Phase 6 remained architecturally clean

### Cost Observations
- Model mix: ~100% sonnet (profile: sonnet for all agents)
- Sessions: 2 — one full build day, one resume session
- Notable: Full platform from zero to verified v1.0 in ~1 day, ~27 min of plan execution time across 11 plans

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | 2 | 6 | First milestone — established all base patterns |

### Cumulative Quality

| Milestone | Tests | Zero-Dep Additions |
|-----------|-------|--------------------|
| v1.0 | 62 non-live | DenoRunner (no ADK), models/results.py (no ADK/Deno) |

### Top Lessons (Verified Across Milestones)

1. Inspect live external dependencies (APIs, catalogs, schemas) during research — never assume structure matches documentation
2. `proc.communicate()` over `proc.wait()` for Windows subprocess with piped stdout is non-negotiable
