"""Pydantic schemas for API contracts and graph payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PoleType = Literal["Person", "Object", "Location", "Event", "Organization"]


class DocumentIngestRequest(BaseModel):
    content: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Human-readable source identifier.")
    session_id: str = Field(default="default")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = Field(default="default")


class EntityCandidate(BaseModel):
    name: str
    entity_type: PoleType
    description: str = ""
    aliases: list[str] = Field(default_factory=list)


class RelationCandidate(BaseModel):
    source_name: str
    source_type: PoleType
    relationship_type: str
    target_name: str
    target_type: PoleType


class DuplicateReviewRequest(BaseModel):
    left_id: str
    right_id: str
    confirm: bool
    reviewer: str = Field(default="human")


class ResolutionDecision(BaseModel):
    action: Literal["merge", "pending", "create"]
    confidence: float
    matched_entity_id: str | None = None
    matched_name: str | None = None
    reason: str


class IngestResult(BaseModel):
    message_id: str
    entity_count: int
    relation_count: int
    resolutions: list[ResolutionDecision]


class ContextEntity(BaseModel):
    id: str
    name: str
    entity_type: PoleType
    score: float
    related_names: list[str] = Field(default_factory=list)


class ContextResponse(BaseModel):
    query: str
    session_id: str
    message_hits: list[str]
    entities: list[ContextEntity]
    reasoning: list[str]


class StatsResponse(BaseModel):
    conversations: int
    messages: int
    entities: int
    traces: int
    pending_duplicates: int
    checked_at: datetime


class HealthResponse(BaseModel):
    status: str
    neo4j: str
