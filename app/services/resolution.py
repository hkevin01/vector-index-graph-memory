"""Entity resolution and deduplication logic for graph-native identity."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models.schemas import EntityCandidate, ResolutionDecision
from app.services.embedding import HashEmbeddingService


@dataclass(frozen=True)
class ExistingEntity:
    id: str
    name: str
    entity_type: str
    aliases: list[str]
    embedding: list[float]


class ResolutionService:
    """Purpose: Turn extracted mentions into merge, pending, or create decisions.

    Inputs: A new entity candidate and same-type existing graph entities.
    Outputs: A resolution decision with score and rationale.
    Preconditions: Existing entities already include embeddings.
    Postconditions: Decisions respect the configured thresholds.
    Failure modes: None for ordinary candidate sets.
    """

    def __init__(
        self,
        embedding_service: HashEmbeddingService,
        auto_merge_threshold: float,
        pending_match_threshold: float,
    ) -> None:
        self.embedding_service = embedding_service
        self.auto_merge_threshold = auto_merge_threshold
        self.pending_match_threshold = pending_match_threshold

    def decide(
        self,
        candidate: EntityCandidate,
        existing_entities: list[ExistingEntity],
    ) -> ResolutionDecision:
        if not existing_entities:
            return ResolutionDecision(
                action="create",
                confidence=0.0,
                reason="No same-type candidates exist yet.",
            )

        candidate_embedding = self.embedding_service.embed(
            f"{candidate.entity_type} {candidate.name} {candidate.description}"
        )
        best_match: ExistingEntity | None = None
        best_score = -1.0
        best_reason = ""

        for existing in existing_entities:
            exact = self._exact_match(candidate, existing)
            fuzzy = self._fuzzy_match(candidate.name, existing)
            semantic = self.embedding_service.cosine_similarity(candidate_embedding, existing.embedding)
            score = max(exact, (fuzzy * 0.45) + (semantic * 0.55))
            if score > best_score:
                best_score = score
                best_match = existing
                best_reason = f"exact={exact:.2f}, fuzzy={fuzzy:.2f}, semantic={semantic:.2f}"

        assert best_match is not None
        if best_score >= self.auto_merge_threshold:
            return ResolutionDecision(
                action="merge",
                confidence=best_score,
                matched_entity_id=best_match.id,
                matched_name=best_match.name,
                reason=best_reason,
            )
        if best_score >= self.pending_match_threshold:
            return ResolutionDecision(
                action="pending",
                confidence=best_score,
                matched_entity_id=best_match.id,
                matched_name=best_match.name,
                reason=best_reason,
            )
        return ResolutionDecision(
            action="create",
            confidence=max(best_score, 0.0),
            matched_entity_id=best_match.id,
            matched_name=best_match.name,
            reason=best_reason,
        )

    def _exact_match(self, candidate: EntityCandidate, existing: ExistingEntity) -> float:
        normalized = candidate.name.casefold().strip()
        names = [existing.name, *existing.aliases]
        return 1.0 if any(normalized == value.casefold().strip() for value in names) else 0.0

    def _fuzzy_match(self, name: str, existing: ExistingEntity) -> float:
        scores = [SequenceMatcher(a=name.casefold(), b=existing.name.casefold()).ratio()]
        scores.extend(
            SequenceMatcher(a=name.casefold(), b=alias.casefold()).ratio() for alias in existing.aliases
        )
        return max(scores, default=0.0)
