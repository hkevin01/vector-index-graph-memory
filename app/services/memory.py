"""Application service that orchestrates extraction, resolution, and retrieval."""

from __future__ import annotations

from app.models.schemas import ChatRequest, ContextResponse, DocumentIngestRequest, IngestResult, ResolutionDecision
from app.repositories.graph import GraphRepository
from app.services.embedding import HashEmbeddingService
from app.services.extraction import ExtractionService
from app.services.resolution import ResolutionService


class MemoryService:
    """Purpose: Coordinate writes and reads across all memory tiers.

    Inputs: API-layer requests plus configured collaborators.
    Outputs: Ingestion results, context payloads, and health-oriented operations.
    Preconditions: Repository schema can be ensured before writes.
    Postconditions: Ingested text updates graph memory deterministically.
    Failure modes: Repository failures propagate to the caller.
    """

    def __init__(
        self,
        repository: GraphRepository,
        embedding_service: HashEmbeddingService,
        extraction_service: ExtractionService,
        resolution_service: ResolutionService,
    ) -> None:
        self.repository = repository
        self.embedding_service = embedding_service
        self.extraction_service = extraction_service
        self.resolution_service = resolution_service

    def ingest_document(self, request: DocumentIngestRequest) -> IngestResult:
        self.repository.ensure_schema()
        message_embedding = self.embedding_service.embed(request.content)
        message_id = self.repository.create_message(request.session_id, "document", request.content, message_embedding)

        entities, relations = self.extraction_service.extract(request.content)
        resolutions: list[ResolutionDecision] = []
        resolved_ids: dict[str, str] = {}
        touched_entity_ids: list[str] = []

        for entity in entities:
            existing_entities = self.repository.find_existing_entities(entity.entity_type)
            decision = self.resolution_service.decide(entity, existing_entities)
            resolutions.append(decision)
            candidate_payload = entity.model_dump()
            if decision.action == "merge" and decision.matched_entity_id:
                self.repository.merge_entity(decision.matched_entity_id, candidate_payload)
                resolved_ids[entity.name.casefold()] = decision.matched_entity_id
                touched_entity_ids.append(decision.matched_entity_id)
                continue

            entity_embedding = self.embedding_service.embed(
                f"{entity.entity_type} {entity.name} {entity.description} {' '.join(entity.aliases)}"
            )
            new_entity_id = self.repository.create_entity(candidate_payload, entity_embedding)
            resolved_ids[entity.name.casefold()] = new_entity_id
            touched_entity_ids.append(new_entity_id)
            if decision.action == "pending" and decision.matched_entity_id:
                self.repository.create_pending_same_as(
                    new_entity_id,
                    decision.matched_entity_id,
                    decision.confidence,
                    decision.reason,
                )

        self.repository.connect_message_mentions(message_id, touched_entity_ids)
        self.repository.connect_entities(relations, resolved_ids)

        return IngestResult(
            message_id=message_id,
            entity_count=len(resolved_ids),
            relation_count=len(relations),
            resolutions=resolutions,
        )

    def chat(self, request: ChatRequest) -> ContextResponse:
        self.repository.ensure_schema()
        message_embedding = self.embedding_service.embed(request.message)
        message_id = self.repository.create_message(request.session_id, "user", request.message, message_embedding)
        context = self.repository.build_context(request.message, request.session_id, message_embedding)
        self.repository.create_reasoning_trace(
            message_id,
            request.message,
            [entity.id for entity in context.entities],
        )
        return context
