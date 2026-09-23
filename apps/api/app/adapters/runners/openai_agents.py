"""AgentRunner backed by the OpenAI Agents SDK (Responses API by default) — spec §12, §26.

Design:
- Bound tools become `FunctionTool`s whose invocation is delegated to our `invoke_tool`
  (permission checks, events and artifact persistence happen there, not in the SDK).
- Clarification is a built-in `ask_user` tool: when the model calls it, the question is
  recorded and the run outcome asks to pause; `resume_state` carries the SDK input list so
  the same run continues after the user's answer.
- Credentials come from `RuntimeAgent.provider_credentials` (resolved per run from the
  SecretStore) and are passed to a per-run model provider; they are never logged.
- Tracing sensitive-data capture follows OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA (off).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from app.ports.runner import EventEmitter, RunInput, RunOutcome, RuntimeAgent, ToolInvoker

_NAME = re.compile(r"[^a-zA-Z0-9_-]")

ASK_USER_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "One concise question that blocks execution"},
        "options": {"type": "array", "items": {"type": "string"}, "description": "Optional choices"},
    },
    "required": ["question"],
    "additionalProperties": False,
}


class OpenAIAgentsRunner:
    name = "openai_agents"

    def __init__(self, *, trace_include_sensitive_data: bool = False) -> None:
        self.trace_include_sensitive_data = trace_include_sensitive_data

    async def run(
        self, agent: RuntimeAgent, run_input: RunInput, *, invoke_tool: ToolInvoker, emit: EventEmitter
    ) -> RunOutcome:
        from agents import Agent, FunctionTool, ModelSettings, RunConfig, Runner
        from agents.models.openai_provider import OpenAIProvider

        api_key = agent.provider_credentials.get("api_key")
        if not api_key:
            raise RuntimeError("provider has no API key configured")
        base_url = agent.provider_credentials.get("base_url") or None

        holder: dict[str, Any] = {}
        tool_calls = 0

        def make_tool(slug: str, description: str, schema: dict[str, Any]) -> FunctionTool:
            async def on_invoke(_ctx: Any, args_json: str) -> str:
                nonlocal tool_calls
                tool_calls += 1
                try:
                    args = json.loads(args_json) if args_json else {}
                except json.JSONDecodeError:
                    args = {}
                result = await invoke_tool(slug, args if isinstance(args, dict) else {})
                return json.dumps(result, default=str)[:20000]

            return FunctionTool(
                name=_NAME.sub("_", slug)[:64],
                description=description or slug,
                params_json_schema=schema or {"type": "object", "properties": {}},
                on_invoke_tool=on_invoke,
                strict_json_schema=False,
            )

        async def ask_user(_ctx: Any, args_json: str) -> str:
            try:
                args = json.loads(args_json)
            except json.JSONDecodeError:
                args = {"question": args_json}
            holder["question"] = str(args.get("question", "")).strip() or "Could you clarify the request?"
            if args.get("options"):
                holder["schema"] = {"type": "string", "enum": [str(o) for o in args["options"]]}
            return "Question recorded. Stop now and wait for the user's answer; do not continue the task."

        tools: list[Any] = [make_tool(t.slug, t.description, t.input_schema) for t in agent.tools]
        if agent.can_ask_clarification and run_input.resume_state is None:
            tools.append(
                FunctionTool(
                    name="ask_user",
                    description="Ask the user one blocking clarification question and stop.",
                    params_json_schema=ASK_USER_SCHEMA,
                    on_invoke_tool=ask_user,
                    strict_json_schema=False,
                )
            )

        settings_kwargs: dict[str, Any] = {}
        for key in (
            "temperature",
            "top_p",
            "max_tokens",
            "tool_choice",
            "parallel_tool_calls",
            "truncation",
            "reasoning",
        ):
            if key in agent.model_settings:
                settings_kwargs[key] = agent.model_settings[key]
        sdk_agent = Agent(
            name=agent.name,
            instructions=agent.instructions,
            model=agent.model,
            tools=tools,
            model_settings=ModelSettings(**settings_kwargs) if settings_kwargs else ModelSettings(),
        )

        if run_input.resume_state and run_input.resume_state.get("input_list"):
            sdk_input: Any = list(run_input.resume_state["input_list"]) + [
                {
                    "role": "user",
                    "content": f"Answer to your question: {run_input.clarification_answer or ''}",
                }
            ]
        elif run_input.session_state and run_input.session_state.get("input_list"):
            # the agent's context window: prior turns with this agent in this conversation
            sdk_input = list(run_input.session_state["input_list"]) + [
                {"role": "user", "content": run_input.user_input}
            ]
        else:
            sdk_input = run_input.user_input
        config = RunConfig(
            model_provider=OpenAIProvider(api_key=api_key, base_url=base_url, use_responses=True),
            trace_include_sensitive_data=self.trace_include_sensitive_data,
            workflow_name=f"origin:{agent.slug}",
        )
        started = time.perf_counter()
        result = await Runner.run(sdk_agent, sdk_input, max_turns=max(1, agent.max_steps), run_config=config)
        duration_ms = int((time.perf_counter() - started) * 1000)

        usage = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "duration_ms": duration_ms,
            "tool_calls": tool_calls,
            "requests": 0,
        }
        for raw in getattr(result, "raw_responses", []) or []:
            u = getattr(raw, "usage", None)
            if u is not None:
                usage["requests"] += 1
                usage["input_tokens"] += int(getattr(u, "input_tokens", 0) or 0)
                usage["output_tokens"] += int(getattr(u, "output_tokens", 0) or 0)
                in_details = getattr(u, "input_tokens_details", None)
                out_details = getattr(u, "output_tokens_details", None)
                usage["cached_input_tokens"] += int(getattr(in_details, "cached_tokens", 0) or 0)
                usage["reasoning_tokens"] += int(getattr(out_details, "reasoning_tokens", 0) or 0)
        steps = len(getattr(result, "new_items", []) or [])

        if holder.get("question"):
            return RunOutcome(
                output_text="",
                requires_clarification=True,
                question=holder["question"],
                question_schema=holder.get("schema"),
                resume_state={"input_list": result.to_input_list()},
                usage=usage,
                steps=steps,
            )

        final = result.final_output
        structured: dict[str, Any] | None = None
        if isinstance(final, dict):
            structured = final
            output_text = json.dumps(final, ensure_ascii=False)
        elif hasattr(final, "model_dump"):
            structured = final.model_dump()
            output_text = json.dumps(structured, ensure_ascii=False)
        else:
            output_text = str(final or "")
            structured = _extract_json_block(output_text)
        return RunOutcome(
            output_text=output_text,
            structured_output=structured,
            usage=usage,
            steps=steps,
            session_state={"input_list": _jsonable(result.to_input_list())},
        )


def _jsonable(items: Any) -> list[dict[str, Any]]:
    """SDK input items may be pydantic models; store plain JSON so they survive the database."""
    out: list[dict[str, Any]] = []
    for it in items or []:
        if hasattr(it, "model_dump"):
            out.append(it.model_dump(mode="json", exclude_none=True))
        elif isinstance(it, dict):
            out.append(json.loads(json.dumps(it, default=str)))
    return out


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Agents are asked to end with a JSON block for structured outputs; parse it if present."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
