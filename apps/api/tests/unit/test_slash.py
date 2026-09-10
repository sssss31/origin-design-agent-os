import pytest
from app.domain.slash import is_valid_command, normalize_command, parse_message


@pytest.mark.parametrize(
    ("text", "command", "body"),
    [
        ("/resize make it 4:5", "/resize", "make it 4:5"),
        ("  /QC  check both", "/qc", "check both"),
        ("/auto", "/auto", ""),
        ("/master\nA new poster", "/master", "A new poster"),
        ("make it bigger", None, "make it bigger"),
        ("/", None, "/"),
        ("/9lives", None, "/9lives"),
        ("path /resize", None, "path /resize"),
        ("/re-size_v2 x", "/re-size_v2", "x"),
    ],
)
def test_parse_message(text: str, command: str | None, body: str) -> None:
    parsed = parse_message(text)
    assert parsed.command == command
    assert parsed.body == body
    assert parsed.is_explicit is (command is not None)


def test_normalize_and_validate() -> None:
    assert normalize_command("Resize") == "/resize"
    assert is_valid_command("/resize")
    assert not is_valid_command("/bad command")
