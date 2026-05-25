"""Deterministic local embeddings for graph writes and retrieval."""

from __future__ import annotations

import hashlib
import math
import re


class HashEmbeddingService:
    """Purpose: Produce deterministic local vectors without external model calls.

    Inputs: Arbitrary text and a configured output dimension.
    Outputs: A normalized dense float vector.
    Preconditions: Dimension is positive and text is non-empty or blank-safe.
    Postconditions: Returned vectors always have the configured length.
    Failure modes: Invalid dimensions raise ValueError during initialization.
    """

    def __init__(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        """Purpose: Convert text into a cosine-ready vector.

        Inputs: Free-form text.
        Outputs: A unit-normalized vector of floats.
        Preconditions: None.
        Postconditions: The vector length equals `self.dimensions`.
        Failure modes: None for normal text input.
        """

        buckets = [0.0] * self.dimensions
        tokens = re.findall(r"[A-Za-z0-9_+-]+", text.lower()) or ["<empty>"]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + (digest[5] / 255.0)
            buckets[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in buckets))
        if norm == 0.0:
            return buckets
        return [value / norm for value in buckets]

    @staticmethod
    def cosine_similarity(left: list[float], right: list[float]) -> float:
        """Purpose: Compute cosine similarity between two equal-length vectors."""

        if len(left) != len(right):
            raise ValueError("Vectors must have the same length")
        return sum(a * b for a, b in zip(left, right, strict=True))
