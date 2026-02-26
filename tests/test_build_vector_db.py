"""Tests for the vector database builder module."""
import json
import os
import tempfile
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import faiss
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from build_vector_db import VectorDBBuilder


SAMPLE_FAQ_DATA = [
    {
        "id": 1,
        "category": "location",
        "question_en": "Where is the nearest charging station?",
        "answer_en": "The nearest station is in Delhi NCR.",
        "question_hi": "निकटतम चार्जिंग स्टेशन कहाँ है?",
        "answer_hi": "निकटतम स्टेशन दिल्ली NCR में है।"
    },
    {
        "id": 2,
        "category": "battery",
        "question_en": "How do I swap a battery?",
        "answer_en": "Visit any swap station and follow the process.",
        "question_hi": "बैटरी कैसे स्वैप करें?",
        "answer_hi": "किसी भी स्वैप स्टेशन पर जाएं।"
    },
]


def _make_fake_embedding(dimension: int = 1536):
    """Return a deterministic fake embedding."""
    rng = np.random.default_rng(42)
    return rng.standard_normal(dimension).tolist()


@patch("build_vector_db.OpenAI")
def test_get_embedding(mock_openai_cls):
    """VectorDBBuilder.get_embedding should return a list of floats."""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    mock_client.embeddings.create.return_value = mock_response

    builder = VectorDBBuilder()
    result = builder.get_embedding("test text")

    assert isinstance(result, list)
    assert len(result) == 1536
    mock_client.embeddings.create.assert_called_once()


@patch("build_vector_db.OpenAI")
def test_build_index_creates_files(mock_openai_cls):
    """build_index should create both index and metadata files."""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    mock_client.embeddings.create.return_value = mock_response

    with tempfile.TemporaryDirectory() as tmp_dir:
        faq_file = os.path.join(tmp_dir, "faqs.json")
        output_dir = os.path.join(tmp_dir, "index_output")

        with open(faq_file, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_FAQ_DATA, f)

        builder = VectorDBBuilder()
        builder.build_index(faq_file, output_dir)

        # Verify output files exist
        assert os.path.exists(os.path.join(output_dir, "faqs.index"))
        assert os.path.exists(os.path.join(output_dir, "metadata.pkl"))

        # Verify index has correct number of vectors (2 FAQs * 2 languages = 4)
        index = faiss.read_index(os.path.join(output_dir, "faqs.index"))
        assert index.ntotal == 4

        # Verify embeddings were requested for each FAQ (2 per FAQ: en + hi)
        assert mock_client.embeddings.create.call_count == 4


@patch("build_vector_db.OpenAI")
def test_build_index_metadata_structure(mock_openai_cls):
    """Built metadata should have the correct structure."""
    import pickle

    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    fake_emb = _make_fake_embedding()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_emb)]
    mock_client.embeddings.create.return_value = mock_response

    with tempfile.TemporaryDirectory() as tmp_dir:
        faq_file = os.path.join(tmp_dir, "faqs.json")
        output_dir = os.path.join(tmp_dir, "index_output")

        with open(faq_file, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_FAQ_DATA, f)

        builder = VectorDBBuilder()
        builder.build_index(faq_file, output_dir)

        with open(os.path.join(output_dir, "metadata.pkl"), "rb") as f:
            metadata = pickle.load(f)

        assert len(metadata) == 4
        for entry in metadata:
            assert "id" in entry
            assert "category" in entry
            assert "language" in entry
            assert entry["language"] in ("en", "hi")
            assert "question" in entry
            assert "answer" in entry


@patch("build_vector_db.OpenAI")
def test_build_index_empty_faq_list(mock_openai_cls):
    """Building from an empty FAQ list should produce an empty index."""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    with tempfile.TemporaryDirectory() as tmp_dir:
        faq_file = os.path.join(tmp_dir, "faqs.json")
        output_dir = os.path.join(tmp_dir, "index_output")

        with open(faq_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        builder = VectorDBBuilder()
        builder.build_index(faq_file, output_dir)

        index = faiss.read_index(os.path.join(output_dir, "faqs.index"))
        assert index.ntotal == 0
        assert mock_client.embeddings.create.call_count == 0
