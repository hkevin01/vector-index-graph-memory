"""HTTP routes for ingest, retrieval, and duplicate review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import ChatRequest, DuplicateReviewRequest, HealthResponse, StatsResponse
from app.models.schemas import ContextResponse, DocumentIngestRequest, IngestResult
from app.services.memory import MemoryService


router = APIRouter(prefix="/api", tags=["memory"])

_provider: callable[[], MemoryService] | None = None


def set_memory_service_provider(provider: callable[[], MemoryService]) -> None:
    global _provider
    _provider = provider


def get_memory_service() -> MemoryService:
    if _provider is None:
        raise RuntimeError("Dependency override not configured")
    return _provider()


@router.get("/health", response_model=HealthResponse)
def health(service: MemoryService = Depends(get_memory_service)) -> HealthResponse:
    if not service.repository.ping():
        return HealthResponse(status="degraded", neo4j="unreachable")
    return HealthResponse(status="ok", neo4j="connected")


@router.post("/documents", response_model=IngestResult)
def ingest_document(
    request: DocumentIngestRequest,
    service: MemoryService = Depends(get_memory_service),
) -> IngestResult:
    try:
        return service.ingest_document(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/chat", response_model=ContextResponse)
def chat(
    request: ChatRequest,
    service: MemoryService = Depends(get_memory_service),
) -> ContextResponse:
    try:
        return service.chat(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/duplicates/review")
def review_duplicate(
    request: DuplicateReviewRequest,
    service: MemoryService = Depends(get_memory_service),
) -> dict[str, str]:
    try:
        service.repository.review_duplicate(request.left_id, request.right_id, request.confirm, request.reviewer)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/stats", response_model=StatsResponse)
def stats(service: MemoryService = Depends(get_memory_service)) -> StatsResponse:
    try:
        return service.repository.stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
