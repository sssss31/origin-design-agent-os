"""Seed the eight design agents, the reusable skills and the built-in tools (spec §13, §21).

Nothing here is special-cased at run time: after seeding, an admin can edit, re-bind,
re-version, disable or delete any of it from the console. Re-running the seed only adds
what is missing (matched by slug) and never overwrites edits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import AuthContext
from app.models.agents import Agent
from app.models.providers import AIProvider
from app.models.skills import Skill
from app.models.tools import Tool
from app.schemas.admin import (
    AgentCreate,
    AgentVersionInput,
    HandoffIn,
    ProviderCreate,
    ProviderModelsSet,
    PublishRequest,
    SkillBindingIn,
    SkillCreate,
    SkillVersionInput,
    ToolBindingIn,
    ToolCreate,
)
from app.services.agents import AgentService
from app.services.providers import ProviderService
from app.services.skills import SkillService
from app.services.tools import ToolService
from app.tools import registry as tool_registry

DEFAULT_OPENAI_MODELS = ["gpt-5", "gpt-5-mini", "gpt-4.1"]


@dataclass(slots=True)
class SkillSeed:
    slug: str
    name: str
    description: str
    instructions: str
    priority: int = 100
    variables_defaults: dict = field(default_factory=dict)
    tool_requirements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentSeed:
    slug: str
    name: str
    command: str
    description: str
    instructions: str
    handoff_description: str
    skills: list[str]
    tools: list[str]
    handoffs: list[tuple[str, str, bool]]  # (target slug, routing hint, failure route)
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    is_manager: bool = False
    max_steps: int = 20


SKILLS: list[SkillSeed] = [
    SkillSeed(
        "brand-asset-lock",
        "Brand & Asset Lock",
        "Preserve logos, key colors, hierarchy and approved assets.",
        "## Brand lock\n- Never move, recolor, distort, crop or replace the primary logo; keep its clear space.\n- Use only the approved palette and fonts from the brand configuration; do not introduce new colors.\n- Keep the visual hierarchy: headline > subhead > call to action; do not reorder.\n- Reuse approved assets by id; do not invent new imagery unless the request asks for it.",
        priority=10,
    ),
    SkillSeed(
        "design-adaptation",
        "Design Adaptation",
        "Rules for aspect-ratio changes without uncontrolled cropping or distortion.",
        "## Adaptation rules\n- Supported targets: 1:1, 4:5, 9:16, 16:9, 3:4, banner. Never stretch: use `adaptive` (cover + centered crop) or `strict` (letterbox) modes.\n- Keep all text and the logo inside a {{safe_margin_px}}px safe margin on every edge.\n- Minimum readable text height is {{min_text_px}}px at the target size; reflow instead of shrinking below it.\n- For vertical formats move secondary elements down, never overlap the headline.",
        priority=20,
        variables_defaults={"safe_margin_px": 48, "min_text_px": 24},
        tool_requirements=["image.resize", "image.inspect"],
    ),
    SkillSeed(
        "editable-svg-rules",
        "Editable SVG Rules",
        "Preserve vector/text structure and report unsupported reconstruction.",
        "## Editable output\n- Keep text as <text> elements with font-family declared; never outline text unless asked.\n- Group layers logically (background, imagery, copy, logo) with descriptive ids.\n- Report explicitly which parts could not be reconstructed as vectors and give a confidence score 0–1.",
        priority=20,
        tool_requirements=["svg.inspect", "file.inspect"],
    ),
    SkillSeed(
        "design-qc-checklist",
        "Design QC Checklist",
        "Content, typography, spacing, alignment, safe margins, distortion and brand checks.",
        '## QC checklist (report every item)\n1. Content: headline, subhead, CTA present and spelled correctly.\n2. Typography: brand fonts only; minimum sizes respected.\n3. Layout: alignment, spacing, safe margins, nothing clipped.\n4. Brand: logo untouched, palette respected.\n5. Technical: dimensions match target, no distortion, file readable.\nSeverity: blocker (cannot ship), error (must fix), warning (should fix), info.\nFinish with a JSON block: {"qc_report": {"passed": bool, "findings": [{"code", "severity", "message", "artifact_id"}], "checks_run": [...], "summary": "...", "artifact_ids": [...]}}',
        priority=10,
        tool_requirements=["qc.checklist", "image.inspect"],
    ),
    SkillSeed(
        "print-preflight",
        "Print Preflight",
        "Dimensions, bleed, DPI and file-format checks for print.",
        "## Print preflight\n- Print exports need {{dpi}} DPI, {{bleed_mm}}mm bleed and CMYK-safe colors; flag RGB-only artwork.\n- Validate final dimensions against the requested trim size before marking anything final.",
        priority=30,
        variables_defaults={"dpi": 300, "bleed_mm": 3},
        tool_requirements=["export.package", "file.inspect"],
    ),
    SkillSeed(
        "artifact-naming",
        "Artifact Naming",
        "Consistent names and version conventions for every output.",
        "## Naming\n- Name outputs `<project-slug>-<purpose>-<size>` (e.g. autumn-poster-4x5). Versions are managed by the platform; never add v2/final to names.\n- Describe every produced file in one line so it can be catalogued.",
        priority=90,
    ),
    SkillSeed(
        "clarification-policy",
        "Clarification Policy",
        "Ask only blocking questions; otherwise use safe defaults and state them.",
        "## Clarification policy\n- Ask at most one question, only when the answer changes the deliverable (target sizes, source file, copy language).\n- Otherwise choose the safest default (keep brand rules, keep current sizes, PNG output) and list every default you used at the end of your reply.",
        priority=5,
    ),
    SkillSeed(
        "manager-routing",
        "Manager Routing",
        "How to identify the specialist sequence and retry limits.",
        '## Routing\n- Split the request into specialist steps in execution order: master → resize → editable → qc → export; copy and asset steps come before master.\n- Only delegate to agents listed in your handoffs. After a QC failure the platform sends the artifact back once; do not loop yourself.\n- Reply with a short plan and end with a JSON block: {"plan": [{"command": "/resize", "instruction": "..."}, ...]}',
        priority=5,
    ),
]

RESIZE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_artifact": {"type": "string", "description": "required"},
        "target_sizes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "required or inferable from platform",
        },
        "preserve_text": {"type": "boolean", "default": True},
        "preserve_logo": {"type": "boolean", "default": True},
        "adaptation_mode": {"type": "string", "enum": ["strict", "adaptive"], "default": "adaptive"},
        "output_formats": {"type": "array", "items": {"type": "string"}, "default": ["png"]},
    },
    "required": ["source_artifact"],
}
QC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "qc_report": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "findings": {"type": "array"},
                "checks_run": {"type": "array"},
                "summary": {"type": "string"},
                "artifact_ids": {"type": "array"},
            },
            "required": ["passed", "findings"],
        }
    },
    "required": ["qc_report"],
}
PLAN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"command": {"type": "string"}, "instruction": {"type": "string"}},
                "required": ["command"],
            },
        }
    },
    "required": ["plan"],
}

AGENTS: list[AgentSeed] = [
    AgentSeed(
        "master-design",
        "Master Design Agent",
        "/master",
        "Create or revise the primary design artifact.",
        "You are the Master Design Agent. You create or revise the primary design (poster, key visual, master layout) from the brief, the brand configuration and the selected assets. Use image.generate for new imagery and asset.list/image.inspect to ground your work in approved assets. Describe the composition, then produce the file. End with a one-line description of each produced file.",
        "Delegate here to create a new master design or revise an existing one.",
        ["clarification-policy", "brand-asset-lock", "artifact-naming"],
        ["image.generate", "asset.list", "image.inspect", "artifact.list"],
        [("qc", "after producing a master, ask QC to check it", False)],
        input_schema={
            "type": "object",
            "properties": {
                "brief": {"type": "string"},
                "format": {"type": "string"},
                "reference_asset_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["brief"],
        },
    ),
    AgentSeed(
        "resize",
        "Resize Agent",
        "/resize",
        "Adapt the approved/master design to requested sizes while preserving hierarchy.",
        "You are the Resize Agent. Adapt the approved master artifact to the requested target sizes with image.resize, preserving text, logo and hierarchy. Inspect the source first with image.inspect. If target sizes are missing and cannot be inferred from the platform named in the request, ask one clarification question. Report each produced size.",
        "Delegate here for aspect-ratio or platform-size adaptations of an existing design.",
        ["clarification-policy", "brand-asset-lock", "design-adaptation", "artifact-naming"],
        ["image.resize", "image.inspect", "artifact.list", "asset.list"],
        [("qc", "check every resized artifact", False), ("export", "export after QC passes", False)],
        input_schema=RESIZE_INPUT_SCHEMA,
    ),
    AgentSeed(
        "editable",
        "Editable Agent",
        "/editable",
        "Convert/reconstruct output into editable SVG/Figma-oriented structure where possible.",
        "You are the Editable Agent. Reconstruct designs into editable, layered SVG-oriented structure. Use svg.inspect and file.inspect to assess the source, keep text as text and vectors as paths, and report a reconstruction confidence with what could not be preserved. Never promise pixel-perfect conversion for arbitrary raster input.",
        "Delegate here when the user needs an editable/vector version of a design.",
        ["clarification-policy", "editable-svg-rules", "artifact-naming"],
        ["svg.inspect", "file.inspect", "artifact.list", "asset.list"],
        [("qc", "check the editable output", False), ("export", "package the editable bundle", False)],
    ),
    AgentSeed(
        "qc",
        "QC Agent",
        "/qc",
        "Check content, layout, brand rules, dimensions, visual issues and export readiness.",
        "You are the QC Agent. Validate the artifacts named in the request (or the latest generated ones) with qc.checklist and image.inspect, then apply the QC checklist skill. Be objective: list findings with severity and the artifact id. Always finish with the qc_report JSON block; passed=false when any error/blocker exists.",
        "Delegate here to validate designs before approval or export.",
        [
            "clarification-policy",
            "design-qc-checklist",
            "brand-asset-lock",
            "editable-svg-rules",
            "print-preflight",
        ],
        ["qc.checklist", "image.inspect", "file.inspect", "artifact.list"],
        [
            ("resize", "send resized artifacts back when they fail", True),
            ("master-design", "send master designs back when they fail", True),
        ],
        output_schema=QC_OUTPUT_SCHEMA,
    ),
    AgentSeed(
        "copy",
        "Copy Agent",
        "/copy",
        "Generate or optimize copy while respecting content constraints.",
        "You are the Copy Agent. Write or optimize headline, subhead, body and CTA copy for the design, respecting the brand voice, character limits and banned words. Validate lengths with copy.constraints. Return the copy in a clear structure with alternatives.",
        "Delegate here for copywriting or copy optimization before design work.",
        ["clarification-policy", "brand-asset-lock"],
        ["copy.constraints"],
        [("master-design", "hand final copy to the master design step", False)],
    ),
    AgentSeed(
        "asset",
        "Asset Agent",
        "/asset",
        "Resolve, inspect, organize and prepare logos/images/fonts/references.",
        "You are the Asset Agent. Find and preflight assets with asset.list, image.inspect and file.inspect: confirm logos, fonts, references and their technical properties (dimensions, DPI, format). Report which assets are ready and what is missing for the requested deliverable.",
        "Delegate here to locate or preflight assets before design or resize work.",
        ["clarification-policy", "brand-asset-lock"],
        ["asset.list", "image.inspect", "file.inspect", "artifact.list"],
        [
            ("master-design", "assets are ready for design", False),
            ("resize", "assets are ready for adaptation", False),
        ],
    ),
    AgentSeed(
        "export",
        "Export Agent",
        "/export",
        "Produce final formats and validate dimensions/file properties.",
        "You are the Export Agent. Package approved artifacts into the requested final formats with export.package (png/jpg/pdf, DPI), validating dimensions, format and size. Only export artifacts that passed QC or are approved; otherwise say what must happen first. List every final file produced.",
        "Delegate here as the last step to produce deliverable files.",
        ["clarification-policy", "print-preflight", "artifact-naming"],
        ["export.package", "file.inspect", "image.inspect", "artifact.list"],
        [("qc", "re-check exports when the user asks", False)],
    ),
    AgentSeed(
        "manager",
        "Manager Agent",
        "/auto",
        "Interpret the request and invoke one or more specialists sequentially.",
        "You are the Manager Agent. Read the request and the context, decide which specialists are needed and in which order, and delegate. Do not do specialist work yourself. Reply with a short plan for the user and end with the JSON plan block.",
        "Automatic routing for requests without an explicit /command.",
        ["clarification-policy", "manager-routing"],
        ["artifact.list", "asset.list"],
        [
            ("asset", "asset lookup or preflight", False),
            ("copy", "copywriting", False),
            ("master-design", "new master design or revision", False),
            ("resize", "size/platform adaptations", False),
            ("editable", "editable/vector conversion", False),
            ("qc", "validation of any artifact", False),
            ("export", "final files", False),
        ],
        output_schema=PLAN_OUTPUT_SCHEMA,
        is_manager=True,
    ),
]


async def seed_builtin_tools(session: AsyncSession, ctx: AuthContext) -> int:
    """Create a `tools` row for every registered built-in tool that the organization lacks."""
    tool_registry.load_builtins()
    svc = ToolService(session, ctx)
    existing = {t.slug for t in await svc.list()}
    created = 0
    for spec in tool_registry.all_specs():
        if spec.slug in existing:
            continue
        await svc.create(
            ToolCreate(
                slug=spec.slug,
                display_name=spec.display_name,
                description=spec.description,
                executor_type="internal_function",
                input_schema=spec.input_schema,
                output_schema=spec.output_schema,
                config={},
                timeout_seconds=spec.timeout_seconds,
            ),
            is_builtin=True,
        )
        created += 1
    return created


async def ensure_provider(
    session: AsyncSession, ctx: AuthContext, provider_type: str, *, models: list[str] | None = None
) -> AIProvider:
    svc = ProviderService(session, ctx)
    for p in await svc.list():
        if p.type == provider_type:
            return p
    names = {"openai": "OpenAI Production", "echo": "Echo (offline test runner)"}
    provider = await svc.create(
        ProviderCreate(name=names.get(provider_type, provider_type), type=provider_type)
    )
    allow = models or (DEFAULT_OPENAI_MODELS if provider_type == "openai" else ["echo-1"])
    return await svc.set_models(
        provider.id, ProviderModelsSet(models=[{"model": m} for m in allow], default_model=allow[0])
    )


async def seed_skills(session: AsyncSession, ctx: AuthContext) -> dict[str, Skill]:
    svc = SkillService(session, ctx)
    existing = {s.slug: s for s in await svc.list()}
    out: dict[str, Skill] = {}
    for seed in SKILLS:
        if seed.slug in existing:
            out[seed.slug] = existing[seed.slug]
            continue
        skill = await svc.create(
            SkillCreate(
                name=seed.name,
                slug=seed.slug,
                description=seed.description,
                version=SkillVersionInput(
                    instructions=seed.instructions,
                    default_priority=seed.priority,
                    variables_defaults=seed.variables_defaults,
                    tool_requirements=seed.tool_requirements,
                ),
            )
        )
        out[seed.slug] = await svc.publish(skill.id, PublishRequest(change_note="seeded"))
    return out


async def seed_design_agents(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    provider_type: str = "openai",
    model: str | None = None,
    publish: bool = True,
) -> dict[str, int]:
    """Seed tools, skills, a provider and the eight agents. Returns counts of created entities."""
    stats = {
        "tools": await seed_builtin_tools(session, ctx),
        "skills": 0,
        "agents": 0,
        "published": 0,
        "skipped": 0,
    }
    provider = await ensure_provider(session, ctx, provider_type, models=[model] if model else None)
    chosen_model = (
        model or provider.default_model or (provider.models[0].model if provider.models else "gpt-5")
    )
    skills = await seed_skills(session, ctx)
    stats["skills"] = len(skills)
    tools = {
        t.slug: t
        for t in (
            await session.scalars(select(Tool).where(Tool.organization_id == ctx.require_organization()))
        ).all()
    }
    agent_svc = AgentService(session, ctx)
    all_agents = await agent_svc.list()
    existing = {a.slug: a for a in all_agents}
    taken_commands = {a.command: a for a in all_agents if a.status == "active"}
    created: dict[str, Agent] = {}
    stats["skipped"] = 0
    for seed in AGENTS:
        if seed.slug in existing:
            created[seed.slug] = existing[seed.slug]
            continue
        if seed.command in taken_commands:
            # an admin already runs their own agent on this command: keep theirs, wire handoffs to it
            created[seed.slug] = taken_commands[seed.command]
            stats["skipped"] += 1
            continue
        agent = await agent_svc.create(
            AgentCreate(
                name=seed.name,
                slug=seed.slug,
                command=seed.command,
                description=seed.description,
                is_manager=seed.is_manager,
                version=AgentVersionInput(
                    provider_id=provider.id,
                    model=chosen_model,
                    instructions=seed.instructions,
                    handoff_description=seed.handoff_description,
                    input_schema=seed.input_schema,
                    output_schema=seed.output_schema,
                    max_steps=seed.max_steps,
                ),
            )
        )
        for slug in seed.skills:
            if slug in skills:
                await agent_svc.attach_skill(agent.id, skills[slug].id, SkillBindingIn())
        for slug in seed.tools:
            if slug in tools:
                await agent_svc.attach_tool(agent.id, tools[slug].id, ToolBindingIn())
        created[seed.slug] = agent
        stats["agents"] += 1
    # handoffs after every agent exists
    for seed in AGENTS:
        agent = created[seed.slug]
        if seed.slug in existing or agent.slug != seed.slug:
            continue
        for target_slug, hint, failure in seed.handoffs:
            target = created.get(target_slug)
            if target is not None:
                await agent_svc.add_handoff(
                    agent.id, target.id, HandoffIn(routing_hint=hint, is_failure_route=failure)
                )
        if publish:
            await agent_svc.publish(agent.id, PublishRequest(change_note="seeded"))
            stats["published"] += 1
    return stats
