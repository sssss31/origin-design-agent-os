"""Vercel Python Function entry point: the whole FastAPI app behind one function.
vercel.json rewrites every path here; SERVERLESS=true must be set in the project's env."""

from app.main import app  # noqa: F401  (Vercel looks for an ASGI `app`)
