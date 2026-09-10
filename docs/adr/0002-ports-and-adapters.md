# ADR 0002 — Ports and adapters for every external capability

**Status:** accepted · **Date:** 2026-09-10

## Context
Storage, secrets, queue, live events, LLM runtime, tools, embeddings and the workflow
scheduler will all change over the product's life (MinIO→R2, inline→Redis, OpenAI→other
providers, sequential→DAG). The dev machine has no Docker/Redis/MinIO.

## Decision
Each capability is a `typing.Protocol` in `app/ports/`. Services depend on ports only.
`app/adapters/registry.py` maps settings to implementations. Local, dependency-free
adapters are the development default; production adapters are selected by environment.

## Consequences
- Adding a backend never touches services or routers.
- Tests run without external services using the local adapters.
- Production profile validation refuses local adapters.
