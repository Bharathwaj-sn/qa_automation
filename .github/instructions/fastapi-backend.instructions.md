---
description: "Use when creating or modifying the FastAPI backend, REST APIs, services, integrations, authentication, long-running workflows, Angular static serving, SPA fallback, or backend deployment. Enforces FastAPI as the only application server."
applyTo: "backend/**/*.py"
---
# FastAPI Backend Architecture

## Runtime And Ownership

- Use FastAPI as the only production application server. The Angular frontend is a client-side SPA compiled to static files; Node.js is never a production runtime.
- Keep all server-side business logic, authentication, authorization, secret handling, orchestration, and privileged operations in the backend.
- Access Databricks, Azure DevOps, Genie, LLM providers, databases, and other protected systems only through FastAPI services or dedicated clients/adapters.
- Keep the application portable between Databricks Apps and Azure App Service. Do not couple business logic to either hosting platform.
- Do not implement frontend rendering, client-side state, browser interaction, or other UI concerns in backend services.

## Code Boundaries

- Preserve the existing organization under `backend/api`, `backend/services`, `backend/models`, `backend/repositories`, `backend/config`, and `backend/core` when it provides a reasonable owner.
- Keep route handlers thin: parse and validate requests, invoke a service or use case, and translate the result into the API response.
- Put business rules, orchestration, SQL and validation workflows, metadata processing, and test-case workflows in services rather than route handlers.
- Put external-system communication behind focused, replaceable, testable service, repository, client, or adapter abstractions. Introduce an `infrastructure` package only when the existing structure no longer provides a clear owner.
- Use FastAPI dependency injection where it clarifies lifecycle, configuration, authentication, or replaceable dependencies.
- Do not instantiate protected external integrations throughout route handlers.
- Keep Angular build and deployment mechanics separate from backend business logic.

## API Contract

- Expose Angular-facing REST APIs under `/api/*`; preserve the existing versioned `/api/v1` convention for current endpoints.
- Use routers for endpoint definitions and typed Pydantic models for request and response contracts.
- Validate all incoming data on the backend and treat frontend input as untrusted.
- Enforce authorization in FastAPI. Never rely on Angular validation, hidden controls, or client-side route guards for security.
- Return predictable JSON contracts and use the project's centralized exception handling for consistent errors.
- Do not expose internal Databricks, Azure DevOps, Genie, or LLM implementation details unless they are required by the frontend contract.
- Do not expose raw internal exceptions, stack traces, credentials, or sensitive configuration in production responses.
- Add or update focused API-contract and service tests when changing request models, responses, validation, errors, or orchestration behavior.

## Secrets And Configuration

- Never hard-code PATs, API keys, client secrets, Databricks credentials, LLM credentials, connection strings, or deployment-specific values in source code.
- Never return backend credentials or privileged tokens to Angular.
- Read deployment-specific settings from environment-backed configuration using the existing settings layer.
- Keep external integrations configurable and replaceable so tests do not require live protected services.

## Long-Running Workflows

- Do not implement Databricks SQL execution, agentic workflows, test execution, validation, or other potentially long-running work as large synchronous route handlers unless explicitly required.
- Prefer an operation contract in which Angular starts work and receives an operation identifier, then polls a status endpoint or uses another backend-supported asynchronous update mechanism.
- Represent queued, running, completed, failed, and cancelled states explicitly when the workflow supports them.
- Choose an execution mechanism with durability appropriate to the deployment; do not assume in-process background work survives restarts or scales across workers.
- Keep blocking SDK calls and CPU-heavy work from blocking the FastAPI event loop.

## Angular Static Serving

- Serve the compiled Angular application from `backend/static/` using FastAPI or Starlette static-file facilities.
- Ensure static assets such as JavaScript, CSS, images, and fonts resolve as files.
- Add one maintainable SPA fallback that returns `backend/static/index.html` for non-file frontend routes such as `/dashboard`, `/test-cases`, `/sql-queries`, `/execution`, and `/results`.
- Register API routes before the SPA fallback. Requests under `/api/*` must always resolve through FastAPI routing and must never return Angular's `index.html`.
- Do not convert missing static asset requests into `index.html`; return the appropriate missing-file response.
- Do not duplicate Angular route names as FastAPI endpoints.
- Do not require Node.js, an Angular development server, Express, or another frontend server to serve the production build.

## Deployment

- Keep the FastAPI application runnable with Uvicorn.
- Production launch configuration must bind to `0.0.0.0` and use the deployment-provided `PORT` when present; do not assume a fixed production port.
- Keep startup and static-path handling independent of the process working directory where practical.
- Preserve compatibility with both Databricks Apps and Azure App Service without introducing a Node.js runtime.

## Feature Placement

- For each feature, first classify work as API contract, service/business logic, or external integration.
- Put credentials, Databricks or Azure DevOps access, Genie or LLM calls, database access, SQL execution, metadata retrieval, and privileged operations behind FastAPI APIs.
- Expose only the contract Angular needs; keep internal orchestration and provider details private.
- For browser-only presentation, navigation, local state, or interaction, provide any required API and leave the UI behavior to Angular.

Maintain this direction of communication:

`Angular -> /api/* -> FastAPI -> Databricks / Azure DevOps / Genie / LLM providers`