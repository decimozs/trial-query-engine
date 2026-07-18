import pytest

from app.services import retrieval
from app.services.retrieval import embed_query


def test_embed_query_returns_single_python_vector(monkeypatch) -> None:
    class FakeEmbedding:
        def tolist(self):
            return [1.0] * 384

    class FakeModel:
        def encode(self, texts, normalize_embeddings=False):
            assert texts == ["question"]
            assert normalize_embeddings is True
            return [FakeEmbedding()]

    monkeypatch.setattr(retrieval, "get_embedding_model", lambda: FakeModel())

    embedding = embed_query("question")

    assert len(embedding) == 384
    assert embedding[0] == 1.0


def test_hybrid_score_weights_semantic_and_keyword(monkeypatch) -> None:
    monkeypatch.setattr(retrieval.settings, "rag_semantic_weight", 0.7)
    monkeypatch.setattr(retrieval.settings, "rag_keyword_weight", 0.3)

    assert retrieval.blend_scores(semantic_score=0.8, keyword_score=0.5) == pytest.approx(0.71)


def test_keyword_tokens_keep_exact_terms_and_drop_noise() -> None:
    assert retrieval.keyword_tokens("What are common eligibility criteria for Type 2 Diabetes trials?") == [
        "eligibility",
        "type",
        "diabetes",
    ]
