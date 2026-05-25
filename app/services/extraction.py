"""Lightweight entity and relation extraction following a staged ladder."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.models.schemas import EntityCandidate, PoleType, RelationCandidate


RELATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r'"?(?P<source>[A-Z][A-Za-z0-9+ .-]+?)"?\s+developed\s+"?(?P<target>[A-Z][A-Za-z0-9+ .-]+)"?', "DEVELOPED_BY_REVERSED"),
    (r'"?(?P<source>[A-Z][A-Za-z0-9+ .-]+?)"?\s+competes\s+with\s+"?(?P<target>[A-Z][A-Za-z0-9+ .-]+)"?', "COMPETES_WITH"),
    (r'"?(?P<source>[A-Z][A-Za-z0-9+ .-]+?)"?\s+is\s+based\s+in\s+"?(?P<target>[A-Z][A-Za-z0-9+ .-]+)"?', "LOCATED_IN"),
    (r'"?(?P<source>[A-Z][A-Za-z0-9+ .-]+?)"?\s+works\s+at\s+"?(?P<target>[A-Z][A-Za-z0-9+ .-]+)"?', "WORKS_AT"),
)


class ExtractionService:
    """Purpose: Extract POLE+O candidates and typed relations from raw text.

    Inputs: Free-form note or message text.
    Outputs: Entity candidates and relationship candidates.
    Preconditions: None.
    Postconditions: Output names are deduplicated by surface form.
    Failure modes: No exceptions for ordinary text; empty output is allowed.
    """

    def extract(self, text: str) -> tuple[list[EntityCandidate], list[RelationCandidate]]:
        entities = self._collect_entities(text)
        relations = self._collect_relations(text, entities)
        return entities, relations

    def _collect_entities(self, text: str) -> list[EntityCandidate]:
        candidates: dict[str, EntityCandidate] = {}
        for match in re.finditer(r'"([^"]{2,80})"', text):
            name = match.group(1).strip()
            if name:
                candidate = self._build_entity(name, text)
                candidates.setdefault(candidate.name.lower(), candidate)

        for match in re.finditer(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][A-Za-z0-9+.-]+){0,4})\b", text):
            name = match.group(0).strip()
            if len(name) < 3 or name.lower() in {"The", "This", "That", "These"}:
                continue
            candidate = self._build_entity(name, text)
            candidates.setdefault(candidate.name.lower(), candidate)

        return sorted(candidates.values(), key=lambda item: item.name)

    def _collect_relations(
        self,
        text: str,
        entities: list[EntityCandidate],
    ) -> list[RelationCandidate]:
        entity_map = {entity.name.lower(): entity for entity in entities}
        relations: list[RelationCandidate] = []
        for pattern, relation_type in RELATION_PATTERNS:
            for match in re.finditer(pattern, text):
                source_name = match.group("source").strip().rstrip(".,")
                target_name = match.group("target").strip().rstrip(".,")
                source = self._resolve_by_surface(source_name, entity_map)
                target = self._resolve_by_surface(target_name, entity_map)
                if not source or not target:
                    continue
                if relation_type == "DEVELOPED_BY_REVERSED":
                    relations.append(
                        RelationCandidate(
                            source_name=target.name,
                            source_type=target.entity_type,
                            relationship_type="DEVELOPED_BY",
                            target_name=source.name,
                            target_type=source.entity_type,
                        )
                    )
                    continue
                relations.append(
                    RelationCandidate(
                        source_name=source.name,
                        source_type=source.entity_type,
                        relationship_type=relation_type,
                        target_name=target.name,
                        target_type=target.entity_type,
                    )
                )
        return relations

    def _build_entity(self, name: str, text: str) -> EntityCandidate:
        entity_type = self._infer_type(name, text)
        return EntityCandidate(
            name=name,
            entity_type=entity_type,
            description=f"Extracted from text for {entity_type.lower()} memory.",
            aliases=[name],
        )

    def _infer_type(self, name: str, text: str) -> PoleType:
        lowered = name.lower()
        context = text.lower()
        if any(token in lowered for token in ["inc", "corp", "llc", "organization", "lab", "labs"]):
            return "Organization"
        if any(token in lowered for token in ["city", "county", "street", "francisco", "york"]):
            return "Location"
        if any(token in lowered for token in ["summit", "conference", "launch", "release"]):
            return "Event"
        if "developed" in context and lowered in context:
            return "Object"
        tokens = name.split()
        if len(tokens) == 2 and all(part[:1].isupper() and part[1:].islower() for part in tokens):
            return "Person"
        return "Object"

    def _resolve_by_surface(
        self,
        name: str,
        entity_map: dict[str, EntityCandidate],
    ) -> EntityCandidate | None:
        lowered = name.lower()
        if lowered in entity_map:
            return entity_map[lowered]
        best_score = 0.0
        best_entity: EntityCandidate | None = None
        for candidate_name, entity in entity_map.items():
            score = SequenceMatcher(a=lowered, b=candidate_name).ratio()
            if score > best_score:
                best_score = score
                best_entity = entity
        return best_entity if best_score >= 0.8 else None
