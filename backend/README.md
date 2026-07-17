# EPM Wizard — backend

Local FastAPI service for EPM Wizard. See the repository root `README.md` for
full documentation. Runs entirely on the local machine; no hosted services.

- `app/schemas` — canonical Pydantic models (single source of truth)
- `app/connector` — the one authoritative EPM connector boundary
- `app/artifacts` — deterministic artifact engine (resolve, validate, render, package)
- `app/context` — context engine, retrieval, `.epwcontext` packages
- `app/ai` — provider-independent AI layer (deterministic Mock + external adapters)
- `app/agent` — intent routing, tools, skills, streaming orchestrator
- `app/architecture` — Cube Architecture & Dimensionality Visualizer services
- `app/api` — FastAPI routes (incl. SSE chat streaming)
