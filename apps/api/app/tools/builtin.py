"""Built-in design tools (spec §13 primary tools). All return JSON-safe dicts; files produced
are returned under "files" as ProducedFile objects and become versioned artifacts."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.qc import QCFinding, Severity, build_report
from app.models.files import Artifact, ArtifactVersion, Asset, AssetVersion
from app.ports.runner import ProducedFile
from app.ports.tools import ToolSpec
from app.tools.context import ToolContext
from app.tools.registry import register

ASPECTS: dict[str, tuple[int, int]] = {
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "3:4": (1080, 1440),
    "2:3": (1000, 1500),
    "banner": (1600, 400),
    "a4": (2480, 3508),
}
SAFE_MARGIN_RATIO = 0.04


async def _load_bytes(ctx: ToolContext, args: dict[str, Any]) -> tuple[bytes, str, dict[str, Any]]:
    """Resolve `asset_id` or `artifact_id` to bytes within the tool's project."""
    async with ctx.session_factory() as session:
        if args.get("artifact_id"):
            art = await session.scalar(
                select(Artifact)
                .options(selectinload(Artifact.versions))
                .where(
                    Artifact.id == uuid.UUID(str(args["artifact_id"])), Artifact.project_id == ctx.project_id
                )
            )
            if art is None:
                raise ValueError("artifact not found in this project")
            v: ArtifactVersion | None = next(
                (x for x in art.versions if x.id == art.current_version_id), None
            )
            if v is None:
                raise ValueError("artifact has no version")
            data = await ctx.storage.get(v.storage_key)
            return (
                data,
                v.mime_type,
                {
                    "source_kind": "artifact",
                    "source_id": str(art.id),
                    "name": art.name,
                    "status": art.status,
                    "width": v.width,
                    "height": v.height,
                },
            )
        if args.get("asset_id"):
            asset = await session.scalar(
                select(Asset)
                .options(selectinload(Asset.versions))
                .where(Asset.id == uuid.UUID(str(args["asset_id"])), Asset.project_id == ctx.project_id)
            )
            if asset is None:
                raise ValueError("asset not found in this project")
            av: AssetVersion | None = next(
                (x for x in asset.versions if x.id == asset.current_version_id), None
            )
            if av is None:
                raise ValueError("asset has no version")
            data = await ctx.storage.get(av.storage_key)
            return (
                data,
                av.mime_type,
                {
                    "source_kind": "asset",
                    "source_id": str(asset.id),
                    "name": asset.name,
                    "kind": asset.kind,
                    "width": av.width,
                    "height": av.height,
                },
            )
    raise ValueError("provide asset_id or artifact_id")


def _open_image(data: bytes) -> Any:
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    im.load()
    return im


# ------------------------------------------------------------------ asset.list
async def asset_list(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    async with ctx.session_factory() as session:
        q = (
            select(Asset)
            .options(selectinload(Asset.versions))
            .where(Asset.project_id == ctx.project_id, Asset.status == "ready")
        )
        if args.get("kind"):
            q = q.where(Asset.kind == args["kind"])
        rows = (
            await session.scalars(q.order_by(Asset.created_at.desc()).limit(int(args.get("limit", 50))))
        ).all()
    items = []
    for a in rows:
        v = next((x for x in a.versions if x.id == a.current_version_id), None)
        items.append(
            {
                "asset_id": str(a.id),
                "name": a.name,
                "kind": a.kind,
                "mime_type": v.mime_type if v else None,
                "width": v.width if v else None,
                "height": v.height if v else None,
            }
        )
    return {"assets": items, "count": len(items)}


register(
    ToolSpec(
        slug="asset.list",
        display_name="List project assets",
        description="List uploaded assets (logos, images, PDFs, fonts) in the current project with ids to use in other tools.",
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    ),
    asset_list,
)


# ------------------------------------------------------------------ artifact.list
async def artifact_list(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    async with ctx.session_factory() as session:
        q = (
            select(Artifact)
            .options(selectinload(Artifact.versions))
            .where(Artifact.project_id == ctx.project_id)
        )
        if args.get("status"):
            q = q.where(Artifact.status == args["status"])
        rows = (
            await session.scalars(q.order_by(Artifact.updated_at.desc()).limit(int(args.get("limit", 50))))
        ).all()
    items = []
    for a in rows:
        v = next((x for x in a.versions if x.id == a.current_version_id), None)
        items.append(
            {
                "artifact_id": str(a.id),
                "name": a.name,
                "type": a.type,
                "status": a.status,
                "version": v.version_number if v else None,
                "width": v.width if v else None,
                "height": v.height if v else None,
                "parent_artifact_id": str(a.parent_artifact_id) if a.parent_artifact_id else None,
            }
        )
    return {"artifacts": items, "count": len(items)}


register(
    ToolSpec(
        slug="artifact.list",
        display_name="List artifacts",
        description="List generated artifacts in the project (master designs, resizes, exports) with status and ids.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    ),
    artifact_list,
)


# ------------------------------------------------------------------ image.inspect / file.inspect
async def image_inspect(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    data, mime, meta = await _load_bytes(ctx, args)
    out: dict[str, Any] = {
        "mime_type": mime,
        "size_bytes": len(data),
        "checksum_sha256": hashlib.sha256(data).hexdigest(),
        **meta,
    }
    if mime.startswith("image/") and mime != "image/svg+xml":
        im = _open_image(data)
        w, h = im.size
        dpi = im.info.get("dpi")
        colors = im.convert("RGB").resize((16, 16)).getcolors(256) or []
        dominant = sorted(colors, reverse=True)[:5]  # (count, (r, g, b))
        out.update(
            {
                "width": w,
                "height": h,
                "aspect_ratio": round(w / h, 4),
                "mode": im.mode,
                "format": im.format,
                "dpi": int(dpi[0]) if dpi else None,
                "dominant_colors": [f"#{c[1][0]:02x}{c[1][1]:02x}{c[1][2]:02x}" for c in dominant],
                "has_alpha": im.mode in ("RGBA", "LA"),
            }
        )
    return out


register(
    ToolSpec(
        slug="image.inspect",
        display_name="Inspect image",
        description="Read dimensions, aspect ratio, DPI, mode and dominant colors of an asset or artifact image.",
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string"}, "artifact_id": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    image_inspect,
)


async def file_inspect(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    data, mime, meta = await _load_bytes(ctx, args)
    out: dict[str, Any] = {
        "mime_type": mime,
        "size_bytes": len(data),
        "checksum_sha256": hashlib.sha256(data).hexdigest(),
        **meta,
    }
    if mime == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:20]:
            box = page.mediabox
            pages.append(
                {
                    "width_pt": float(box.width),
                    "height_pt": float(box.height),
                    "width_mm": round(float(box.width) * 25.4 / 72, 1),
                    "height_mm": round(float(box.height) * 25.4 / 72, 1),
                }
            )
        out.update({"pages": len(reader.pages), "page_sizes": pages})
    elif mime == "image/svg+xml":
        out.update(_svg_stats(data))
    return out


register(
    ToolSpec(
        slug="file.inspect",
        display_name="Inspect file",
        description="Read metadata of any asset/artifact: size, checksum, PDF page sizes, SVG structure.",
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string"}, "artifact_id": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    file_inspect,
)


def _svg_stats(data: bytes) -> dict[str, Any]:
    try:
        root = ET.fromstring(data)  # noqa: S314 - parsed for statistics only, never rendered
    except ET.ParseError as exc:
        return {"svg_valid": False, "svg_error": str(exc)[:200]}

    def local(tag: str) -> str:
        return tag.split("}", 1)[-1]

    counts: dict[str, int] = {}
    fonts: set[str] = set()
    for el in root.iter():
        name = local(el.tag)
        counts[name] = counts.get(name, 0) + 1
        ff = (
            el.get("font-family") or (el.get("style") or "").split("font-family:")[-1].split(";")[0]
            if "font-family" in (el.get("style") or "")
            else el.get("font-family")
        )
        if ff:
            fonts.add(ff.strip().strip("'\""))
    return {
        "svg_valid": True,
        "viewBox": root.get("viewBox"),
        "width": root.get("width"),
        "height": root.get("height"),
        "text_elements": counts.get("text", 0),
        "paths": counts.get("path", 0),
        "groups": counts.get("g", 0),
        "raster_images": counts.get("image", 0),
        "fonts": sorted(fonts),
        "editable": counts.get("text", 0) > 0 or counts.get("path", 0) > 0,
    }


# ------------------------------------------------------------------ svg.inspect
async def svg_inspect(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    data, mime, meta = await _load_bytes(ctx, args)
    if mime != "image/svg+xml":
        return {"svg_valid": False, "reason": f"not an SVG ({mime})", **meta}
    return {**_svg_stats(data), **meta}


register(
    ToolSpec(
        slug="svg.inspect",
        display_name="Inspect SVG structure",
        description="Report whether an SVG keeps editable text/vector layers, which fonts it references and whether raster images are embedded.",
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string"}, "artifact_id": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    svg_inspect,
)


# ------------------------------------------------------------------ image.resize
async def image_resize(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    from PIL import Image, ImageOps

    data, mime, meta = await _load_bytes(ctx, args)
    if not mime.startswith("image/") or mime == "image/svg+xml":
        raise ValueError("image.resize needs a raster image source")
    targets = args.get("target_sizes") or ["4:5"]
    mode = args.get("adaptation_mode", "adaptive")
    fmt = (args.get("output_format") or "png").lower()
    im = _open_image(data).convert("RGBA" if fmt == "png" else "RGB")
    files: list[ProducedFile] = []
    outputs = []
    for target in targets:
        if isinstance(target, str) and "x" in target and target.split("x")[0].isdigit():
            w, h = (int(p) for p in target.lower().split("x"))
            label = target
        else:
            label = str(target)
            if label not in ASPECTS:
                raise ValueError(f"unknown target size {label}; use one of {sorted(ASPECTS)} or WIDTHxHEIGHT")
            w, h = ASPECTS[label]
        if mode == "strict":
            out = ImageOps.pad(im, (w, h), color=(255, 255, 255, 0) if fmt == "png" else (255, 255, 255))
        else:
            # adaptive: cover the frame, crop centered; keeps proportions, never distorts
            out = ImageOps.fit(im, (w, h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        buf = io.BytesIO()
        pil_fmt = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}.get(fmt, "PNG")
        out.save(buf, format=pil_fmt, **({"quality": 92} if pil_fmt == "JPEG" else {}))
        ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[pil_fmt]
        base = str(meta.get("name", "design")).rsplit(".", 1)[0]
        filename = f"{base}-{label.replace(':', 'x')}.{ext}"
        files.append(
            ProducedFile(
                filename=filename,
                content=buf.getvalue(),
                mime_type=f"image/{'jpeg' if ext == 'jpg' else ext}",
                artifact_type="image",
                metadata={
                    "target": label,
                    "adaptation_mode": mode,
                    "source_id": meta.get("source_id"),
                    "source_kind": meta.get("source_kind"),
                    "parent_artifact_id": meta.get("source_id")
                    if meta.get("source_kind") == "artifact"
                    else None,
                    "artifact_name": filename,
                },
            )
        )
        outputs.append({"target": label, "width": w, "height": h, "filename": filename})
    return {"outputs": outputs, "source": meta, "files": files}


register(
    ToolSpec(
        slug="image.resize",
        display_name="Resize / adapt image",
        description="Adapt a raster design to target aspect ratios (4:5, 9:16, 16:9, 1:1, banner, a4 or WIDTHxHEIGHT). adaptive = cover+center crop, strict = letterbox pad. Produces one artifact per target.",
        input_schema={
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "artifact_id": {"type": "string"},
                "target_sizes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
                "adaptation_mode": {"type": "string", "enum": ["strict", "adaptive"]},
                "output_format": {"type": "string", "enum": ["png", "jpg", "webp"]},
            },
            "additionalProperties": False,
        },
        timeout_seconds=120,
    ),
    image_resize,
)


# ------------------------------------------------------------------ image.generate (provider-backed)
async def image_generate(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    api_key = ctx.provider_credentials.get("api_key")
    if not api_key:
        raise ValueError("image generation needs a provider with an API key (OpenAI)")
    base_url = (ctx.provider_credentials.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    size = args.get("size", "1024x1024")
    model = ctx.settings.get("image_model", "gpt-image-1")
    async with httpx.AsyncClient(timeout=120) as client:
        res = await client.post(
            f"{base_url}/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "prompt": args["prompt"], "size": size, "n": 1},
        )
    if res.status_code != 200:
        raise ValueError(f"image provider returned HTTP {res.status_code}")
    payload = res.json()
    item = (payload.get("data") or [{}])[0]
    if item.get("b64_json"):
        import base64

        content = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        async with httpx.AsyncClient(timeout=120) as client:
            content = (await client.get(item["url"])).content
    else:
        raise ValueError("image provider returned no image")
    name = args.get("name") or "generated"
    return {
        "width": int(size.split("x")[0]),
        "height": int(size.split("x")[1]),
        "model": model,
        "files": [
            ProducedFile(
                filename=f"{name}.png",
                content=content,
                mime_type="image/png",
                artifact_type="image",
                metadata={"prompt": args["prompt"][:500], "artifact_name": f"{name}.png"},
            )
        ],
    }


register(
    ToolSpec(
        slug="image.generate",
        display_name="Generate image",
        description="Generate a new raster design from a text prompt with the provider's image model. Produces one artifact.",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 3},
                "size": {"type": "string", "enum": ["1024x1024", "1024x1536", "1536x1024"]},
                "name": {"type": "string"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        timeout_seconds=180,
        requires_secret="provider",
    ),
    image_generate,
)


# ------------------------------------------------------------------ qc.checklist (deterministic)
async def qc_checklist(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    from PIL import ImageStat

    data, mime, meta = await _load_bytes(ctx, args)
    findings: list[QCFinding] = []
    checks = ["readable", "dimensions", "aspect_ratio", "safe_margin", "blank_or_flat", "file_size"]
    artifact_id = meta.get("source_id") if meta.get("source_kind") == "artifact" else None
    if not mime.startswith("image/") or mime == "image/svg+xml":
        findings.append(
            QCFinding(
                code="not_raster",
                severity=Severity.INFO,
                message=f"{mime} skipped raster checks",
                artifact_id=artifact_id,
            )
        )
        return build_report(
            findings, checks_run=["readable"], artifact_ids=[artifact_id] if artifact_id else []
        ).model_dump()
    try:
        im = _open_image(data)
    except Exception as exc:
        findings.append(
            QCFinding(
                code="unreadable",
                severity=Severity.BLOCKER,
                message=f"image cannot be decoded: {exc}",
                artifact_id=artifact_id,
            )
        )
        return build_report(
            findings, checks_run=["readable"], artifact_ids=[artifact_id] if artifact_id else []
        ).model_dump()
    w, h = im.size
    expected = args.get("expected_size")
    if expected:
        if isinstance(expected, str) and expected in ASPECTS:
            ew, eh = ASPECTS[expected]
        else:
            ew, eh = (int(p) for p in str(expected).lower().split("x"))
        if (w, h) != (ew, eh):
            findings.append(
                QCFinding(
                    code="dimension_mismatch",
                    severity=Severity.ERROR,
                    message=f"expected {ew}x{eh}px, got {w}x{h}px",
                    artifact_id=artifact_id,
                )
            )
    if args.get("expected_aspect") and args["expected_aspect"] in ASPECTS:
        aw, ah = ASPECTS[args["expected_aspect"]]
        if abs(w / h - aw / ah) > 0.01:
            findings.append(
                QCFinding(
                    code="aspect_mismatch",
                    severity=Severity.ERROR,
                    message=f"aspect {w}:{h} does not match {args['expected_aspect']}",
                    artifact_id=artifact_id,
                )
            )
    min_w, min_h = int(args.get("min_width", 600)), int(args.get("min_height", 600))
    if w < min_w or h < min_h:
        findings.append(
            QCFinding(
                code="too_small",
                severity=Severity.ERROR,
                message=f"{w}x{h}px is below the minimum {min_w}x{min_h}px",
                artifact_id=artifact_id,
            )
        )
    gray = im.convert("L")
    stat = ImageStat.Stat(gray)
    if stat.stddev[0] < 2:
        findings.append(
            QCFinding(
                code="blank_image",
                severity=Severity.BLOCKER,
                message="image is blank or a flat color",
                artifact_id=artifact_id,
            )
        )
    margin = max(1, int(min(w, h) * SAFE_MARGIN_RATIO))
    edges = [
        gray.crop((0, 0, w, margin)),
        gray.crop((0, h - margin, w, h)),
        gray.crop((0, 0, margin, h)),
        gray.crop((w - margin, 0, w, h)),
    ]
    busy_edges = sum(1 for e in edges if ImageStat.Stat(e).stddev[0] > 40)
    if busy_edges >= 3:
        findings.append(
            QCFinding(
                code="safe_margin_busy",
                severity=Severity.WARNING,
                message="high-contrast content touches 3+ edges; check safe margins for text/logo",
                artifact_id=artifact_id,
            )
        )
    if len(data) > int(args.get("max_bytes", 20 * 1024 * 1024)):
        findings.append(
            QCFinding(
                code="file_too_large",
                severity=Severity.ERROR,
                message=f"{len(data)} bytes exceeds the export limit",
                artifact_id=artifact_id,
            )
        )
    return build_report(
        findings, checks_run=checks, artifact_ids=[artifact_id] if artifact_id else []
    ).model_dump()


register(
    ToolSpec(
        slug="qc.checklist",
        display_name="Deterministic QC checklist",
        description="Run objective checks on an artifact: decodable, expected size/aspect, minimum size, blank detection, safe-margin crowding, file size. Returns a structured QC report with pass/fail.",
        input_schema={
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "asset_id": {"type": "string"},
                "expected_size": {"type": "string"},
                "expected_aspect": {"type": "string"},
                "min_width": {"type": "integer"},
                "min_height": {"type": "integer"},
                "max_bytes": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    ),
    qc_checklist,
)


# ------------------------------------------------------------------ export.package
async def export_package(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:

    data, mime, meta = await _load_bytes(ctx, args)
    fmt = (args.get("format") or "png").lower()
    files: list[ProducedFile] = []
    validation: dict[str, Any] = {"format": fmt}
    base = str(meta.get("name", "export")).rsplit(".", 1)[0]
    if mime.startswith("image/") and mime != "image/svg+xml":
        im = _open_image(data)
        w, h = im.size
        if args.get("expected_size"):
            ew, eh = (int(p) for p in str(args["expected_size"]).lower().split("x"))
            validation["dimensions_ok"] = (w, h) == (ew, eh)
            if not validation["dimensions_ok"]:
                raise ValueError(f"export refused: {w}x{h}px does not match expected {ew}x{eh}px")
        dpi = int(args.get("dpi", 72))
        buf = io.BytesIO()
        if fmt == "pdf":
            im.convert("RGB").save(buf, format="PDF", resolution=dpi)
            out_mime, ext, art_type = "application/pdf", "pdf", "pdf"
        elif fmt in ("jpg", "jpeg"):
            im.convert("RGB").save(buf, format="JPEG", quality=int(args.get("quality", 92)), dpi=(dpi, dpi))
            out_mime, ext, art_type = "image/jpeg", "jpg", "image"
        else:
            im.save(buf, format="PNG", dpi=(dpi, dpi))
            out_mime, ext, art_type = "image/png", "png", "image"
        content = buf.getvalue()
        max_bytes = int(args.get("max_bytes", 25 * 1024 * 1024))
        if len(content) > max_bytes:
            raise ValueError(f"export refused: {len(content)} bytes exceeds {max_bytes}")
        validation.update(
            {"width": w, "height": h, "dpi": dpi, "size_bytes": len(content), "mime_type": out_mime}
        )
        filename = f"{base}-final.{ext}"
        files.append(
            ProducedFile(
                filename=filename,
                content=content,
                mime_type=out_mime,
                artifact_type=art_type,
                metadata={
                    "export": validation,
                    "parent_artifact_id": meta.get("source_id")
                    if meta.get("source_kind") == "artifact"
                    else None,
                    "artifact_name": filename,
                    "final": True,
                },
            )
        )
    else:
        filename = f"{base}-final.{mime.split('/')[-1].replace('svg+xml', 'svg')}"
        validation.update({"size_bytes": len(data), "mime_type": mime, "passthrough": True})
        files.append(
            ProducedFile(
                filename=filename,
                content=data,
                mime_type=mime,
                artifact_type="svg"
                if mime == "image/svg+xml"
                else "pdf"
                if mime == "application/pdf"
                else "text",
                metadata={
                    "export": validation,
                    "parent_artifact_id": meta.get("source_id")
                    if meta.get("source_kind") == "artifact"
                    else None,
                    "artifact_name": filename,
                    "final": True,
                },
            )
        )
    return {"validation": validation, "filename": files[0].filename, "files": files}


register(
    ToolSpec(
        slug="export.package",
        display_name="Export final file",
        description="Produce the final deliverable (png/jpg/pdf) from an approved artifact, validating dimensions, DPI and file size. The result is stored as a final artifact.",
        input_schema={
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "asset_id": {"type": "string"},
                "format": {"type": "string", "enum": ["png", "jpg", "pdf"]},
                "dpi": {"type": "integer", "minimum": 72, "maximum": 600},
                "quality": {"type": "integer", "minimum": 50, "maximum": 100},
                "expected_size": {"type": "string"},
                "max_bytes": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        timeout_seconds=120,
    ),
    export_package,
)


# ------------------------------------------------------------------ copy.constraints (pure text helper)
async def copy_constraints(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    text = str(args.get("text", ""))
    max_chars = int(args.get("max_chars", 120))
    banned = [w for w in args.get("banned_words", []) if w.lower() in text.lower()]
    return {
        "length": len(text),
        "within_limit": len(text) <= max_chars,
        "banned_words_found": banned,
        "word_count": len(text.split()),
        "ok": len(text) <= max_chars and not banned,
    }


register(
    ToolSpec(
        slug="copy.constraints",
        display_name="Check copy constraints",
        description="Validate headline/body copy against character limits and banned words.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "max_chars": {"type": "integer"},
                "banned_words": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    ),
    copy_constraints,
)

_ = json  # keep import for future serializers
