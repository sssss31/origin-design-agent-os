from app.domain.session_memory import budget_chars, count_turns, trim_input_list


def _turn(i: int, size: int = 10) -> list[dict]:
    return [
        {"role": "user", "content": f"u{i}" + "x" * size},
        {"type": "function_call", "call_id": f"c{i}", "name": "image.inspect", "arguments": "{}"},
        {"type": "function_call_output", "call_id": f"c{i}", "output": "ok"},
        {"role": "assistant", "content": f"a{i}"},
    ]


def test_trim_keeps_recent_whole_turns_and_never_orphans_tool_outputs() -> None:
    items = [it for i in range(5) for it in _turn(i)]
    kept = trim_input_list(items, max_chars=400)
    assert kept and kept[0]["role"] == "user"  # always starts at a user boundary
    assert count_turns(kept) < 5
    calls = {it["call_id"] for it in kept if it.get("type") == "function_call"}
    outputs = {it["call_id"] for it in kept if it.get("type") == "function_call_output"}
    assert calls == outputs
    assert kept[-1] == items[-1]


def test_trim_respects_turn_cap_and_empty() -> None:
    items = [it for i in range(10) for it in _turn(i, size=1)]
    assert count_turns(trim_input_list(items, max_chars=10**6, max_turns=3)) == 3
    assert trim_input_list([], max_chars=100) == []
    assert trim_input_list(items, max_chars=10**6) == items


def test_budget_scales_with_context_window() -> None:
    assert budget_chars(128_000) > budget_chars(32_000) > 0
    assert budget_chars(None) == budget_chars(128_000)
