"""Tests for the vector search module."""
import json
import os
import pickle
import tempfile
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import faiss
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from vector_search import VectorSearch


def _build_test_index(tmp_dir: str, dimension: int = 1536, n_vectors: int = 4):
    """Create a minimal FAISS index and metadata for testing."""
    index = faiss.IndexFlatL2(dimension)
    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((n_vectors, dimension)).astype("float32")
    index.add(vectors)

    metadata = [
        {"id": 1, "category": "location", "language": "en",
         "question": "Where is the nearest station?",
         "answer": "The nearest station is in Delhi."},
        {"id": 1, "category": "location", "language": "hi",
         "question": "निकटतम स्टेशन कहाँ है?",
         "answer": "निकटतम स्टेशन दिल्ली में है।"},
        {"id": 2, "category": "battery", "language": "en",
         "question": "How do I swap a battery?",
         "answer": "Go to any swap station and follow the instructions."},
        {"id": 2, "category": "battery", "language": "hi",
         "question": "बैटरी कैसे स्वैप करें?",
         "answer": "किसी भी स्वैप स्टेशन पर जाएं और निर्देशों का पालन करें।"},
    ]

    faiss.write_index(index, os.path.join(tmp_dir, "faqs.index"))
    with open(os.path.join(tmp_dir, "metadata.pkl"), "wb") as f:
        pickle.dump(metadata, f)

    return vectors


@pytest.fixture
def test_index_dir():
    """Create a temporary directory with a test FAISS index."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        _build_test_index(tmp_dir)
        yield tmp_dir


def _make_fake_embedding(dimension: int = 1536):
    """Return a deterministic fake embedding response."""
    rng = np.random.default_rng(99)
    return rng.standard_normal(dimension).astype("float32").tolist()


@patch("vector_search.OpenAI")
def test_init_missing_index(mock_openai_cls):
    """VectorSearch should raise FileNotFoundError when index is missing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with pytest.raises(FileNotFoundError, match="FAISS index not found"):
            VectorSearch(index_dir=tmp_dir)


@patch("vector_search.OpenAI")
def test_init_loads_index(mock_openai_cls, test_index_dir):
    """VectorSearch should load a valid FAISS index without errors."""
    vs = VectorSearch(index_dir=test_index_dir)
    assert vs.index.ntotal == 4
    assert len(vs.metadata) == 4


@patch("vector_search.OpenAI")
def test_search_filters_by_language(mock_openai_cls, test_index_dir):
    """Search should filter results by the requested language."""
    vs = VectorSearch(index_dir=test_index_dir)

    # Mock the embedding call
    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    vs.client.embeddings.create = MagicMock(return_value=mock_response)

    results_en = vs.search("Where is the station?", language="en", top_k=10)
    for r in results_en:
        assert r["language"] == "en"

    results_hi = vs.search("स्टेशन कहाँ है?", language="hi", top_k=10)
    for r in results_hi:
        assert r["language"] == "hi"


@patch("vector_search.OpenAI")
def test_search_returns_expected_fields(mock_openai_cls, test_index_dir):
    """Each search result should have the expected keys."""
    vs = VectorSearch(index_dir=test_index_dir)

    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    vs.client.embeddings.create = MagicMock(return_value=mock_response)

    results = vs.search("battery swap", language="en", top_k=2)
    assert len(results) > 0
    for r in results:
        assert "category" in r
        assert "question" in r
        assert "answer" in r
        assert "language" in r
        assert "similarity_score" in r
        assert 0 <= r["similarity_score"] <= 1


@patch("vector_search.OpenAI")
def test_get_context_for_llm_format(mock_openai_cls, test_index_dir):
    """get_context_for_llm should return a formatted string."""
    vs = VectorSearch(index_dir=test_index_dir)

    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    vs.client.embeddings.create = MagicMock(return_value=mock_response)

    context = vs.get_context_for_llm("station location", language="en", top_k=2)
    assert "relevant FAQs" in context.lower() or "Category:" in context
    assert "Q:" in context
    assert "A:" in context


@patch("vector_search.OpenAI")
def test_get_context_for_llm_no_results(mock_openai_cls, test_index_dir):
    """get_context_for_llm should return a 'no results' message when nothing matches the language."""
    vs = VectorSearch(index_dir=test_index_dir)

    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    vs.client.embeddings.create = MagicMock(return_value=mock_response)

    # Use a language code that has no entries
    context = vs.get_context_for_llm("test query", language="fr", top_k=2)
    assert "no similar faqs" in context.lower()


@patch("vector_search.OpenAI")
def test_embedding_cache(mock_openai_cls, test_index_dir):
    """Repeated queries should use the cache instead of calling the API again."""
    vs = VectorSearch(index_dir=test_index_dir)

    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    vs.client.embeddings.create = MagicMock(return_value=mock_response)

    # First call should hit the API
    vs.get_embedding("test query")
    assert vs.client.embeddings.create.call_count == 1

    # Second call with same text should use cache
    vs.get_embedding("test query")
    assert vs.client.embeddings.create.call_count == 1

    # Different query should hit API again
    vs.get_embedding("different query")
    assert vs.client.embeddings.create.call_count == 2
