from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, max_length: int = 60) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    text = _NON_ALNUM.sub("-", text.lower()).strip("-")
    return text[:max_length].strip("-") or "item"
