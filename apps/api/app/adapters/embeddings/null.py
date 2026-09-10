class NullEmbeddings:
    """No semantic memory: retrieval falls back to recency + keyword search."""

    name = "none"
    dimensions = 0

    @property
    def available(self) -> bool:
        return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embeddings are disabled (EMBEDDINGS_BACKEND=none)")
