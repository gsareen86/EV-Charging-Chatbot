"""
Vector search utility for FAQ retrieval using FAISS
"""
import os
import pickle
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
import faiss
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class VectorSearch:
    """Handle vector similarity search for FAQ retrieval"""

    def __init__(self, index_dir: str = None, embedding_model: str = "text-embedding-3-small"):
        """Initialize vector search with FAISS index"""
        if index_dir is None:
            project_root = Path(__file__).parent.parent
            index_dir = project_root / "data" / "faiss_index"

        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.embedding_model = embedding_model

        # Load FAISS index
        index_path = os.path.join(index_dir, 'faqs.index')
        metadata_path = os.path.join(index_dir, 'metadata.pkl')

        if not os.path.exists(index_path):
            raise FileNotFoundError(f"FAISS index not found at {index_path}. Please run build_vector_db.py first.")

        self.index = faiss.read_index(index_path)

        with open(metadata_path, 'rb') as f:
            self.metadata = pickle.load(f)

        print(f"Loaded FAISS index with {self.index.ntotal} vectors")

    def get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for query text"""
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        embedding = np.array(response.data[0].embedding).astype('float32')
        return embedding.reshape(1, -1)

    def search(self, query: str, language: str = 'en', top_k: int = 3) -> List[Dict]:
        """
        Search for similar FAQs based on query

        Args:
            query: User query text
            language: Language preference ('en' or 'hi')
            top_k: Number of top results to return

        Returns:
            List of matching FAQ entries with similarity scores
        """
        # Get query embedding
        query_embedding = self.get_embedding(query)

        # Search in FAISS index
        distances, indices = self.index.search(query_embedding, top_k * 2)  # Get more to filter by language

        # Filter results by language and prepare output
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.metadata):
                faq = self.metadata[idx]

                # Filter by language if specified
                if language and faq['language'] != language:
                    continue

                results.append({
                    'category': faq['category'],
                    'question': faq['question'],
                    'answer': faq['answer'],
                    'language': faq['language'],
                    'similarity_score': float(1 / (1 + dist))  # Convert distance to similarity score
                })

                if len(results) >= top_k:
                    break

        return results

    def get_context_for_llm(self, query: str, language: str = 'en', top_k: int = 3) -> str:
        """
        Get formatted context from similar FAQs for LLM

        Args:
            query: User query
            language: Language preference
            top_k: Number of results to include

        Returns:
            Formatted context string for LLM prompt
        """
        results = self.search(query, language, top_k)

        if not results:
            return "No similar FAQs found."

        context_parts = ["Here are the most relevant FAQs:\n"]

        for i, result in enumerate(results, 1):
            context_parts.append(f"\n{i}. Category: {result['category']}")
            context_parts.append(f"   Q: {result['question']}")
            context_parts.append(f"   A: {result['answer']}")
            context_parts.append(f"   (Relevance: {result['similarity_score']:.2f})")

        return "\n".join(context_parts)


# Test function
def test_search():
    """Test the vector search functionality"""
    vs = VectorSearch()

    # Test queries
    test_queries = [
        ("Where is the nearest charging station?", "en"),
        ("निकटतम चार्जिंग स्टेशन कहाँ है?", "hi"),
        ("How do I reset my password?", "en"),
        ("Battery swapping is not working", "en"),
    ]

    for query, lang in test_queries:
        print(f"\nQuery: {query} (Language: {lang})")
        print("-" * 80)
        results = vs.search(query, language=lang, top_k=2)
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['question']}")
            print(f"   Answer: {result['answer'][:100]}...")
            print(f"   Score: {result['similarity_score']:.3f}")


if __name__ == "__main__":
    test_search()
