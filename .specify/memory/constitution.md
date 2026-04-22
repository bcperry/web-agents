<!--
  Sync Impact Report
  ==================
  Version change: 2.0.2 → 2.1.0
  Bump rationale: MINOR — add mandatory Visual Verification
    Protocol section. All frontend/UI changes now require
    automated Playwright-based screenshot capture and agentic
    visual review before work is considered complete. This is
    a new enforceable section, not just a workflow note.

  Modified principles:
    - (none)

  Added sections:
    - Visual Verification Protocol (new section after
      Development Workflow)

  Removed sections:
    - (none)

  Modified workflow rules:
    - Development Workflow → Frontend changes: replaced vague
      "take a screenshot" note with reference to the new
      Visual Verification Protocol section

  Templates requiring updates:
    - .specify/templates/tasks-template.md — tasks that touch
      frontend files SHOULD include a visual verification task
    - .specify/templates/plan-template.md — ✅ no updates needed
    - .specify/templates/spec-template.md — ✅ no updates needed

  Follow-up TODOs:
    - (none)
-->

# Agent Framework Minimal SQL Constitution

## Core Principles

### I. Read-Only Data Access (NON-NEGOTIABLE)

All SQL operations executed by the agent MUST be read-only `SELECT`
statements. No data mutation (`INSERT`, `UPDATE`, `DELETE`) or schema
modification (`CREATE`, `ALTER`, `DROP`) is permitted under any
circumstance.

- Tool implementations MUST enforce this constraint at the query
  validation layer before execution.
- Truncated result sets MUST never be interpreted as absence of data;
  follow-on paged queries are required to confirm coverage.
- Query results MUST respect configured row and character limits
  (`MAX_QUERY_RESULT_ROWS`, `MAX_QUERY_RESULT_CHARS`).

**Rationale**: The agent operates against production Azure SQL databases
containing sensitive operational readiness data. Write access would
create an unacceptable risk of data corruption or loss.

### II. Single-File Agent Definitions

All agent profiles MUST be defined in a single `agents.yaml` file.
Each profile entry contains its system prompt and the list of tools
it uses. Tool descriptions and docstrings MUST live with the tool
implementations in Python code — not in YAML configuration.

- A single `agents.yaml` file defines every agent profile, each
  with its system prompt text and the names of tools it may invoke.
- Tool descriptions, usage rules, and documentation MUST be
  maintained as Python docstrings and `@tool` decorator metadata
  on the tool functions themselves.
- The Python source is the single source of truth for tool behavior
  and documentation. No YAML file may restate or override tool
  descriptions.
- Environment-specific prompt overrides (if needed) MUST be handled
  via overlay YAML or environment variables — not by duplicating
  agent entries.

**Rationale**: Keeping tool documentation next to the code that
implements it eliminates drift. A single YAML file for all agents
keeps configuration obvious and auditable without a sprawling
config tree.

### III. Security & Credential Hygiene

Credentials, connection strings, and tokens MUST never appear in
logs, tool output, API responses, or frontend bundles.

- Connection strings MUST be masked before any logging call.
- Production deployments MUST use Azure Managed Identity
  authentication — API keys are permitted only for local
  development.
- All Azure endpoints MUST target Azure Government cloud
  (`.azure.us` / `.usgovcloudapi.net` domains).
- User input MUST be bounded (`MAX_USER_INPUT_CHARS`) to prevent
  prompt injection and resource abuse.
- During local development with a separate frontend dev server,
  CORS MUST be restricted to `localhost` origins only. In
  production, CORS is not required because the frontend is
  served from the same origin.
- API endpoints MUST authenticate callers via Azure AD tokens or
  an equivalent mechanism — unauthenticated access to agent
  endpoints is prohibited outside local development.
- The React frontend MUST NOT embed secrets, API keys, or
  connection strings. All sensitive operations MUST be proxied
  through the backend.

**Rationale**: The system handles government-controlled data under
Azure Government compliance requirements. Credential leakage,
misrouted traffic, or unauthenticated API access would violate
those controls.

### IV. Evaluation-Driven Quality

Agent behavior changes MUST be validated through the evaluation
pipeline before deployment to shared environments.

- The `eval/` pipeline (trace generation → deterministic + AI-judge
  scoring → Foundry upload) MUST be executed for prompt, model, or
  parameter changes.
- Evaluation datasets MUST be maintained in `eval/datasets/` and
  versioned alongside prompt configs.
- Regression in evaluation scores MUST block promotion to staging
  or production overlays.

**Rationale**: AI agent output is non-deterministic. Systematic
evaluation is the only reliable way to detect quality regressions
before they reach users.

### V. Simplicity & Minimalism

Prefer the simplest implementation that satisfies requirements.
Avoid speculative abstractions, premature optimization, and
unnecessary indirection.

- Backend: `uv` is the ONLY permitted Python package manager.
  Never use `pip` directly.
- Frontend: `npm` is the permitted JavaScript/TypeScript package
  manager.
- New dependencies in either tier MUST be justified by a concrete,
  immediate need.
- Agent profiles (sql, search, hybrid) MUST reuse the shared
  `agent_factory` machinery — no per-profile forks of core logic.
- YAGNI: do not build features, configuration knobs, or
  abstractions for hypothetical future requirements.
- The two-tier split MUST NOT introduce unnecessary duplication;
  shared types or contracts between backend and frontend SHOULD
  be generated or derived from a single source (e.g., OpenAPI
  schema).

**Rationale**: A minimal codebase is easier to audit, test, and
maintain — especially critical for a security-sensitive government
application.

### VI. Infrastructure as Code

All Azure resources MUST be provisioned and managed via Terraform
configurations in `infra/`.

- Manual resource creation in the Azure portal is prohibited for
  any environment beyond personal experimentation.
- Terraform modules MUST be used for logical groupings
  (app-service, managed-identity, etc.).
- Environment-specific values MUST be supplied through
  `main.tfvars.json` — secrets MUST NOT be committed to the
  repository.

**Rationale**: Reproducible infrastructure is essential for disaster
recovery, environment parity, and auditability in a government
deployment context.

### VII. Two-Tier API-First Architecture

The application MUST be structured as a two-tier webapp: a Python
FastAPI backend and a React/TypeScript frontend. All agent
functionality is exposed exclusively through the backend API.
The built frontend is served as static files at the root of the
FastAPI application — a single deployment unit.

- The FastAPI backend is the sole gateway to LLM calls, database
  queries, search operations, and all server-side business logic.
  The frontend MUST NOT communicate with Azure services directly.
- The backend MUST expose a well-defined REST (or WebSocket) API.
  API contracts MUST be documented via OpenAPI (auto-generated by
  FastAPI).
- The React frontend is a single-page application (SPA) that
  consumes the backend API. It is responsible only for
  presentation and user interaction — no business logic.
- Backend and frontend MUST be independently buildable and
  testable, but they are deployed as a single unit: the
  production build step compiles the frontend into static assets
  that FastAPI serves from its root path.
- Frontend source lives in `frontend/` at the repository root.
  Backend source lives at the repository root (or `backend/`
  if restructured).
- The frontend build step (`npm run build`) MUST output compiled
  assets to a directory that the FastAPI application is configured
  to serve as static files (e.g., `frontend/dist/` or a path
  mounted via `StaticFiles`). The build output path MUST be
  consistent across local and CI/CD builds — no manual file
  copying is permitted.
- During local development, the frontend dev server proxies API
  requests to the FastAPI backend for a fast iteration cycle.

**Rationale**: Serving the frontend as static files from the
FastAPI app keeps deployment simple — one App Service, one
process, one URL. The clear source separation (frontend/ vs
backend Python) still allows independent development and testing
while avoiding the operational complexity of multi-service
hosting.

## Technology Stack & Constraints

- **Backend Language**: Python 3.12+
- **Backend Framework**: FastAPI
- **Frontend Language**: TypeScript
- **Frontend Framework**: React
- **Agent Runtime**: `agent-framework-core` +
  `agent-framework-azure-ai-search`
- **LLM Provider**: Azure OpenAI (Azure Government endpoints)
- **Database**: Azure SQL / Azure Synapse Analytics (read-only)
- **Search**: Azure AI Search (maintenance documentation RAG)
- **Infrastructure**: Terraform → Azure App Service (single
  deployment serving backend API + frontend static files) +
  Managed Identity
- **Backend Package Manager**: `uv` exclusively
- **Frontend Package Manager**: `npm`
- **Auth**: Azure AD / Managed Identity; token-based API auth
- **Agent Config**: Single `agents.yaml` (all profiles, system
  prompts + tool lists)
- **API Contract**: OpenAPI (auto-generated by FastAPI)

## Development Workflow

- **Backend changes**: Develop in `backend/`. Run
  `uv sync` for dependencies, `uv run pytest` for tests,
  `uv run uvicorn` to start the API server locally.
- **Frontend changes**: Develop in `frontend/`. Run
  `npm install` for dependencies, `npm test` for tests,
  `npm run dev` to start the dev server with API proxy.
  After making visual or layout changes, you MUST follow the
  Visual Verification Protocol defined below. Frontend work
  is NOT complete until automated visual verification passes.
- **Prompt changes**: Edit the agent profile in `agents.yaml`,
  run eval pipeline, review scores in Foundry, then promote.
- **Tool changes**: Update the Python tool function's docstring
  and implementation directly. Run backend tests to validate.
- **Dependency changes (backend)**: Add to `pyproject.toml`,
  install via `uv sync`. Never use `pip install`.
- **Dependency changes (frontend)**: Add to `package.json`,
  install via `npm install`.
- **Infrastructure changes**: Modify Terraform in `infra/`, run
  `terraform plan` for review, then `terraform apply` with
  approval.
- **Testing**: `agents.yaml` MUST pass schema validation tests.
  Backend tests (`pytest`) and frontend tests (`npm test`) MUST
  pass before merge. Evaluation pipeline MUST pass for prompt or
  model changes.
- **API contract**: When backend API endpoints change, regenerate
  or update the OpenAPI spec. Frontend API client code SHOULD be
  regenerated from the spec to prevent drift.

## Visual Verification Protocol (NON-NEGOTIABLE for UI Changes)

Any change that modifies frontend appearance — CSS, component
templates, layout, images, fonts, or theming — MUST complete
automated visual verification before the work is considered done.
DOM-based assertions alone are insufficient; they miss visual
regressions that only a rendered screenshot can reveal.

### Procedure

1. **Build the frontend**: Run `cd frontend && npm run build` and
   confirm zero errors.
2. **Start the server**: Launch the backend serving the built
   frontend assets (e.g., `AUTH_DISABLED=true uv run uvicorn
   main:app --host 0.0.0.0 --port 8000`).
3. **Capture screenshots via Playwright**: Using a headless
   Chromium instance (Playwright with system Chrome at
   `/usr/bin/google-chrome` or Playwright-managed Chromium),
   navigate through every affected screen and save PNG
   screenshots. At minimum, capture:
   - Disclaimer/warning overlay (scrolled to top and bottom)
   - Profile/mission selection screen
   - Empty chat view (with starter questions visible)
   - Chat view with at least one user message and one AI response
   - Any screen specifically affected by the current change
4. **Agentic visual review**: The agent MUST view each captured
   screenshot image (using image viewing tools) and evaluate:
   - Text is readable (no clipping, overflow, or truncation)
   - Colors and contrast match the design specification
   - Layout is correct (alignment, spacing, no overlaps)
   - No broken icons, empty boxes, or missing assets
   - Responsive elements render correctly at the tested viewport
5. **Fix and re-verify**: If any screenshot reveals a defect, the
   agent MUST fix the issue and repeat steps 1-4 until all
   screenshots pass visual review.
6. **Report**: After all screenshots pass, briefly summarize what
   was verified across each screen.

### Rules

- **No skipping**: "It probably looks fine" is never acceptable.
  Every UI change gets screenshots.
- **No emoji in rendered UI**: Emoji characters render
  inconsistently across headless browsers and OS environments.
  Use text-based indicators (e.g., `[W]`, `[SYS]`, `[OPR]`,
  `[TOOL]`, `[+IMG]`) instead of emoji for any UI element that
  must render reliably.
- **Viewport**: Default Playwright viewport is 1440×900. If the
  change involves responsive behavior, also capture at 768×1024
  and 360×640.
- **Screenshot storage**: Save screenshots to `screenshots/` at
  the repository root. This directory SHOULD be .gitignored.
- **Playwright dependency**: `playwright` is a dev dependency in
  `pyproject.toml`. Use system Chrome (`/usr/bin/google-chrome`)
  as the executable path to avoid Playwright browser downloads
  in CI.

**Rationale**: DOM assertions pass while the UI is visually broken
(centered text, broken emoji, clipped content, wrong colors). Only
real rendered screenshots catch these defects. Automating this via
Playwright removes human overhead while ensuring every UI change
is verified.

## Governance

This constitution supersedes all informal practices and ad-hoc
conventions. All pull requests and code reviews MUST verify
compliance with the principles defined above.

- **Amendment process**: Propose changes via PR to this file.
  Changes require review and explicit approval. Each amendment
  MUST include a Sync Impact Report (HTML comment at file top)
  and update the version line below.
- **Versioning**: Constitution version follows semantic versioning:
  - MAJOR: Principle removals or incompatible redefinitions.
  - MINOR: New principles, sections, or material expansions.
  - PATCH: Clarifications, wording, and non-semantic refinements.
- **Compliance review**: At minimum, review constitution alignment
  when adding new agent profiles, modifying tool access patterns,
  changing API contracts, or changing infrastructure modules.
- **Complexity justification**: Any deviation from Principle V
  (Simplicity) MUST be documented with concrete rationale in the
  relevant PR description.

**Version**: 2.1.0 | **Ratified**: 2026-03-20 | **Last Amended**: 2026-03-27
