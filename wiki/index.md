# Wiki Index

## Concepts

- [v1 deliverable](concepts/v1_deliverable.md) — The set of core features and functionalities required for the initial launch of 

- [Two-pass routing pattern](concepts/two-pass_routing_pattern.md) — The architectural approach where the agent first extracts tags and evaluates con

- [allow_net validation](concepts/allow_net_validation.md) — The architectural decision to rigorously validate network permissions (`--allow-

- [Tag vocabulary constraint](concepts/tag_vocabulary_constraint.md) — The architectural decision to constrain Gemini's tag generation to match known c

- [Confidence threshold stability](concepts/confidence_threshold_stability.md) — The architectural decision to manage the confidence threshold against potential 

- [GitHub rate limit mitigation](concepts/github_rate_limit_mitigation.md) — The architectural decision to prevent hitting GitHub API rate limits during cata

- [Tool schema bloat mitigation](concepts/tool_schema_bloat_mitigation.md) — The architectural decision to address the issue of too many injected tool schema

- [Zombie process prevention](concepts/zombie_process_prevention.md) — The architectural decision to ensure complete cleanup of Deno subprocesses, incl

- [Pipe deadlock mitigation](concepts/pipe_deadlock_mitigation.md) — The architectural decision to use `proc.communicate()` instead of `proc.wait()` 

- [Deno 2.x](concepts/deno_2x.md) — The TypeScript runtime and secure sandbox used for executing skills.

- [Pydantic 2.12+](concepts/pydantic_212.md) — A data validation library required by ADK for defining models and contracts.

- [google-adk](concepts/google-adk.md) — The Python library providing the agent framework components (LlmAgent, Runner, B

- [Deno subprocess sandbox](concepts/deno_subprocess_sandbox.md) — The isolated execution environment for TypeScript skills, leveraging Deno's deny

- [TypeScript skills](concepts/typescript_skills.md) — Dynamically discoverable and executable units of functionality, hosted in a GitH

- [Gemini agent](concepts/gemini_agent.md) — The core LLM agent, powered by Google's Gemini model, responsible for skill disc

- [GEMINI_API_KEY](concepts/gemini_api_key.md) — The API key required for authenticating with the Gemini API.

- [Use yaml.safe_load](concepts/use_yamlsafe_load.md) — The decision to exclusively use yaml.safe_load for parsing YAML files to prevent

- [Use httpx for HTTP client](concepts/use_httpx_for_http_client.md) — The choice to use httpx as the async HTTP client, leveraging its existing presen

- [Use asyncio.create_subprocess_exec](concepts/use_asynciocreate_subprocess_exec.md) — The decision to use asyncio's native subprocess creation for Deno invocation, en

- [Use Deno for skill execution](concepts/use_deno_for_skill_execution.md) — The choice to use Deno as the runtime for TypeScript skills due to its security 

- [Pin google-genai to 1.x](concepts/pin_google-genai_to_1x.md) — A critical decision to restrict google-genai to major version 1 due to incompati

- [pytest.asyncio_mode = auto](concepts/pytestasyncio_mode_auto.md) — A configuration setting for pytest-asyncio to automatically manage the asyncio e

- [Alternatives Considered](concepts/alternatives_considered.md) — A comparison of recommended technologies with other options, highlighting reason

- [Installation](concepts/installation.md) — Instructions for setting up the development environment and installing required 

- [Async Handling](concepts/async_handling.md) — Guidelines and patterns for managing asynchronous operations within the ADK and 

- [Deno Subprocess Invocation](concepts/deno_subprocess_invocation.md) — The verified pattern for executing TypeScript skills via Deno in a separate proc

- [FunctionDeclaration](concepts/functiondeclaration.md) — A type from google.genai used by ADK to declare a tool's capabilities, including

- [ADK Agent Patterns](concepts/adk_agent_patterns.md) — Recommended architectural patterns and code examples for using the google-adk li

- [Development Tools](concepts/development_tools.md) — Utilities and software used for local development, testing, and pre-execution va

- [Supporting Libraries](concepts/supporting_libraries.md) — Auxiliary libraries that provide specific functionalities, often as transitive d

- [Core Technologies](concepts/core_technologies.md) — The primary software components essential for the project's runtime and core fun

- [Recommended Stack](concepts/recommended_stack.md) — The proposed set of core technologies, supporting libraries, and development too

- [Stack Research](concepts/stack_research.md) — An overview of the technology investigation for the project, including domain, r

- [Schema Linting](concepts/schema_linting.md) — A development practice involving automated checks in CI to ensure `skill.json` f

- [additionalProperties: false](concepts/additionalproperties_false.md) — A JSON Schema keyword that, when set to `false`, prevents the validation from si

- [HTTP Mocking (Tests)](concepts/http_mocking_tests.md) — The practice of using libraries like `pytest-mock` and `responses` to simulate H

- [GitHub PAT (Personal Access Token)](concepts/github_pat_personal_access_token.md) — An optional authentication token that can be provided as an environment variable

- [In-memory Cache (Catalog)](concepts/in-memory_cache_catalog.md) — A caching mechanism for `catalog.yaml` and `skill.json` files to reduce repeated

- [Raw Content Endpoint (GitHub)](concepts/raw_content_endpoint_github.md) — The `raw.githubusercontent.com` endpoint, which is CDN-backed and has higher rat

- [Dry-run Mode](concepts/dry-run_mode.md) — A testing and calibration strategy where both cached and catalog-fetched paths a

- [Model Version Pinning](concepts/model_version_pinning.md) — The practice of explicitly specifying a fixed LLM model version (e.g., `gemini-2

- [Windows Job Object](concepts/windows_job_object.md) — A Windows-specific mechanism to group processes together, allowing for reliable 

- [Process Group Termination](concepts/process_group_termination.md) — A technique using `os.killpg` on POSIX systems to terminate a parent process and

- [GitHub API](concepts/github_api.md) — An external service used by the CatalogExplorer to fetch skill metadata and cont

- [JSON Schema](concepts/json_schema.md) — A standard for describing the structure and validation rules for JSON data, used

- [Gemini Context Window](concepts/gemini_context_window.md) — The fixed token budget of Gemini models that is shared among system prompts, too

- [Subprocess Sandboxing](concepts/subprocess_sandboxing.md) — The mechanism for running Deno skills in isolated subprocesses to prevent securi

- [LLM Tool Injection](concepts/llm_tool_injection.md) — The process of providing an LLM (specifically Gemini) with definitions of availa

- [Agentic platform](concepts/agentic_platform.md) — The target domain for the project, emphasizing distributed skill discovery and D

- [Confidence threshold](concepts/confidence_threshold.md) — A numeric value used in intent routing to determine whether to trust local knowl

- [git tags](concepts/git_tags.md) — A feature of Git used as a simple versioning mechanism for the skills catalog in

- [MCP](concepts/mcp.md) — A platform or environment mentioned as a potential execution channel for vector 

- [WebAssembly](concepts/webassembly.md) — A binary instruction format for a stack-based virtual machine, considered for an

- [Extism](concepts/extism.md) — A WebAssembly host runtime, considered for an alternative execution channel.

- [Qdrant](concepts/qdrant.md) — A vector database considered for future vector caching capabilities.

- [FastAPI](concepts/fastapi.md) — A Python web framework considered for future web UI development.

- [BASC](concepts/basc.md) — Business Alliance for Secure Commerce, a standard relevant for the immutable aud

- [ISO 27001](concepts/iso_27001.md) — An international standard for information security management, relevant for the 

- [REQ-07](concepts/req-07.md) — A specific requirement from the PRD concerning the immutable audit log.

- [REQ-08](concepts/req-08.md) — A specific requirement from the PRD concerning JSON Schema parameter validation.

- [PROJECT.md](concepts/projectmd.md) — A project overview document, serving as a high-confidence source for project int

- [Python's subprocess.run](concepts/pythons_subprocessrun.md) — A Python function used to run external processes, specifically for Deno sandbox 

- [jsonschema Python library](concepts/jsonschema_python_library.md) — A Python library used for validating JSON data against a JSON schema.

- [Deno sandboxing patterns](concepts/deno_sandboxing_patterns.md) — Design patterns for secure and isolated execution environments using Deno.

- [Anthropic Tool Schema](concepts/anthropic_tool_schema.md) — A reference for defining tool schemas, influencing the project's design.

- [Google ADK](concepts/google_adk.md) — Google's Agent Development Kit, serving as the framework for the Gemini agent.

- [Automated skill publishing pipeline](concepts/automated_skill_publishing_pipeline.md) — A decision to defer an automated CI/CD pipeline for publishing skills until v2, 

- [Skill versioning and rollback](concepts/skill_versioning_and_rollback.md) — A decision to defer formal skill versioning and rollback mechanisms until v2, us

- [Real-time streaming output](concepts/real-time_streaming_output.md) — A decision to defer real-time streaming of LLM responses until v2, prioritizing 

- [Multi-user / team support](concepts/multi-user_team_support.md) — A decision to defer features for multiple users, permissions, and billing until 

- [Vector cache auto-curation](concepts/vector_cache_auto-curation.md) — A decision to defer automatic caching of skill lookups using vector databases du

- [Web UI / FastAPI endpoint](concepts/web_ui_fastapi_endpoint.md) — A decision to defer development of a graphical web interface or FastAPI endpoint

- [Immutable audit log (full lifecycle)](concepts/immutable_audit_log_full_lifecycle.md) — A comprehensive, unalterable record of every step of an agent's request lifecycl

- [Execution channel routing by skill type](concepts/execution_channel_routing_by_skill_type.md) — The ability to automatically route different categories of skills (e.g., compute

- [SKILL.md cognitive guide](concepts/skillmd_cognitive_guide.md) — A human-readable Markdown document accompanying each skill to provide business r

- [Two-level catalog structure](concepts/two-level_catalog_structure.md) — An architectural choice using a lightweight root index (catalog.yaml) and separa

- [Tag-based semantic pre-filtering (in-memory)](concepts/tag-based_semantic_pre-filtering_in-memory.md) — A method to reduce LLM token consumption by programmatically filtering skills ba

- [Confidence-gated fallback routing](concepts/confidence-gated_fallback_routing.md) — Optimizes skill discovery by using cached or local knowledge when an LLM is high

- [Zero-redeploy skill addition](concepts/zero-redeploy_skill_addition.md) — Allows new skills to be made available to the agent simply by updating a catalog

- [End-to-end happy path (one skill)](concepts/end-to-end_happy_path_one_skill.md) — The foundational acceptance criterion for the initial version, ensuring a comple

- [CLI entry point](concepts/cli_entry_point.md) — The main command-line interface for interacting with and running the agent.

- [Structured error propagation](concepts/structured_error_propagation.md) — Handling and returning controlled, distinct error states for different types of 

- [Execution timeout enforcement](concepts/execution_timeout_enforcement.md) — A mechanism to terminate skill execution if it exceeds a predefined time limit.

- [Deno sandbox execution](concepts/deno_sandbox_execution.md) — The strategy for running TypeScript skills in an isolated and permission-control

- [JSON Schema parameter validation (pre-execution)](concepts/json_schema_parameter_validation_pre-execution.md) — Validation of LLM-generated skill parameters against a defined JSON schema befor

- [Dynamic tool injection](concepts/dynamic_tool_injection.md) — The critical missing piece and primary build target for v1, enabling runtime ski

- [Lazy-load skill definition (skill.json)](concepts/lazy-load_skill_definition_skilljson.md) — The mechanism to load the full contract of a skill (from its skill.json file) on

- [Catalog fetch and tag-based pre-filter](concepts/catalog_fetch_and_tag-based_pre-filter.md) — A method to efficiently identify relevant skills using a lightweight catalog ind

- [Natural-language intent routing](concepts/natural-language_intent_routing.md) — The ability of the agent to map user prompts in natural language to the appropri

- [Dynamic tool marketplace](concepts/dynamic_tool_marketplace.md) — A system where tools (skills) can be discovered and used on the fly.

- [Distributed skill discovery](concepts/distributed_skill_discovery.md) — The mechanism by which the agent finds and integrates new capabilities (skills) 

- [CLI-based agentic platform](concepts/cli-based_agentic_platform.md) — The primary domain of the project, focusing on an agent system controlled via a 

- [InputSchema](concepts/inputschema.md) — A Pydantic model defining the JSON schema for skill input parameters, used for v

- [CatalogSkill](concepts/catalogskill.md) — A Pydantic model representing an individual skill entry in the catalog.

- [CatalogManifest](concepts/catalogmanifest.md) — A Pydantic model representing the structure of the `catalog.yaml` file.

- [Async Subprocess with Hard Timeout](concepts/async_subprocess_with_hard_timeout.md) — An architectural pattern for skill execution using non-blocking asynchronous sub

- [FunctionTool as Execution Proxy](concepts/functiontool_as_execution_proxy.md) — An architectural pattern where SkillInjector wraps the Deno execution logic with

- [Two-Pass Agent Execution](concepts/two-pass_agent_execution.md) — An architectural pattern where the agent performs an initial LLM pass for confid

- [Deno runtime](concepts/deno_runtime.md) — The external JavaScript/TypeScript runtime used for executing sandboxed skills a

- [Gemini](concepts/gemini.md) — The Large Language Model used by the CoordinatingAgent for prompt processing, co

- [Subprocess sandboxing](concepts/subprocess_sandboxing.md) — Execution of skills in isolated Deno subprocesses with controlled permissions an

- [Lazy tool loading](concepts/lazy_tool_loading.md) — Skills (tools) are not loaded upfront but are discovered and injected into the a

- [Confidence-based routing](concepts/confidence-based_routing.md) — A core mechanism where the agent's confidence in directly executing a task deter

- [Dynamic agentic platform](concepts/dynamic_agentic_platform.md) — The overarching system design allowing agents to dynamically discover and execut

- [asyncio Subprocess with Timeout and Cleanup](concepts/asyncio_subprocess_with_timeout_and_cleanup.md) — An architectural pattern for managing Python `asyncio` subprocesses, including c

- [Module structure](concepts/module_structure.md) — The predefined file and directory layout for the `DenoRunner` and associated com

- [TypeScript skill files](concepts/typescript_skill_files.md) — External files containing business logic written in TypeScript, executed by the 

- [TC-03](concepts/tc-03.md) — An acceptance criterion related to the enforcement of execution timeouts.

- [Pydantic model inheritance](concepts/pydantic_model_inheritance.md) — An implementation detail concerning the specific hierarchy of Pydantic models fo

- [Zombie process detection](concepts/zombie_process_detection.md) — An area left to the discretion of the developer, concerning how to identify and 

- [asyncio vs subprocess threading](concepts/asyncio_vs_subprocess_threading.md) — An architectural decision point left to the discretion of the developer, regardi

- [Process group kill implementation](concepts/process_group_kill_implementation.md) — An area of implementation detail left to the discretion of the developer (Claude

- [pytest-asyncio](concepts/pytest-asyncio.md) — A pytest plugin that provides utilities for testing asynchronous Python code, us

- [pytest](concepts/pytest.md) — A popular Python testing framework used for testing the DenoRunner component.

- [Deno.stderr](concepts/denostderr.md) — Deno's standard error stream, exclusively reserved for error output from skill e

- [Deno.stdout](concepts/denostdout.md) — Deno's standard output stream, used by skills to return a single JSON result and

- [Deno.stdin](concepts/denostdin.md) — Deno's standard input stream, used by DenoRunner to pass JSON parameters to skil

- [Pydantic](concepts/pydantic.md) — A Python library used for data validation and settings management, adopted for m

- [Result type design](concepts/result_type_design.md) — A locked decision defining the structured Pydantic models used for all execution

- [Permission model](concepts/permission_model.md) — A locked decision specifying how Deno permissions, particularly `--allow-net` do

- [Skill I/O protocol](concepts/skill_io_protocol.md) — A locked decision outlining the communication contract between Python and Deno s

- [SkillInjector](concepts/skillinjector.md) — A component planned for Phase 2 that will act as the primary downstream consumer

- [Agent](concepts/agent.md) — A generic term referring to the intelligent component that performs discovery, i

- [Deno 2.6.7](concepts/deno_267.md) — A specific version of the Deno runtime against which network redirect behavior w

- [Deno redirect behavior](concepts/deno_redirect_behavior.md) — An area of low confidence regarding Deno's handling of network redirects, requir

- [Gemini structured JSON output](concepts/gemini_structured_json_output.md) — A specific JSON output design required for confidence score extraction in Phase 

- [Proc.communicate Preference Decision](concepts/proccommunicate_preference_decision.md) — The decision to always use 'proc.communicate()' over 'proc.wait()' in Phase 1 to

- [Windows Subprocess Cleanup Decision](concepts/windows_subprocess_cleanup_decision.md) — The decision to use 'taskkill /F /T /PID' for subprocess cleanup on Windows 11 i

- [Roadmap Build Order Decision](concepts/roadmap_build_order_decision.md) — The architecturally mandated sequence of phases for project delivery.

- [Core value](concepts/core_value.md) — The guiding principle of the project: dynamic skill discovery and execution from

- [LLM](concepts/llm.md) — Large Language Model, which supplies parameters to ADK FunctionTools.

- [Deno](concepts/deno.md) — A secure JavaScript/TypeScript runtime environment used to execute skill files w

- [TypeScript skill file](concepts/typescript_skill_file.md) — A skill implementation written in TypeScript, intended for execution by DenoRunn

- [Natural-language prompt](concepts/natural-language_prompt.md) — User input provided to the agent in an unstructured, human-readable format.

- [CLI Entry Point + End-to-End Validation](concepts/cli_entry_point_end-to-end_validation.md) — The fifth and final milestone, providing a user-facing command-line interface fo

- [Rate-limit protection](concepts/rate-limit_protection.md) — Mechanisms to avoid exceeding GitHub API request limits.

- [GITHUB_TOKEN](concepts/github_token.md) — An environment variable used for authenticated requests to GitHub, providing hig

- [TTL cache](concepts/ttl_cache.md) — A time-to-live cache used to store catalog data from GitHub to reduce network ca

- [CatalogExplorer Integration + Caching](concepts/catalogexplorer_integration_caching.md) — The fourth milestone, integrating with the GitHub-hosted skill catalog with in-m

- [JSONL logging](concepts/jsonl_logging.md) — The practice of logging routing decisions as JSON Line records.

- [Tag extraction](concepts/tag_extraction.md) — The process of identifying and extracting relevant tags from a user prompt.

- [Confidence-gated routing](concepts/confidence-gated_routing.md) — A routing strategy where the agent's confidence score dictates whether to answer

- [Coordinating Agent + Two-Pass Routing](concepts/coordinating_agent_two-pass_routing.md) — The third milestone, establishing the agent's routing logic based on confidence 

- [JSON Schema validation](concepts/json_schema_validation.md) — A mechanism for validating LLM-supplied parameters against a defined schema.

- [ADK FunctionTool](concepts/adk_functiontool.md) — Google ADK's mechanism for exposing Python callables to the LLM as tools, used b

- [SkillDefinition](concepts/skilldefinition.md) — A Pydantic model representing the definition of a skill, including its input sch

- [Skill Injection Bridge](concepts/skill_injection_bridge.md) — The second milestone, converting skill definitions into callable ADK FunctionToo

- [Phase 1: Deno Execution Channel](concepts/phase_1_deno_execution_channel.md) — The initial phase of a project focused on creating a secure and isolated executi

- [CatalogExplorer](concepts/catalogexplorer.md) — An already-existing system that AIAgentsCrew builds an agent layer upon.

- [Multi-skill DAG chaining](concepts/multi-skill_dag_chaining.md) — A decision to defer complex chaining of multiple skills into directed acyclic gr

- [Docker execution channel](concepts/docker_execution_channel.md) — A future execution channel for SRE-class skills (out of scope for v1).

- [MCP channel (Qdrant)](concepts/mcp_channel_qdrant.md) — A planned channel for Qdrant knowledge base integration (v2).

- [WebAssembly/Extism channel](concepts/webassemblyextism_channel.md) — A decision to defer adding an execution channel based on WebAssembly and Extism 

- [google-genai](concepts/google-genai.md) — The Python client library for interacting with the Gemini API.

- [GitHub](concepts/github.md) — The platform hosting the skill catalog and individual skill definitions.

- [Python 3.11](concepts/python_311.md) — The recommended runtime for the project, chosen for stability and asyncio.TaskGr

- [workflow](concepts/workflow.md) — A nested configuration object defining various workflow stages (research, plan_c

- [model_profile](concepts/model_profile.md) — A configuration parameter defining the model's performance profile, set to 'bala

- [commit_docs](concepts/commit_docs.md) — A boolean configuration parameter indicating whether documentation commits are e

- [parallelization](concepts/parallelization.md) — A boolean configuration parameter enabling or disabling parallel execution.

- [depth](concepts/depth.md) — A configuration parameter related to processing depth, set to 'standard'.

- [mode](concepts/mode.md) — A configuration parameter related to the operational mode, set to 'yolo'.

- [OBS-01](concepts/obs-01.md) — ISO 27001 / BASC-aligned immutable execution logs — full lifecycle capture from 

- [CHAN-01](concepts/chan-01.md) — WebAssembly/Extism channel for closed-compute skills (calculator) — microsecond 

- [ORCH-01](concepts/orch-01.md) — Multi-skill DAG chaining — single prompt triggers sequential execution of multip

- [CLI-02](concepts/cli-02.md) — End-to-end happy path verified with at least one real TypeScript skill from the 

- [CLI-01](concepts/cli-01.md) — User runs `python main.py` from terminal, enters a natural-language prompt, rece

- [RELI-04](concepts/reli-04.md) — Each routing decision logged to JSONL (prompt hash, extracted tags, confidence s

- [RELI-03](concepts/reli-03.md) — Confidence threshold is externalized to config (env var or config file) — re-cal

- [RELI-02](concepts/reli-02.md) — `GITHUB_TOKEN` env var supported for authenticated GitHub fetches (5000 req/hr v

- [RELI-01](concepts/reli-01.md) — `catalog.yaml` responses are TTL-cached in-memory (5-minute TTL) to prevent GitH

- [EXEC-03](concepts/exec-03.md) — CLI shows a progress indicator during the Deno execution window so the user know

- [EXEC-02](concepts/exec-02.md) — Execution errors return typed structured results (timeout / validation_failure /

- [EXEC-01](concepts/exec-01.md) — Matched skill executes via Deno subprocess with `--allow-net=<validated-domain>`

- [INJS-03](concepts/injs-03.md) — `SKILL.md` cognitive guide content is fetched from GitHub and injected into agen

- [INJS-02](concepts/injs-02.md) — LLM payload is validated against `skill.json` `input_schema` (JSON Schema) befor

- [INJS-01](concepts/injs-01.md) — SkillInjector converts `SkillDefinition` (from `skill.json`) to a live ADK `Func

- [DISC-04](concepts/disc-04.md) — Matched skill's `skill.json` is lazy-loaded from GitHub SSOT per request (alread

- [DISC-03](concepts/disc-03.md) — CatalogExplorer fetches `catalog.yaml` from GitHub SSOT and filters skills by ta

- [DISC-02](concepts/disc-02.md) — Pass 1 tag extraction constrains output to the catalog's actual tag vocabulary t

- [DISC-01](concepts/disc-01.md) — Coordinating Agent routes user prompt via confidence-gated fallback — if confide

- [Anthropic Tool Definition Schema](concepts/anthropic_tool_definition_schema.md) — The JSON Schema standard that `skill.json` files must conform to, defining the c

- [CLI](concepts/cli.md) — The primary user interface for AIAgentsCrew, allowing users to type natural-lang

- [Skills Catalog](concepts/skills_catalog.md) — A GitHub-hosted collection of skills, indexed by `catalog.yaml` and containing i

- [AIAgentsCrew](concepts/aiagentscrew.md) — The project name for a CLI-based agentic platform with dynamic skill discovery a

- [Oracle OKE](concepts/oracle_oke.md) — Oracle Container Engine for Kubernetes, targeted for future Docker channel deplo

- [Extism/Wasmtime](concepts/extismwasmtime.md) — Runtime environment used by the WebAssembly Sandbox for code execution.

- [gitlab_manager](concepts/gitlab_manager.md) — A skill for managing groups, users, and issues in GitLab.

- [qdrant_kb](concepts/qdrant_kb.md) — A skill for managing a vector knowledge base in Qdrant (mykb) for storage and se

- [calculator](concepts/calculator.md) — A skill for performing basic mathematical operations.

- [software_realiability_engineering](concepts/software_realiability_engineering.md) — A skill to evaluate the reliability of a software system.

- [especificar_testcase](concepts/especificar_testcase.md) — A skill for specifying test cases based on the SCRUM methodology.

- [especificar_user_story](concepts/especificar_user_story.md) — An example TypeScript skill mentioned for end-to-end validation.

- [evaluar-test-case](concepts/evaluar-test-case.md) — An example TypeScript skill mentioned for end-to-end validation.

- [Canal Docker (Evolución Futura)](concepts/canal_docker_evolución_futura.md) — A future execution channel prepared for isolated ephemeral container execution i

- [Canal MCP (Model Context Protocol)](concepts/canal_mcp_model_context_protocol.md) — A native bidirectional integration channel for corporate relational and vector d

- [Canal Deno Sandbox (I/O & APIs)](concepts/canal_deno_sandbox_io_apis.md) — A secure execution channel for TypeScript/JavaScript scripts with granular netwo

- [Canal WebAssembly Sandbox (Cómputo)](concepts/canal_webassembly_sandbox_cómputo.md) — An execution channel mandatory for closed dynamic code and mathematical utility 

- [motor de ejecución](concepts/motor_de_ejecución.md) — The execution engine that processes LLM-validated payloads through regulated cha

- [Grafo de Ejecución DAG](concepts/grafo_de_ejecución_dag.md) — A Directed Acyclic Graph representing the dynamic chaining of multi-skill sequen

- [cache indexada localmente](concepts/cache_indexada_localmente.md) — A local indexed cache used by the orchestrator for semantic matching of skills.

- [Catalog Explorer Agent](concepts/catalog_explorer_agent.md) — A sub-agent responsible for dynamically discovering and loading skills from the 

- [Coordinating Agent](concepts/coordinating_agent.md) — The central agent component responsible for responding to user prompts, extracti

- [SKILL.md](concepts/skillmd.md) — Markdown content describing a skill, fetched from GitHub and injected into the a

- [skill.json](concepts/skilljson.md) — A file defining an external skill, likely adhering to the Anthropic Tool Definit

- [skill folder](concepts/skill_folder.md) — A directory structure for each skill, containing its definition and documentatio

- [Sandboxing](concepts/sandboxing.md) — A mechanism for secure, lightweight, and audited runtime injection of skills.

- [catalog.yaml](concepts/catalogyaml.md) — A YAML configuration file for discovering and managing skills.

- [plataforma agéntica desacoplada](concepts/plataforma_agéntica_desacoplada.md) — The product solution: a decoupled and dynamically extensible agentic platform.

- [soluciones agénticas tradicionales](concepts/soluciones_agénticas_tradicionales.md) — Traditional agentic solutions that suffer from architectural rigidity, defining 

- [WebAssembly (Extism)](concepts/webassembly_extism.md) — A secure execution channel for dynamic code and mathematical computations using 

- [Deno Sandbox](concepts/deno_sandbox.md) — A secure execution environment for TypeScript skills, invoked as a subprocess wi

- [uv and Python 3.11 (FastAPI)](concepts/uv_and_python_311_fastapi.md) — Part of the core technological stack, likely for API development and runtime.

- [Anthropic Tool Standard](concepts/anthropic_tool_standard.md) — A JSON Schema standard used for defining skill contracts (skill.json).

- [GitHub (SSOT)](concepts/github_ssot.md) — GitHub acting as the Single Source of Truth for the distributed skill catalog.

- [Google AI ADK](concepts/google_ai_adk.md) — The core framework (`google-genai`) upon which the agentic platform is built, en

- [PRD](concepts/prd.md) — Project Requirements Document, serving as a high-confidence source for intended 

- [Sistema Agéntica General basado en Skills Distribuidos](concepts/sistema_agéntica_general_basado_en_skills_distribuidos.md) — The core product, a general agentic system based on distributed skills.

- [graph_weight](concepts/graph_weight.md) — The weighting factor for graph-based search in the overall search relevance calc

- [vector_weight](concepts/vector_weight.md) — The weighting factor for vector-based search in the overall search relevance cal

- [bm25_weight](concepts/bm25_weight.md) — The weighting factor for the BM25 search algorithm in the overall search relevan

- [search_weights](concepts/search_weights.md) — A group of settings that define the relative importance of different search algo

- [decay_days](concepts/decay_days.md) — The number of days over which confidence scores decay for information.

- [contradict_delta](concepts/contradict_delta.md) — The amount by which a confidence score decreases when information is contradicte

- [reinforce_delta](concepts/reinforce_delta.md) — The amount by which a confidence score increases when information is reinforced.

- [initial_confidence](concepts/initial_confidence.md) — The starting confidence score assigned to new information or statements.

- [confidence_settings](concepts/confidence_settings.md) — A group of settings that define how confidence scores are managed and updated wi

- [context_depth](concepts/context_depth.md) — The depth of context to consider when processing information for wiki generation

- [wiki_dir](concepts/wiki_dir.md) — The directory where the generated wiki documentation will be stored.

- [model](concepts/model.md) — The specific Large Language Model (LLM) to be used by llmwikidoc for generating 

- [llmwikidoc](concepts/llmwikidoc.md) — The main application or tool configured by this file, responsible for generating

## Modules

- [models/skill.py](entities/modelsskillpy.md) — The module containing shared Pydantic data contracts (CatalogManifest, CatalogSk

- [CLI](entities/cli.md) — The command-line interface entry point for the application.

- [types](entities/types.md) — A module from google.genai containing data structures like FunctionDeclaration.

- [json](entities/json.md) — Python's built-in library for working with JSON data.

- [jsonschema](entities/jsonschema.md) — A library for validating JSON data against a JSON schema.

- [pytest-asyncio](entities/pytest-asyncio.md) — A pytest plugin for writing asynchronous tests.

- [pytest](entities/pytest.md) — A popular test runner for Python applications.

- [anyio](entities/anyio.md) — A library for async primitives, providing an abstraction over asyncio and trio.

- [python-dotenv](entities/python-dotenv.md) — A library for loading environment variables from .env files.

- [pyyaml](entities/pyyaml.md) — A YAML parser library for handling YAML configuration files like catalog.yaml.

- [httpx](entities/httpx.md) — An asynchronous HTTP client for making network requests, e.g., fetching catalog 

- [pydantic](entities/pydantic.md) — A library for data validation, used for schema validation (e.g., skill.json inpu

- [google-genai](entities/google-genai.md) — The Python client library for interacting with Google's Gemini API, used interna

- [google-adk](entities/google-adk.md) — The Google Agent Development Kit, serving as the primary agent framework.

- [Python](entities/python.md) — The core programming language runtime for the project.

- [Deno](entities/deno.md) — A JavaScript/TypeScript runtime used for executing skills in a secure sandbox.

- [ADK](entities/adk.md) — Agent Development Kit, a framework that handles skill injection and execution wi

- [Coordinating Agent](entities/coordinating_agent.md) — The central component responsible for orchestrating the overall agentic workflow

- [asyncio](entities/asyncio.md) — Python's built-in library for writing concurrent code using the async/await synt

- [Pydantic models](entities/pydantic_models.md) — A group of models (CatalogManifest, CatalogSkill, SkillDefinition, InputSchema) 

- [main.py](entities/mainpy.md) — The CLI entry point, responsible for parsing user arguments, starting the event 

- [src/models/results.py](entities/srcmodelsresultspy.md) — The Python module containing the Pydantic result type models (`ExecutionSuccess`

- [tests/fixtures/skills/echo_skill.ts](entities/testsfixturesskillsecho_skillts.md) — A minimal TypeScript skill used as a test fixture, designed to read JSON from st

- [tests/execution/test_deno_runner.py](entities/testsexecutiontest_deno_runnerpy.md) — The test suite for the `DenoRunner` class.

- [src/execution/deno_runner.py](entities/srcexecutiondeno_runnerpy.md) — The Python module containing the `DenoRunner` class implementation.

- [PROJECT.md](entities/projectmd.md) — A documentation file containing project reference and key decisions.

- [SkillInjector](entities/skillinjector.md) — A new component responsible for converting SkillDefinition models into ADK Funct

- [CatalogExplorer](entities/catalogexplorer.md) — An existing component responsible for fetching the catalog index, filtering by t

## Classs

- [SkillTool](entities/skilltool.md) — A custom implementation of BaseTool that bridges external skill definitions (ski

- [BaseTool](entities/basetool.md) — An abstract base class for defining individual tools within google-adk.

- [SkillToolset](entities/skilltoolset.md) — A custom implementation of BaseToolset designed to provide dynamically discovere

- [ReadonlyContext](entities/readonlycontext.md) — A context object passed to toolset methods, providing read-only access to agent 

- [InMemorySessionService](entities/inmemorysessionservice.md) — A google-adk component for managing session state, suitable for single-instance 

- [BaseToolset](entities/basetoolset.md) — An ADK component that provides the API for dynamic tool injection, allowing tool

- [Runner](entities/runner.md) — A google-adk component responsible for managing the agent's execution flow and s

- [LlmAgent](entities/llmagent.md) — The canonical agent class from google-adk, used for orchestrating AI agent behav

- [ADK LlmAgent](entities/adk_llmagent.md) — The underlying Google ADK agent component that CoordinatingAgent wraps and deleg

- [ValidationFailure](entities/validationfailure.md) — A Pydantic model representing an error due to invalid input, specifically an inv

- [ExecutionError](entities/executionerror.md) — A Pydantic model representing a skill execution failure, including the exit code

- [TimeoutError](entities/timeouterror.md) — A Pydantic model representing a skill execution timeout, including the elapsed t

- [ExecutionSuccess](entities/executionsuccess.md) — A Pydantic model representing a successful skill execution result, containing pa

- [CLI shell](entities/cli_shell.md) — A command-line interface component enabling interactive prompt sessions, progres

- [CoordinatingAgent](entities/coordinatingagent.md) — A new orchestration component that implements the two-pass routing logic, manage

- [DenoRunner](entities/denorunner.md) — A new component that acts as an `asyncio.create_subprocess_exec` wrapper for exe

- [CatalogSkill](entities/catalogskill.md) — A Pydantic model representing a single skill's entry in the catalog index.

- [CatalogManifest](entities/catalogmanifest.md) — A Pydantic model representing the index structure of the skill catalog.

- [InputSchema](entities/inputschema.md) — A Pydantic model (`src/models/skill.py`) defining the expected input parameters 

- [SkillDefinition](entities/skilldefinition.md) — A Pydantic model representing the full definition and contract of a skill (from 

- [FunctionTool](entities/functiontool.md) — An ADK class instance representing a callable tool derived from a skill, injecte

## Functions

- [anyio.move_on_after](entities/anyiomove_on_after.md) — An anyio primitive for running a block of code with a timeout, allowing it to co

- [yaml.safe_load](entities/yamlsafe_load.md) — A pyyaml function for safely parsing a YAML string into a Python object.

- [load_dotenv](entities/load_dotenv.md) — A function from python-dotenv for loading environment variables from a .env file

- [json.loads](entities/jsonloads.md) — A JSON function for deserializing a JSON formatted string to a Python dict.

- [json.dumps](entities/jsondumps.md) — A JSON function for serializing a Python dict to a JSON formatted string.

- [proc.wait](entities/procwait.md) — An asynchronous method of an asyncio subprocess object that waits for the proces

- [proc.kill](entities/prockill.md) — A method of an asyncio subprocess object for terminating the process abruptly.

- [proc.communicate](entities/proccommunicate.md) — A method of an asyncio subprocess object for sending input and reading output/er

- [asyncio.wait_for](entities/asynciowait_for.md) — An asyncio function for running a coroutine with a timeout.

- [asyncio.create_subprocess_exec](entities/asynciocreate_subprocess_exec.md) — An asyncio function for creating a new subprocess and executing a command.

- [execute_via_deno](entities/execute_via_deno.md) — A custom asynchronous function responsible for invoking a TypeScript skill via a

- [run_async](entities/run_async.md) — An asynchronous method of BaseTool (and SkillTool) that executes the tool's logi

- [_get_declaration](entities/_get_declaration.md) — A protected method of SkillTool that generates the google.genai.types.FunctionDe

- [close](entities/close.md) — An asynchronous method of BaseToolset for performing cleanup when the toolset is

- [get_tools](entities/get_tools.md) — An asynchronous method of BaseToolset that returns a list of tools for the agent

- [google.genai.types.count_tokens()](entities/googlegenaitypescount_tokens.md) — A utility function to measure the token count of a payload, specifically for Gem

- [DenoRunner.execute()](entities/denorunnerexecute.md) — The primary method of DenoRunner that spawns a Deno subprocess, passes parameter

- [proc.wait()](entities/procwait.md) — A Python subprocess method for waiting for process termination, generally avoide

- [proc.communicate()](entities/proccommunicate.md) — A Python subprocess method recommended for interacting with process I/O to avoid

- [os.killpg](entities/oskillpg.md) — A Python function for killing a process group, noted as unavailable on Windows 1

- [taskkill /F /T /PID](entities/taskkill_f_t_pid.md) — A Windows command used for forcefully terminating processes by Process ID (PID).
