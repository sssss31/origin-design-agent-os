Database migrations live with the API code in `apps/api/alembic/` (Alembic).

- Apply: `cd apps/api && python -m alembic upgrade head` (the API container does this on start).
- Create: `python -m alembic revision --autogenerate -m "describe change"` then review the file.
- Never edit an applied migration; add a new one.
