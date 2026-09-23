"""Usage & cost: configurable pricing, per-call cost rows with attribution, breakdowns, budgets, test console."""

from __future__ import annotations

from app.domain.roles import Role
from app.models.workflows import ApiUsage
from sqlalchemy import select

from tests.api.test_runs import drain, make_agent, setup_org
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


async def test_pricing_cost_attribution_breakdown_and_budget(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    # pricing is admin-configured; prefix rows apply to model families
    res = await admin.put(
        f"{ADMIN}/usage/pricing",
        json={
            "provider_type": "echo",
            "model": "echo-*",
            "input_per_million": 2,
            "output_per_million": 8,
            "note": "test rate",
        },
    )
    assert res.status_code == 200, res.text
    pricing_rows = (await admin.get(f"{ADMIN}/usage/pricing")).json()
    assert pricing_rows[0]["model"] == "echo-*" and pricing_rows[0]["input_per_million"] == 2.0

    copy = await make_agent(admin, provider, name="Copy Agent", command="/copy")
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()
    created = (
        await admin.post(
            f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/copy write a tagline for autumn"}
        )
    ).json()
    await drain(app)
    run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
    assert run["status"] == "SUCCEEDED"

    async with app.state.session_factory() as session:
        usage = (await session.scalars(select(ApiUsage).order_by(ApiUsage.created_at))).all()
    assert len(usage) == 1
    u = usage[0]
    assert (
        u.agent_id is not None
        and u.provider_id is not None
        and u.user_id is not None
        and u.workspace_id is not None
    )
    assert u.command == "/copy" and u.status == "ok" and u.priced is True
    # echo counts words: cost = input * $2/M + output * $8/M (per-million rates above)
    expected = u.input_tokens * 2 / 1_000_000 + u.output_tokens * 8 / 1_000_000
    assert expected > 0 and abs(float(u.estimated_cost_usd) - expected) < 1e-6

    summary = (await admin.get(f"{ADMIN}/usage/summary")).json()
    assert (
        summary["currency"] == "INR"
        and summary["today"]["requests"] == 1
        and summary["month"]["cost_usd"] > 0
    )
    # cost_usd is rounded to 4 decimals for display; the converted figure comes from the exact value
    assert (
        abs(summary["today"]["cost_display"] - summary["today"]["cost_usd"] * summary["fx_usd_rate"]) <= 0.01
    )
    for by in ("agent", "model", "user", "workspace", "workflow", "provider"):
        rows = (await admin.get(f"{ADMIN}/usage/breakdown?by={by}")).json()
        assert rows and rows[0]["requests"] == 1, by
    assert (await admin.get(f"{ADMIN}/usage/breakdown?by=agent")).json()[0]["label"] == "Copy Agent"
    assert (await admin.get(f"{ADMIN}/usage/breakdown?by=workflow")).json()[0]["label"] == "/copy"
    calls = (await admin.get(f"{ADMIN}/usage/calls")).json()
    assert (
        calls[0]["agent"] == "Copy Agent"
        and calls[0]["cost_usd"] > 0
        and calls[0]["run_status"] == "SUCCEEDED"
    )
    overview = (await admin.get(f"{ADMIN}/integrations/overview")).json()
    assert (
        next(c for c in overview["providers"] if c["provider"]["id"] == provider["id"])[
            "estimated_cost_month_usd"
        ]
        > 0
    )

    # budget: a monthly budget below the spend blocks the next run with a sanitized 429-style failure
    await admin.patch(
        f"{ADMIN}/providers/{provider['id']}", json={"rate_limit_policy": {"monthly_budget_usd": 0.00000001}}
    )
    created = (
        await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/copy another one"})
    ).json()
    await drain(app)
    run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
    assert run["status"] == "FAILED" and run["error_json"]["code"] == "provider_budget_exhausted"
    test = await admin.post(f"{ADMIN}/agents/{copy['id']}/test", json={"input": "hi", "use_draft": False})
    assert test.status_code == 200 and test.json()["error_code"] == "provider_budget_exhausted"
    assert [s["status"] for s in test.json()["steps"]][-1] == "failed"
    # lifting the budget restores the test console with the full step checklist and usage
    await admin.patch(f"{ADMIN}/providers/{provider['id']}", json={"rate_limit_policy": {}})
    test = (
        await admin.post(
            f"{ADMIN}/agents/{copy['id']}/test",
            json={"input": "Create a premium healthcare poster", "use_draft": False},
        )
    ).json()
    labels = [s["label"] for s in test["steps"]]
    assert labels == [
        "Agent loaded",
        "Provider loaded",
        "Skills loaded",
        "Workspace context loaded",
        "Provider connected",
        "Agent executing",
        "Response received",
        "Usage recorded",
    ]
    assert (
        all(s["status"] == "done" for s in test["steps"])
        and test["usage"]["priced"]
        and test["usage"]["estimated_cost_usd"] > 0
    )
    calls = (await admin.get(f"{ADMIN}/usage/calls")).json()
    assert calls[0]["status"] == "test"
    # non-admins cannot read usage or pricing
    member = await make_user("m@example.com", role=Role.MEMBER)
    assert (await member.get(f"{ADMIN}/usage/summary")).status_code == 403
    # delete a pricing row
    assert (await admin.delete(f"{ADMIN}/usage/pricing/{pricing_rows[0]['id']}")).status_code == 204
