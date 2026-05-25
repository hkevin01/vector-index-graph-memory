from app.services.embedding import HashEmbeddingService


def test_embedding_is_deterministic() -> None:
    service = HashEmbeddingService(32)
    left = service.embed("Claude Code competes with Codex")
    right = service.embed("Claude Code competes with Codex")
    assert left == right


def test_cosine_similarity_prefers_similar_text() -> None:
    service = HashEmbeddingService(64)
    base = service.embed("Anthropic developed Claude Code")
    similar = service.embed("Claude Code was developed by Anthropic")
    different = service.embed("Bananas grow in tropical regions")
    assert service.cosine_similarity(base, similar) > service.cosine_similarity(base, different)
