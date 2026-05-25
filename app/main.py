"""FastAPI entrypoint for the graph-native vector index fix prototype."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.repositories.graph import GraphRepository
from app.routes import api
from app.services.embedding import HashEmbeddingService
from app.services.extraction import ExtractionService
from app.services.memory import MemoryService
from app.services.resolution import ResolutionService


settings = get_settings()
repository = GraphRepository(settings)
embedding_service = HashEmbeddingService(settings.embedding_dimensions)
extraction_service = ExtractionService()
resolution_service = ResolutionService(
    embedding_service=embedding_service,
    auto_merge_threshold=settings.auto_merge_threshold,
    pending_match_threshold=settings.pending_match_threshold,
)
memory_service = MemoryService(
    repository=repository,
    embedding_service=embedding_service,
    extraction_service=extraction_service,
    resolution_service=resolution_service,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    repository.close()


app = FastAPI(
    title="Vector Index Graph Memory",
    version="0.1.0",
    lifespan=lifespan,
)

api.set_memory_service_provider(lambda: memory_service)
app.include_router(api.router)
