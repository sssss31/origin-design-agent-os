# Deploying Origin

Everything runs on **Vercel** (free Hobby plan) except the database, which is a free **Supabase** Postgres. Two Vercel projects from the same repository:

| Vercel project | Root Directory | What it is |
| --- | --- | --- |
| `origin-design-agent-os` | `apps/web` | the chat UI (Next.js) |
| `origin-api` | `apps/api` | the API as one Python serverless function (`api/index.py` + `vercel.json`) |

The browser only talks to the web project; Next proxies `/api/v1/*` to the API project (`API_PROXY_TARGET`), so no CORS or public API URL is needed in the browser.

## 1. Database on Supabase (free, 2 minutes)

1. https://supabase.com → **New project** → choose a region near your users → set a **database password** and keep it.
2. Project → **Connect** (top bar) → **Transaction pooler** → copy the URI:
   `postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres` — replace `[YOUR-PASSWORD]`.
   The transaction pooler is the right choice for serverless (many short connections); the API disables server-side prepared statements in serverless mode so it is safe. The direct connection is IPv6-only and will not work from Vercel.

## 2. API on Vercel (free, 5 minutes)

1. https://vercel.com/new → **Import** `sssss31/origin-design-agent-os` again → project name `origin-api` → **Root Directory** `apps/web` → change to **`apps/api`** → Framework Preset **Other**.
2. **Environment Variables** (all for Production):

   | Key | Value |
   | --- | --- |
   | `SERVERLESS` | `true` |
   | `APP_ENV` | `production` |
   | `DATABASE_URL` | the Supabase URI from step 1 |
   | `JWT_SECRET` | any random string, 32+ characters |
   | `ENCRYPTION_KEY` | any random string, 32+ characters — **never change it later** (stored agent keys would become unreadable) |
   | `ALLOWED_ORIGINS` | `https://origin-design-agent-os.vercel.app` |
   | `FRONTEND_URL` | `https://origin-design-agent-os.vercel.app` |
   | `BOOTSTRAP_ADMIN_EMAIL` | `admin@origin.local` (or your email) |
   | `BOOTSTRAP_ADMIN_PASSWORD` | 16+ characters; creates the first admin only — change it after the first login |

   Generate the two secrets with `openssl rand -base64 48` (or any password generator).
3. **Deploy**. The first request runs the database migrations (under an advisory lock) and creates the admin. Check `https://origin-api-<hash>.vercel.app/healthz` → `{"status":"ok"}`.
4. Vercel → project `origin-api` → **Settings → Deployment Protection** → turn **Vercel Authentication off** for Production, otherwise the web project cannot reach the API.

How it works in serverless mode (`SERVERLESS=true`): there is no background worker — the chat's SSE request executes the agent call while streaming it (up to 300 s per message); the database engine uses no pool; uploads go to `/tmp` (ephemeral — set `STORAGE_BACKEND=s3` with Supabase Storage for durable files).

## 3. Web on Vercel

The repo is a monorepo, so Vercel must build `apps/web`, not the repo root (a root build produces nothing and every URL returns Vercel's `404 NOT_FOUND`).

1. Vercel → project **origin-design-agent-os** → **Settings → General → Root Directory** → `apps/web` → Save.
2. **Settings → Environment Variables** → add `API_PROXY_TARGET` = the API project's production URL, e.g. `https://origin-api-<hash>.vercel.app` (no trailing slash; from the `origin-api` project's **Domains**), for Production.
3. **Deployments → ⋯ → Redeploy** (or push a commit).

Framework preset stays "Next.js"; the build command is the default `next build`. `output: "standalone"` is disabled automatically on Vercel.

## 4. First login

Open the Vercel URL → sign in with `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` → account menu → **Admin console → Agents** → add your GPT agents' endpoints and API keys → Test.

## Alternative: API on Render (Docker)

`render.yaml` deploys the API as a long-running Docker service with Render Postgres (free database expires after 30 days; the free web service sleeps when idle). Use it if you prefer a classic server over serverless: New → Blueprint → this repo, then set `API_PROXY_TARGET` on the web project to the Render URL.

## Self-hosting with Docker instead

`infra/docker-compose.yml` runs Postgres, the API (`infra/deploy/api.Dockerfile`) and the web (`infra/deploy/web.Dockerfile`). Set the same environment variables as above; `API_PROXY_TARGET` for the web container is the API container's URL.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Vercel shows `404 NOT_FOUND` on every page | Root Directory is the repo root | Set Root Directory to `apps/web`, redeploy |
| Login says the web app is not connected to an API | `API_PROXY_TARGET` missing or wrong | Set it to the API project URL, redeploy the web |
| API URL opens a Vercel login page | Deployment Protection is on for the API project | Turn Vercel Authentication off for Production on `origin-api` |
| First request after a while is slow (5–10 s) | serverless cold start + migration check | normal on the free plan |
| Login works but chat replies fail with a CORS error | `ALLOWED_ORIGINS` does not include the web URL | Add the exact `https://…` origin, restart the API |
| "the stored credential cannot be read" | `ENCRYPTION_KEY` changed after keys were saved | Restore the old value, or re-enter the agent keys |
| API refuses to start with "Invalid production configuration" | A required variable is missing | The message lists what to set |
