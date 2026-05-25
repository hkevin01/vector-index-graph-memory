"""Runtime configuration for the graph-native memory prototype."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Purpose: Hold runtime configuration loaded from the environment.

    Inputs: Environment variables for Neo4j connectivity and threshold tuning.
    Outputs: An immutable configuration object.
    Preconditions: Environment variables are either absent or parseable.
    Postconditions: All settings have concrete defaulted values.
    Failure modes: Invalid numeric values raise ValueError during parsing.
    """

    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    embedding_dimensions: int
    auto_merge_threshold: float
    pending_match_threshold: float


def get_settings() -> Settings:
    """Purpose: Build the process-wide configuration object.

    Inputs: Process environment variables.
    Outputs: A Settings instance.
    Preconditions: None.
    Postconditions: Missing values are replaced with safe local defaults.
    Failure modes: Raises ValueError if configured numbers cannot be parsed.
    """

    return Settings(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "change-this-password"),
        embedding_dimensions=int(os.getenv("MEMORY_EMBEDDING_DIMENSIONS", "256")),
        auto_merge_threshold=float(os.getenv("AUTO_MERGE_THRESHOLD", "0.95")),
        pending_match_threshold=float(os.getenv("PENDING_MATCH_THRESHOLD", "0.85")),
    )
