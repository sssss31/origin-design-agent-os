"""Target aspect ratio → an output size the OpenAI image tool accepts (execution brief §5).

A resize request names a ratio ("16:9", "4:5", "square", "story", "1080x1920"). The image tool does not
take a ratio, so the closest size it supports is chosen here, server-side, instead of blindly sending
1024x1536 for a landscape request.

Rules (image generation guide):
- gpt-image-2 / 2.5: width and height multiples of 16, ratio between 1:3 and 3:1, 655,360–8,294,400 px.
- earlier gpt-image models: exactly 1024x1024, 1536x1024 or 1024x1536.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

_RATIO_RE = re.compile(r"(?<![\d.])(\d{1,2})\s*[:x×/]\s*(\d{1,2})(?!\d)(?!\.\d)", re.IGNORECASE)
_PIXELS_RE = re.compile(r"(?<!\d)(\d{3,4})\s*[x×]\s*(\d{3,4})(?!\d)", re.IGNORECASE)
_WORDS: dict[str, tuple[int, int]] = {
    "square": (1, 1),
    "landscape": (16, 9),
    "widescreen": (16, 9),
    "portrait": (4, 5),
    "story": (9, 16),
    "stories": (9, 16),
    "reel": (9, 16),
    "reels": (9, 16),
    "vertical": (9, 16),
    "banner": (3, 1),
    "cover": (16, 9),
}
FIXED_SIZES = {"square": (1024, 1024), "landscape": (1536, 1024), "portrait": (1024, 1536)}
MIN_PIXELS, MAX_PIXELS = 655_360, 8_294_400
MAX_EDGE = 3840
# flexible-size targets around 1.3–2 MP: sharp enough for social/print proofs, well inside the limits
_FLEX_TARGET_PIXELS = 1_800_000


@dataclass(frozen=True, slots=True)
class TargetSize:
    width: int
    height: int
    ratio: str  # "16:9"
    source: str  # "ratio" | "pixels" | "word"

    @property
    def size(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def slug(self) -> str:
        return self.ratio.replace(":", "x")

    @property
    def orientation(self) -> str:
        if self.width == self.height:
            return "square"
        return "landscape" if self.width > self.height else "portrait"


def parse_target(text: str) -> tuple[Fraction, str, str] | None:
    """The requested ratio (as a Fraction w/h), its label and where it came from, or None."""
    m = _PIXELS_RE.search(text)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        return Fraction(w, h), f"{w}x{h}", "pixels"
    m = _RATIO_RE.search(text)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if w and h:
            return Fraction(w, h), f"{w}:{h}", "ratio"
    lowered = text.lower()
    for word, (w, h) in _WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return Fraction(w, h), f"{w}:{h}", "word"
    return None


def _flexible(ratio: Fraction) -> tuple[int, int]:
    """Multiples of 16 around the target pixel budget, ratio clamped to 1:3…3:1."""
    r = float(ratio)
    r = max(1 / 3, min(3.0, r))
    # round the short edge to a multiple of 16, derive the long edge from it so the ratio never
    # rounds past the 1:3…3:1 limit
    if r >= 1:
        h = max(16, int(round((_FLEX_TARGET_PIXELS / r) ** 0.5 / 16)) * 16)
        w = max(16, int(round(h * r / 16)) * 16)
        while w / h > 3.0:
            w -= 16
    else:
        w = max(16, int(round((_FLEX_TARGET_PIXELS * r) ** 0.5 / 16)) * 16)
        h = max(16, int(round(w / r / 16)) * 16)
        while h / w > 3.0:
            h -= 16
    while w * h < MIN_PIXELS:
        w, h = w + 16, h + 16
    while w * h > MAX_PIXELS or w > MAX_EDGE or h > MAX_EDGE:
        w, h = w - 16, h - 16
    return w, h


def _fixed(ratio: Fraction) -> tuple[int, int]:
    r = float(ratio)
    if abs(r - 1) < 0.08:
        return FIXED_SIZES["square"]
    return FIXED_SIZES["landscape"] if r > 1 else FIXED_SIZES["portrait"]


def target_size_for(text: str, *, image_model: str | None) -> TargetSize | None:
    """Size for the image tool from the user's request, or None when no ratio is mentioned."""
    parsed = parse_target(text)
    if parsed is None:
        return None
    ratio, label, source = parsed
    flexible = bool(image_model) and str(image_model).startswith("gpt-image-2")
    w, h = _flexible(ratio) if flexible else _fixed(ratio)
    return TargetSize(width=w, height=h, ratio=label, source=source)
