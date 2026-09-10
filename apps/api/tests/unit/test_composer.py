from app.services.composer import PLATFORM_RULES, ComposedSkill, CompositionInput, compose, render_variables


def test_composition_order_matches_spec() -> None:
    out = compose(
        CompositionInput(
            agent_instructions="You resize designs.",
            organization_rules="Never use Comic Sans.",
            skills=[
                ComposedSkill("Brand Lock", "brand-lock", 2, "Keep the logo.", priority=20),
                ComposedSkill(
                    "Resize Intelligence",
                    "resize",
                    1,
                    "Safe margin {{margin}}px.",
                    priority=10,
                    variables={"margin": 24},
                ),
            ],
            workspace_rules="Use brand blue.",
            project_rules=["Keep headline.", ""],
            brand_summary="- primary: #003366",
            context_summary="Poster set for autumn.",
            user_request="/resize to 4:5",
        )
    )
    assert out.sections == [
        "platform_rules",
        "organization_rules",
        "agent_instructions",
        "skill:resize@1",
        "skill:brand-lock@2",
        "brand_configuration",
        "workspace_rules",
        "project_rules",
        "context_summary",
        "user_request",
    ]
    assert out.text.startswith(PLATFORM_RULES)
    assert "Safe margin 24px." in out.text
    assert (
        out.text.index("Never use Comic Sans.")
        < out.text.index("You resize designs.")
        < out.text.index("Keep the logo.")
    )
    assert "- Keep headline." in out.text and "- \n" not in out.text


def test_composition_is_deterministic_and_skips_empty_sections() -> None:
    a = compose(CompositionInput(agent_instructions="x", organization_rules="  "))
    b = compose(CompositionInput(agent_instructions="x"))
    assert a.text == b.text and a.sections == ["platform_rules", "agent_instructions"]


def test_render_variables_leaves_unknown_placeholders_visible() -> None:
    assert render_variables("A {{ known }} and {{unknown}}", {"known": 1}) == "A 1 and {{unknown}}"
