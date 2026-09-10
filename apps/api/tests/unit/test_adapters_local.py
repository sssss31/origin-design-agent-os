import asyncio
import time
from contextlib import aclosing
from pathlib import Path

import pytest
from app.adapters.events.memory import InMemoryEventBus
from app.adapters.queue.inline import InlineQueue
from app.adapters.runners.echo import EchoRunner
from app.adapters.scheduler.dag import CyclicWorkflow, DagScheduler
from app.adapters.scheduler.sequential import SequentialScheduler
from app.adapters.storage.local_fs import LocalFSStorage
from app.adapters.tools_internal import InternalFunctionExecutor
from app.ports.queue import Job
from app.ports.runner import RunInput, RuntimeAgent, RuntimeTool
from app.ports.scheduler import EdgeSpec, NodeSpec
from app.ports.tools import ToolCall, ToolSpec


async def test_local_storage_roundtrip_and_signing(tmp_path: Path) -> None:
    storage = LocalFSStorage(tmp_path, signing_key="k", public_base_url="/api/v1")
    obj = await storage.put("ws/a/b.txt", b"hello", content_type="text/plain")
    assert obj.size == 5 and len(obj.checksum_sha256) == 64
    assert await storage.get("ws/a/b.txt") == b"hello"
    assert await storage.exists("ws/a/b.txt")
    url = await storage.presign_download("ws/a/b.txt", expires_in=60, filename="b.txt")
    assert url.startswith("/api/v1/files/ws/a/b.txt?expires=")
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("signature=")[1].split("&")[0]
    assert storage.verify("ws/a/b.txt", expires, signature)
    assert not storage.verify("ws/a/other.txt", expires, signature)
    assert not storage.verify(
        "ws/a/b.txt", int(time.time()) - 1, storage.sign("ws/a/b.txt", int(time.time()) - 1)
    )
    await storage.delete("ws/a/b.txt")
    assert not await storage.exists("ws/a/b.txt")


async def test_local_storage_refuses_path_traversal(tmp_path: Path) -> None:
    storage = LocalFSStorage(tmp_path, signing_key="k", public_base_url="/api/v1")
    for bad in ("../x", "/etc/passwd", "a/../../b", ""):
        with pytest.raises(ValueError):
            await storage.put(bad, b"x", content_type="text/plain")


async def test_inline_queue_runs_handler_and_dedupes() -> None:
    q = InlineQueue()
    seen: list[str] = []

    async def handler(job: Job) -> None:
        await asyncio.sleep(0.01)
        seen.append(job.payload["run_id"])

    q.register("run.execute", handler)
    await q.enqueue(Job(type="run.execute", payload={"run_id": "r1"}, idempotency_key="r1"))
    await q.enqueue(Job(type="run.execute", payload={"run_id": "r1"}, idempotency_key="r1"))
    await q.drain()
    assert seen == ["r1"]
    with pytest.raises(LookupError):
        await q.enqueue(Job(type="unknown"))


async def test_memory_event_bus_fanout() -> None:
    bus = InMemoryEventBus()
    received: list[dict] = []

    async def consume() -> None:
        async with aclosing(bus.subscribe("run-1")) as events:
            async for ev in events:
                received.append(ev)
                if ev["type"] == "run.completed":
                    break

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    assert bus.subscriber_count("run-1") == 1
    await bus.publish("run-1", {"type": "run.started"})
    await bus.publish("other", {"type": "ignored"})
    await bus.publish("run-1", {"type": "run.completed"})
    await asyncio.wait_for(task, 1)
    assert [e["type"] for e in received] == ["run.started", "run.completed"]
    assert bus.subscriber_count("run-1") == 0


def test_sequential_scheduler_preserves_order() -> None:
    nodes = [NodeSpec("a", "A", "agent"), NodeSpec("b", "B", "agent"), NodeSpec("c", "C", "agent")]
    plan = SequentialScheduler().plan(nodes, [EdgeSpec("c", "a")])
    assert [[n.id for n in batch] for batch in plan] == [["a"], ["b"], ["c"]]


def test_dag_scheduler_levels_and_cycles() -> None:
    nodes = [NodeSpec(i, i.upper(), "agent") for i in ("resize", "qc", "export", "copy")]
    edges = [EdgeSpec("resize", "qc"), EdgeSpec("copy", "qc"), EdgeSpec("qc", "export")]
    plan = DagScheduler().plan(nodes, edges)
    assert [[n.id for n in b] for b in plan] == [["resize", "copy"], ["qc"], ["export"]]
    with pytest.raises(CyclicWorkflow):
        DagScheduler().plan(nodes[:2], [EdgeSpec("resize", "qc"), EdgeSpec("qc", "resize")])


def _agent(**kw) -> RuntimeAgent:  # type: ignore[no-untyped-def]
    base = dict(
        slug="copy", name="Copy", version=3, instructions="x" * 10, model="echo-1", provider_type="echo"
    )
    base.update(kw)
    return RuntimeAgent(**base)  # type: ignore[arg-type]


async def _noop_tool(slug: str, args: dict) -> dict:
    return {"ok": True, "slug": slug}


async def _noop_emit(event_type: str, payload: dict) -> None:
    return None


async def test_echo_runner_echoes_and_clarifies() -> None:
    runner = EchoRunner()
    out = await runner.run(_agent(), RunInput(user_input="hello"), invoke_tool=_noop_tool, emit=_noop_emit)
    assert out.output_text.startswith("[copy v3 · echo-1] hello")
    assert not out.requires_clarification
    out = await runner.run(
        _agent(), RunInput(user_input="resize ?clarify"), invoke_tool=_noop_tool, emit=_noop_emit
    )
    assert out.requires_clarification and out.question and out.resume_state
    out = await runner.run(
        _agent(),
        RunInput(user_input="", resume_state=out.resume_state, clarification_answer="4:5"),
        invoke_tool=_noop_tool,
        emit=_noop_emit,
    )
    assert "resumed with answer: 4:5" in out.output_text


async def test_echo_runner_uses_allowed_tools_only() -> None:
    tool = RuntimeTool(slug="image.inspect", display_name="Inspect", description="", input_schema={})
    out = await EchoRunner().run(
        _agent(tools=[tool]),
        RunInput(user_input="!image.inspect !image.generate"),
        invoke_tool=_noop_tool,
        emit=_noop_emit,
    )
    assert (
        "image.inspect→True" in out.output_text and "image.generate" not in out.output_text.split("tools:")[1]
    )


async def test_internal_tool_executor_validates_and_redacts() -> None:
    async def fn(args: dict) -> dict:
        return {"width": args["width"] * 2, "api_key": "sk-secretsecretsecret"}

    spec = ToolSpec(
        slug="double",
        display_name="Double",
        description="",
        input_schema={"type": "object", "required": ["width"], "properties": {"width": {"type": "integer"}}},
        output_schema={"type": "object", "required": ["width"]},
    )
    executor = InternalFunctionExecutor({"double": fn})
    ok = await executor.execute(ToolCall(tool=spec, arguments={"width": 4}))
    assert ok.ok and ok.output["width"] == 8 and ok.output["api_key"] == "[REDACTED]"
    bad = await executor.execute(ToolCall(tool=spec, arguments={"width": "four"}))
    assert not bad.ok and bad.error_code == "invalid_input"
    missing = await executor.execute(ToolCall(tool=ToolSpec("nope", "", "", {}), arguments={}))
    assert missing.error_code == "tool_not_registered"
