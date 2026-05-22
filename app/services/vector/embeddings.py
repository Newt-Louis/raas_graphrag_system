from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import Protocol


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class TextEmbeddingService(Protocol):
    model_name: str
    dimensions: int

    def embed_text(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingTextEmbeddingService:
    """Deterministic local embeddings for dev/test until provider-backed models are wired."""

    def __init__(self, dimensions: int = 384, model_name: str = "local-hashing-v1") -> None:
        if dimensions < 16:
            raise ValueError("Embedding dimensions must be at least 16.")
        self.dimensions = dimensions
        self.model_name = model_name

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._features(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            hashed = int.from_bytes(digest, byteorder="big", signed=False)
            index = hashed % self.dimensions
            sign = 1.0 if (hashed >> 63) == 0 else -1.0
            vector[index] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def _features(self, text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        tokens = [_stem(token.lower()) for token in _TOKEN_RE.findall(normalized)]
        features: list[str] = []
        for token in tokens:
            if not token:
                continue
            features.append(f"tok:{token}")
            if len(token) >= 5:
                features.extend(f"tri:{token[index:index + 3]}" for index in range(len(token) - 2))
        return features


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token
