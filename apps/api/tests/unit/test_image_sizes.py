"""Requested ratio → output size the image tool accepts (execution brief §5)."""

from __future__ import annotations

import pytest
from app.domain.image_sizes import MAX_PIXELS, MIN_PIXELS, target_size_for


@pytest.mark.parametrize(
    ("text", "model", "expected", "ratio"),
    [
        ("resize 16:9", "gpt-image-2.5-sunburst", "1792x1008", "16:9"),
        ("Make the same design 4:5.", "gpt-image-2.5-sunburst", "1200x1504", "4:5"),
        ("make another square version", "gpt-image-2.5-sunburst", "1344x1344", "1:1"),
        ("instagram story please", "gpt-image-2.5-sunburst", "1008x1792", "9:16"),
        ("a 1080x1920 version", "gpt-image-2.5-sunburst", "1008x1792", "1080x1920"),
        ("resize 16:9", "gpt-image-1", "1536x1024", "16:9"),
        ("resize to 4:5", "gpt-image-1.5", "1024x1536", "4:5"),
        ("square", None, "1024x1024", "1:1"),
    ],
)
def test_target_size(text: str, model: str | None, expected: str, ratio: str) -> None:
    t = target_size_for(text, image_model=model)
    assert t is not None and t.size == expected and t.ratio == ratio
    if model and model.startswith("gpt-image-2"):
        assert t.width % 16 == 0 and t.height % 16 == 0 and MIN_PIXELS <= t.width * t.height <= MAX_PIXELS


def test_no_ratio_means_no_size() -> None:
    assert target_size_for("make the headline bigger", image_model="gpt-image-2.5-sunburst") is None
    assert target_size_for("use 12 colours and 3 fonts", image_model="gpt-image-2.5-sunburst") is None


def test_ratio_is_kept_within_tool_limits() -> None:
    t = target_size_for("make it 10:1", image_model="gpt-image-2.5-sunburst")
    assert t is not None and t.width / t.height <= 3.0 + 1e-6
