from app.services.extraction import ExtractionService


def test_extraction_finds_entities_and_relations() -> None:
    service = ExtractionService()
    entities, relations = service.extract(
        'Anthropic developed "Claude Code". Claude Code competes with Codex.'
    )
    entity_names = {entity.name for entity in entities}
    relation_types = {relation.relationship_type for relation in relations}
    assert "Anthropic" in entity_names
    assert "Claude Code" in entity_names
    assert "Codex" in entity_names
    assert "DEVELOPED_BY" in relation_types
    assert "COMPETES_WITH" in relation_types
