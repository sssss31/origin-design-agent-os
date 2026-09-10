# ADR 0001 — Monorepo location and stack

**Status:** accepted · **Date:** 2026-09-10

## Context
The spec mandates Next.js + TypeScript, FastAPI + Python, PostgreSQL, S3-compatible
storage. It was first scaffolded inside an unrelated host repository (PathSense) and then moved to its own repository.

## Decision
A self-contained monorepo (repository root) with `apps/api`,
`apps/web`, `packages/shared-schemas`, `infra/`, `docs/`. Python 3.14 with
`postgresql+psycopg` (psycopg 3 async). Next.js 16 App Router with Tailwind 4.

## Consequences
- psycopg 3 replaces asyncpg (no Python 3.14 wheels for asyncpg).
