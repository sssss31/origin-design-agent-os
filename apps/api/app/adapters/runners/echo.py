"""Deterministic runner for tests, admin 'Test' sandboxes without a provider, and demos.

Behaviour:
- If the input contains `?clarify`, it asks a clarification question (exercises pause/resume).
- If a `resume_state` is supplied, it completes using the clarification answer.
- Otherwise it echoes the request with the agent identity and the composed instruction length.
"""

from __future__ import annotations

from app.ports.runner import EventEmitter, RunInput, RunOutcome, RuntimeAgent, ToolInvoker


class EchoRunner:
    name = "echo"

    async def run(
        self,
        agent: RuntimeAgent,
        run_input: RunInput,
        *,
        invoke_tool: ToolInvoker,
        emit: EventEmitter,
    ) -> RunOutcome:
        if run_input.resume_state is not None:
            answer = run_input.clarification_answer or ""
            return RunOutcome(
                output_text=f"[{agent.slug} v{agent.version}] resumed with answer: {answer}",
                structured_output={"resumed": True, "answer": answer},
                steps=1,
            )
        if "?clarify" in run_input.user_input and agent.can_ask_clarification:
            return RunOutcome(
                output_text="",
                requires_clarification=True,
                question="Which target sizes do you need?",
                question_schema={
                    "type": "object",
                    "properties": {"sizes": {"type": "array", "items": {"type": "string"}}},
                },
                resume_state={"original_input": run_input.user_input},
                steps=1,
            )
        tool_notes: list[str] = []
        for tool in agent.tools:
            if f"!{tool.slug}" in run_input.user_input:
                result = await invoke_tool(tool.slug, {})
                tool_notes.append(f"{tool.slug}→{result.get('ok', True)}")
        return RunOutcome(
            output_text=(
                f"[{agent.slug} v{agent.version} · {agent.model}] {run_input.user_input.strip()}"
                + (f" (tools: {', '.join(tool_notes)})" if tool_notes else "")
            ),
            structured_output={"echo": run_input.user_input, "instruction_chars": len(agent.instructions)},
            defaults_used=["echo runner: no provider call was made"],
            steps=1,
        )
