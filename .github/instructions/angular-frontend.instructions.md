---
description: "Use when creating or modifying the Angular frontend, its build configuration, routing, state, API integration, SQL editor, or deployment integration. Enforces a static Angular SPA served by FastAPI."
applyTo: "frontend/**/*.{ts,html,scss,css,json}"
---
# Angular Frontend Architecture

## Runtime And Deployment Boundary

- Keep the frontend a client-side Angular SPA written in TypeScript.
- The production frontend must compile to static HTML, JavaScript, CSS, and assets with `ng build`.
- FastAPI is the only production application server. It serves the Angular build output from `backend/static/`.
- Node.js is a development and build-time dependency only. Never require Node.js in production.
- Do not introduce Angular SSR, Angular Universal, server rendering, Angular server routes, Next.js, Express, or another frontend server.
- Preserve static-file deployment when implementing every feature.
- Keep the frontend independent of the hosting platform so the same build can be served by Databricks Apps or Azure App Service.
- Configure FastAPI to return Angular's `index.html` for non-API client routes so SPA navigation and direct browser refresh work. Never let the SPA fallback intercept `/api/*`.

## Browser And Server Responsibilities

- Implement rendering, interaction, browser behavior, client-side routing, local reactive state, and presentation in Angular.
- Implement Databricks access, Azure DevOps access, Genie integration, LLM or agent orchestration, SQL execution, metadata retrieval, test-case generation and validation, background operations, authentication, authorization, and privileged operations in FastAPI.
- Before implementing a feature, decide which side owns it. Anything requiring credentials, protected services, database access, SQL execution, or server-side privileges belongs in FastAPI and must be exposed through an API.
- Never move backend responsibilities into Angular to simplify an implementation.
- Never use server-side filesystem, Node.js runtime, or server-side environment APIs from frontend code.

## Angular Implementation

- Use Angular Router for client-side navigation.
- Use Angular Signals (`signal`, `computed`, and `effect`) for local reactive state where appropriate.
- Use Angular services and dependency injection for API communication and shared frontend logic.
- Keep components focused on presentation and user interaction. Do not scatter HTTP or backend business communication across components.
- Keep server or persistent state distinct from local UI state.
- Prefer Angular built-in capabilities and small, focused dependencies.
- Do not add NgRx, another large state-management library, or a large UI framework unless explicitly requested.

## API And Security Boundary

- Communicate with FastAPI only through relative REST paths under `/api/*`. Do not hard-code hostnames or environment-specific backend URLs.
- Never call Databricks, Azure DevOps, Genie, LLM providers, or other protected external services directly from Angular.
- Never place PATs, API keys, client secrets, Databricks credentials, connection strings, or other secrets in frontend source, assets, build configuration, or Angular environment files.
- Frontend configuration may contain only values safe to expose publicly in a browser.
- Keep authentication and authorization decisions in FastAPI. Angular may present authentication UI and consume only browser-safe session information.
- For every API-driven view, implement appropriate loading, success, error, validation, execution-status, and empty states.
- Treat long-running backend work as asynchronous. Start work through FastAPI, expose progress or status through an API-supported mechanism, and keep the browser responsive while polling or receiving updates.

## SQL Editing

- Use CodeMirror 6 with SQL language support when a SQL editor is required.
- Do not introduce Monaco Editor unless explicitly requested.
- Syntax highlighting and lightweight editor feedback may run in Angular.
- Treat FastAPI and Databricks results as authoritative for SQL validation and execution.

## Build And Configuration

- Keep Angular source under `frontend/` and generate the production build into `backend/static/`.
- Ensure `ng build` remains sufficient to produce all frontend runtime files.
- Use an appropriate browser-safe configuration mechanism for environment-specific public values; never compile secrets into the application.
- Do not change the architecture to require a separate frontend runtime or deployment service unless explicitly requested.