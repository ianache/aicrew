# Pitfalls Research

**Domain:** Agentic platform — dynamic skill discovery, LLM tool injection, subprocess sandboxing
**Researched:** 2026-05-16
**Confidence:** MEDIUM (no WebSearch/WebFetch permitted; conclusions drawn from training-data knowledge of ADK, Deno, asyncio, JSON Schema, and GitHub API. All claims flagged with confidence level.)

---

## Critical Pitfalls

### Pitfall 1: Tool Schema Bloat Exhausts Gemini Context Window

**What goes wrong:**
Each skill injected as an ADK tool carries its full `skill.json` schema in the context window. Gemini models have a fixed token budget shared between the system prompt, tool schemas, conversation history, and the user prompt. When the catalog grows beyond ~15-20 skills and all are injected at once, the tool schema payload alone can consume 20-40k tokens, leaving little room for conversation history and causing silent truncation or API errors.

**Why it happens:**
Developers treat tool injection as "free" — they assume the LLM can handle any number of tools. In practice, each tool schema serialized to JSON adds 200-800 tokens depending on description verbosity and parameter count. ADK does not automatically truncate or paginate tools.

**How to avoid:**
- Enforce a hard cap of 8-12 injected tools per invocation (tune empirically against Gemini Flash/Pro limits).
- The CatalogExplorer's tag-filtering is the correct gate — ensure it returns at most N candidates before injection, not all matching skills.
- Measure token count of assembled tool list before calling the model: use `google.genai.types.count_tokens()` on the tool declarations payload.
- Keep `skill.json` descriptions concise: parameter descriptions under 60 chars, skill description under 120 chars.

**Warning signs:**
- Gemini API returns `400 INVALID_ARGUMENT` with "request payload too large" or "too many tokens."
- Model starts hallucinating parameter names that don't exist in any real skill (context bleed from truncation).
- Latency spikes suddenly when catalog grows past a certain size.

**Phase to address:**
Skill injection phase (core agent loop). Add token-count assertion as a pre-injection guard. Test with a catalog of 30+ skills early to expose the limit before shipping.

---

### Pitfall 2: Deno Subprocess Zombie Processes on Timeout

**What goes wrong:**
When Python's `asyncio.create_subprocess_exec()` launches Deno and the 5000ms timeout triggers `process.kill()`, the Deno process is sent SIGKILL/SIGTERM but its child processes (if Deno spawned any via `Deno.Command`) are not killed. On Linux/macOS, these become orphaned. On Windows, `asyncio` subprocess termination is even less reliable — `process.terminate()` calls `TerminateProcess()` but does not kill the job tree.

**Why it happens:**
`asyncio.wait_for()` cancels the coroutine awaiting the process, but cancellation only calls `process.kill()` on the top-level Deno PID. The OS does not automatically reap grandchild processes.

**How to avoid:**
- Use `asyncio.create_subprocess_exec()` with `start_new_session=True` on POSIX, then on timeout call `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` to kill the entire process group.
- On Windows, wrap the subprocess in a Windows Job Object (or use `subprocess.CREATE_NEW_PROCESS_GROUP` + `taskkill /F /T /PID`) — this is the only reliable approach for job-tree termination on Windows.
- Add a process registry: track all spawned Deno PIDs in a module-level set, and register an `atexit` handler and signal handler (`SIGINT`, `SIGTERM`) that kills all tracked PIDs before the Python process exits.
- Deno skills should not spawn subprocesses themselves (enforce via `--no-prompt` and absence of `--allow-run` flag).

**Warning signs:**
- `ps aux | grep deno` shows Deno processes with PPID 1 (reparented to init) after test runs.
- Memory usage of the host machine grows across repeated test runs.
- Integration tests intermittently hang when run in rapid succession (port conflicts from un-reaped processes that held sockets).

**Phase to address:**
Deno execution channel phase. The process cleanup logic must be in the first working implementation — retrofitting it later after the agent is being used is painful because the pattern spreads across the codebase.

---

### Pitfall 3: Confidence Threshold Is Model-Version-Dependent

**What goes wrong:**
The 0.72 confidence threshold for triggering CatalogExplorer is calibrated against one specific Gemini model version. When Google silently updates the underlying model weights (as they routinely do with `gemini-2.0-flash` or `gemini-1.5-pro`), the distribution of confidence scores shifts. A threshold that was well-calibrated produces too many or too few catalog fetches after the model update, without any code change on your side.

**Why it happens:**
Confidence scores from LLMs are not absolute probabilities — they are relative logit-derived values that depend on training distribution. Model updates change these distributions.

**How to avoid:**
- Pin the model version explicitly (`model="gemini-2.0-flash-001"` not `"gemini-2.0-flash"`), and treat model version bumps as requiring threshold re-calibration.
- Log every routing decision: `{prompt_hash, extracted_tags, confidence_score, decision: "use_cached" | "fetch_catalog"}`. Build a calibration dataset from these logs.
- Implement a dry-run mode that runs both paths (cached + catalog fetch) and compares results, allowing offline threshold calibration without live traffic.
- Consider confidence band rather than hard threshold: if confidence is 0.65-0.80, log as "uncertain" even if the cached path is taken, for post-hoc review.

**Warning signs:**
- Catalog fetch rate changes dramatically (up or down) without changes to user prompt patterns.
- Users report that previously-recognized intents now fail to match skills.
- After a `requirements.txt` or ADK version bump, routing behavior changes.

**Phase to address:**
Core agent routing phase. The threshold value should live in config (not hardcoded) from day one. Add a metrics sink (even just a JSONL log file) in the first working loop.

---

### Pitfall 4: GitHub API Rate Limiting Breaks Catalog Fetch

**What goes wrong:**
Unauthenticated GitHub API requests are limited to 60 requests per hour per IP. Each `catalog.yaml` fetch is one request. Each `skill.json` lazy-load is another request. A session that matches 10 prompts to different skills can consume 11+ API calls. In a development environment where tests hit the live repo (as noted in PROJECT.md), running the test suite twice in rapid succession hits the rate limit.

**Why it happens:**
GitHub's raw content endpoint (`raw.githubusercontent.com`) is not rate-limited the same way as the API, but the GitHub API endpoint (`api.github.com/repos/.../contents/...`) is. If CatalogExplorer uses the API endpoint (for branch-aware fetching or metadata), it hits the 60/hour ceiling fast.

**How to avoid:**
- Use `raw.githubusercontent.com` for content fetching (not the GitHub API) — it has much higher limits and is CDN-backed.
- Implement a TTL-based in-memory cache (5-minute TTL) for `catalog.yaml` — most sessions do not need a fresh catalog on every prompt.
- For `skill.json` files, cache indefinitely per session (they don't change between catalog refreshes).
- Add a GitHub PAT as an optional environment variable (`GITHUB_TOKEN`). When set, authenticate requests to raise the limit to 5000/hour. Never hard-code the token.
- In tests, mock the HTTP layer entirely using `pytest-mock` + `responses` library — do not hit live GitHub in unit/integration tests.

**Warning signs:**
- `CatalogExplorer` raises `403` or `429` responses from GitHub.
- Test suite passes locally then fails in CI (different IP, shared rate limit).
- First prompt of the day works, subsequent prompts fail with network errors.

**Phase to address:**
CatalogExplorer phase (already built per PROJECT.md, but caching may not be implemented). Verify TTL caching and raw-URL usage before connecting the Agent layer.

---

### Pitfall 5: JSON Schema Validation Passes Malformed Payloads Due to Missing `additionalProperties: false`

**What goes wrong:**
The LLM is instructed to populate skill parameters according to `skill.json`. If the agent sends a parameter object with extra keys (hallucinated field names) and the JSON Schema validator does not have `additionalProperties: false` set, validation passes silently. The Deno skill receives unexpected extra parameters and either ignores them (best case) or behaves incorrectly (worst case).

**Why it happens:**
JSON Schema's default behavior allows additional properties. `additionalProperties: false` must be explicitly set. Anthropic Tool Definition Schema (which `skill.json` follows) does not mandate this flag, so skill authors often omit it.

**How to avoid:**
- In the Python validation layer (before Deno execution), always validate with `additionalProperties: false` injected programmatically if not present in the schema: `schema.setdefault("additionalProperties", False)`.
- Use `jsonschema` with `Draft7Validator` and check `format` validators explicitly — the default validator does not validate `format` keywords.
- Add a schema linting step to the skills catalog CI: any `skill.json` that lacks `additionalProperties: false` should fail a lint check.
- Log exactly which parameters were received vs. which were expected after each validation pass — this surfaces LLM hallucination patterns.

**Warning signs:**
- Skills execute but produce wrong output despite valid-looking inputs.
- Deno skill's TypeScript type checker catches an unexpected field that Python validation missed.
- LLM consistently adds extra keys like `"skill_name"` or `"confidence"` to the parameter payload.

**Phase to address:**
Parameter validation phase (between agent output and Deno invocation). Make the validator a standalone, tested module — not inline logic.

---

### Pitfall 6: Deno `--allow-net` Whitelist Bypassed via Redirect

**What goes wrong:**
A skill is granted `--allow-net=api.example.com`. If that API returns a `301/302` redirect to a different domain (e.g., a CDN or data processing service), Deno follows the redirect and the request to the redirected domain is permitted because Deno's `--allow-net` check happens at connection time before the redirect is resolved in some versions.

**Why it happens:**
HTTP redirect handling in `fetch()` is automatic by default (`redirect: "follow"`). The permission check validates the original hostname, not the final hostname after redirect resolution.

**How to avoid:**
- Skills should use `fetch(url, { redirect: "error" })` and handle redirects explicitly, following only to approved domains.
- The `--allow-net` flag should be as narrow as possible: `--allow-net=api.specific-endpoint.com` not `--allow-net=*.example.com`.
- Add a network egress policy document to the skills catalog: skill authors must declare exactly which domains are needed and why.
- In the Python execution layer, validate that the `allow_net` field in `skill.json` is a non-empty, specific domain list — reject skills with wildcards or empty allow-net.

**Warning signs:**
- Skill execution makes unexpected external calls visible in network logs.
- `skill.json` declares `allow_net: ["api.example.com"]` but Deno logs show connections to `cdn.fastly.com` or similar.

**Phase to address:**
Deno execution channel phase. Review Deno's current redirect behavior in the version being used (`deno --version`), as this behavior may change between releases.

---

### Pitfall 7: Asyncio Event Loop Blocking on Deno Subprocess stdout/stderr

**What goes wrong:**
`asyncio.create_subprocess_exec()` returns an async process, but if the Deno skill writes large output to stdout and the Python consumer does not read stdout concurrently, the subprocess blocks when the OS pipe buffer fills (~64KB on Linux, ~4KB on Windows). The process hangs indefinitely — it cannot finish until Python reads the pipe, but Python is waiting for the process to finish. This is a classic deadlock.

**Why it happens:**
Developers commonly write `await proc.wait()` after spawning the process without draining stdout/stderr first. The `communicate()` helper avoids this, but only if used correctly.

**How to avoid:**
- Always use `stdout, stderr = await proc.communicate(input=None)` instead of `await proc.wait()`. `communicate()` concurrently drains both pipes.
- If streaming output is needed (for progress), use `asyncio.gather()` with two coroutines: one reading stdout and one reading stderr, while also monitoring for timeout.
- Set a maximum output size limit: if Deno produces more than N bytes, terminate the process and return an error. Skills should not produce unbounded output.
- In the 5000ms timeout implementation, wrap `communicate()` in `asyncio.wait_for()`, not `proc.wait()`.

**Warning signs:**
- Integration tests with large Deno output hang indefinitely.
- Tests that pass with small outputs fail with larger outputs.
- CPU shows Python process at 0% (blocked on I/O) while Deno process is also at 0% (blocked on pipe write).

**Phase to address:**
Deno execution channel phase. The first working implementation must use `communicate()` — this is a correctness issue, not a performance optimization.

---

### Pitfall 8: Tag Extraction Brittleness Causes Complete Skill Routing Failure

**What goes wrong:**
The agent is instructed to extract 1-3 tags from the user prompt to query the catalog. If the prompt is ambiguous, domain-specific, or in a language/register the model does not handle well, tag extraction returns generic tags (`["task", "help", "do"]`) that match nothing in the catalog — or matches everything. The result is either a failed lookup or an overwhelmingly large candidate set injected into context.

**Why it happens:**
Tag extraction is a zero-shot classification task with an open vocabulary. The catalog's tag taxonomy and the model's intuitions about tagging may diverge, especially for niche skill domains.

**How to avoid:**
- Provide the model with the catalog's actual tag vocabulary as part of the extraction prompt: "Extract 1-3 tags from this list: [tag1, tag2, ...tag_n]". This converts open-vocabulary extraction to constrained classification.
- Cache the tag vocabulary from `catalog.yaml` alongside the catalog cache — rebuild when catalog refreshes.
- Add a fallback: if extracted tags return 0 skill matches, retry with a broader match (any single tag) before returning "no skill found."
- Log tag extraction attempts and catalog hit rates. A hit rate below 60% signals that the tag vocabulary needs review.

**Warning signs:**
- User prompts that clearly map to existing skills return "no skill found" errors.
- Catalog fetch always returns the full skill list (tags too generic).
- Tag extraction returns single-word tags like `"help"` or `"run"` that are not in the catalog taxonomy.

**Phase to address:**
Core agent routing phase. The tag vocabulary constraint should be in the first working prompt template.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode confidence threshold 0.72 | Faster to ship | Breaks silently after model updates; requires code change to retune | Never — put in config from day 1 |
| Hit live GitHub in all tests | No mock setup | Rate limit hits in CI; flaky tests on network errors; slow test suite | Never — mock HTTP in unit/integration tests |
| Use `proc.wait()` instead of `communicate()` | Simpler code | Pipe deadlock on outputs >64KB | Never — `communicate()` is the correct API |
| No TTL cache on catalog.yaml | Simpler fetch logic | Rate limit exhaustion in development; slow cold-start per prompt | Never — cache is table-stakes for this architecture |
| Inject all catalog skills as tools | No filtering logic needed | Context window exhaustion past ~15 skills | Never — tag filtering is the core differentiator |
| Skip `additionalProperties: false` | Faster schema authoring | Silent validation pass on hallucinated fields | Acceptable only in prototype stage, before first real skill |
| Use `gemini-2.0-flash` (unpinned) | Always uses latest | Routing behavior changes without notice after model update | Only if threshold is in config and logged for re-calibration |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| GitHub raw content | Using `api.github.com/repos/.../contents/...` for file fetch | Use `raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` — no auth needed, CDN-backed, no rate limit concern for content reads |
| Google ADK tool registration | Registering tools as plain `dict` objects | Use `google.genai.types.Tool` and `google.genai.types.FunctionDeclaration` — plain dicts are not validated and may silently fail |
| ADK confidence scoring | Assuming `grounding_metadata` confidence is a 0-1 probability | ADK confidence scores are model-specific logit derivatives; treat as ordinal ranking, not probability |
| Deno subprocess on Windows | Using `asyncio.create_subprocess_exec("deno", ...)` without PATH check | Deno on Windows may be installed in a non-PATH location; resolve binary path at startup and fail fast if not found |
| JSON Schema validation | Using `jsonschema.validate()` which raises on first error | Use `jsonschema.Draft7Validator(schema).iter_errors(instance)` to collect all errors and return a structured error list |
| Deno `--allow-net` | Passing user-controlled data into the flag value | The `allow_net` field in `skill.json` must be validated against an allowlist of approved domains before being passed to the Deno process invocation; never interpolate raw skill metadata into CLI flags |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Fetching `catalog.yaml` on every prompt with no cache | Each prompt adds 200-500ms network latency | TTL cache (5min) for catalog in CatalogExplorer | Immediately — first multi-prompt session |
| Lazy-loading all matching `skill.json` files sequentially | Tag match returns 8 skills, 8 sequential HTTP requests add 1-4s | Fetch matching skill.json files concurrently with `asyncio.gather()` | When catalog has >5 matching skills |
| Injecting verbose tool schemas | Token count balloons; model picks wrong tool due to noise | Keep `skill.json` descriptions concise; measure tokens before injection | Past ~15 injected skills |
| Deno cold start eating timeout budget | 5000ms timeout triggers before skill logic even runs | Measure Deno cold-start time (`deno run --v8-flags=--jitless`) on target machine; adjust timeout floor accordingly | On first invocation per session (Deno caches after) |
| No output size cap on Deno stdout | Large outputs fill pipe buffer and cause deadlock | Cap stdout read at 1MB; terminate process if exceeded | When skill returns large JSON payloads |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Trusting `skill.json` from an unreviewed catalog PR | Malicious skill author injects `--allow-run` or `--allow-write` via parameter value interpolation | Never interpolate skill parameters into Deno CLI flags; validate `allow_net` against approved domain allowlist; require manual review for new skills |
| Not validating `allow_net` from `skill.json` before passing to Deno | Skill claims it needs `api.example.com` but the value is `--allow-all` (flag injection) | Strip non-alphanumeric characters and validate domain format with regex before constructing the Deno command |
| Deno skill writes to stdout a payload that Python eval()s | Code execution in the Python host | Never `eval()` or `exec()` Deno output; always parse as JSON with `json.loads()` and catch `ValueError` |
| Exposing GitHub PAT in logs | Token appears in stack traces or debug logs | Use `SecretStr` (Pydantic) for the token; ensure log formatters redact it; never log the raw HTTP Authorization header |
| No process isolation between skills | One skill's environment leaks into another (env vars, temp files) | Each Deno invocation uses `--no-env` or an explicit env whitelist; use `tempfile.mkdtemp()` with cleanup for any temp files |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent routing decision (no feedback on why a skill was/wasn't found) | User types prompt, gets unhelpful "no skill found" with no diagnostic | Print the extracted tags and confidence score to stderr in verbose mode; always show which catalog path was taken |
| 5000ms timeout returns generic "execution failed" error | User doesn't know if it was a network issue, a skill bug, or a timeout | Return structured errors: `{"error": "timeout", "timeout_ms": 5000, "skill": "skill_name"}` |
| Catalog fetch failure silently falls back to no-skills mode | Agent behaves as a plain chatbot with no indication catalog is unavailable | Detect catalog fetch failure explicitly and warn the user; don't silently degrade |
| No progress indicator during skill execution | CLI appears frozen during 5000ms Deno execution | Print "Executing skill_name..." with a spinner using `rich` or simple dot-printing |

---

## "Looks Done But Isn't" Checklist

- [ ] **Deno timeout:** Verify with `asyncio.wait_for(proc.communicate(), timeout=5.0)` — not `proc.wait()`. Test with a skill that hangs indefinitely to confirm it terminates.
- [ ] **Process cleanup:** Test that after a Python SIGINT (Ctrl+C during skill execution), no Deno process remains (`ps aux | grep deno`).
- [ ] **Rate limit cache:** Confirm `catalog.yaml` is fetched once per session even if 10 prompts are entered. Check with network proxy or mock counter.
- [ ] **Token count guard:** Inject 30 skills from a large catalog and verify the API call does not return a 400 error. Measure token count before injection.
- [ ] **Schema validation:** Send a parameter payload with a hallucinated field and verify `additionalProperties: false` causes rejection before Deno is invoked.
- [ ] **`allow_net` injection:** Pass `api.example.com --allow-all` as the `allow_net` value in a test `skill.json` and verify Python strips the flag injection.
- [ ] **Tag vocabulary constraint:** Confirm tag extraction uses the catalog's actual tag list as a constrained vocabulary, not open generation.
- [ ] **Windows path:** Run `deno --version` at startup on Windows and fail fast with a clear error if Deno is not found.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Context window exhaustion from tool bloat | MEDIUM | Add token count guard; reduce description lengths in existing `skill.json` files; implement hard cap on injected tool count |
| Zombie Deno processes after deployment | LOW | Add process group kill on timeout; deploy atexit handler; restart Python process to clear accumulated zombies |
| Confidence threshold miscalibrated after model update | LOW | Adjust threshold in config; re-run calibration against logged decision history |
| GitHub rate limit hit in production | LOW | Add GitHub PAT to environment; switch to `raw.githubusercontent.com` if using API endpoint |
| Pipe deadlock in production | HIGH | Requires code change to replace `proc.wait()` with `communicate()`; any in-flight executions must be killed; rolling restart needed |
| Schema validation gap allows bad payload through | MEDIUM | Add `additionalProperties: false` enforcement in validator; audit existing skill execution logs for unexpected fields |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Tool schema bloat / context window exhaustion | Core agent loop (skill injection) | Inject 30-skill catalog; assert no 400 error; measure token count before call |
| Zombie Deno processes on timeout | Deno execution channel (first implementation) | Run skill with infinite loop; confirm process terminates within 6000ms; check for orphans |
| Pipe deadlock on large stdout | Deno execution channel (first implementation) | Run skill that outputs 1MB to stdout; confirm no hang |
| Confidence threshold drift | Core agent routing | Pin model version in config; add routing decision log from first working loop |
| GitHub rate limiting | CatalogExplorer review (before agent integration) | Run 70 sequential catalog fetches; confirm no 403; verify cache is hit after first fetch |
| Missing `additionalProperties: false` | Parameter validation module | Send hallucinated field; assert rejection before Deno invocation |
| `allow_net` flag injection | Deno execution channel (security hardening) | Unit test: `allow_net = "api.ok.com --allow-all"` must raise `ValueError` |
| Tag extraction brittleness | Core agent routing (first prompt template) | Test 10 prompts; verify extracted tags are always from catalog vocabulary |
| Deno cold start eating timeout | Deno execution channel | Measure cold-start on target machine; set timeout with 1500ms safety margin above measured cold-start |

---

## Sources

- Google AI ADK documentation (training-data knowledge, MEDIUM confidence) — tool registration patterns, context window behavior
- Deno official security model (training-data knowledge, MEDIUM confidence) — `--allow-net` semantics, subprocess permission isolation
- Python `asyncio` subprocess documentation (training-data knowledge, HIGH confidence) — `communicate()` vs `wait()` deadlock is a well-documented Python gotcha
- GitHub REST API documentation (training-data knowledge, HIGH confidence) — 60 req/hour unauthenticated, 5000 req/hour authenticated limits are stable
- JSON Schema specification (training-data knowledge, HIGH confidence) — `additionalProperties` default behavior
- Known Deno behavior: redirect and `--allow-net` (training-data knowledge, LOW confidence — verify against current Deno version in use)
- Process group kill pattern on POSIX (training-data knowledge, HIGH confidence) — well-established Unix pattern

**Note:** WebSearch and WebFetch were not available for this research session. All findings are based on training-data knowledge verified against multiple internal cross-checks. Claims marked HIGH confidence are well-established platform behaviors unlikely to have changed. Claims marked LOW confidence should be verified against current Deno changelog before implementation.

---
*Pitfalls research for: AIAgentsCrew — Distributed Skills Agentic Platform*
*Researched: 2026-05-16*
