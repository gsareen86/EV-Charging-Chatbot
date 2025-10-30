"""
Script to build FAISS vector database from FAQ data
"""
import json
import os
import pickle
from pathlib import Path
from typing import List, Dict
import numpy as np
from openai import OpenAI
import faiss
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class VectorDBBuilder:
    """Build and manage FAISS vector database for FAQ retrieval"""

    def __init__(self, embedding_model: str = "text-embedding-3-small"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.embedding_model = embedding_model
        self.dimension = 1536  # dimension for text-embedding-3-small

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a given text"""
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    def build_index(self, faq_file: str, output_dir: str):
        """Build FAISS index from FAQ data"""
        # Load FAQ data
        with open(faq_file, 'r', encoding='utf-8') as f:
            faqs = json.load(f)

        print(f"Loaded {len(faqs)} FAQs")

        # Prepare data structures
        embeddings_list = []
        metadata_list = []

        # Process each FAQ for both English and Hindi
        for idx, faq in enumerate(faqs):
            # English version
            en_text = f"{faq['question_en']} {faq['answer_en']}"
            en_embedding = self.get_embedding(en_text)
            embeddings_list.append(en_embedding)
            metadata_list.append({
                'id': faq['id'],
                'category': faq['category'],
                'language': 'en',
                'question': faq['question_en'],
                'answer': faq['answer_en']
            })

            # Hindi version
            hi_text = f"{faq['question_hi']} {faq['answer_hi']}"
            hi_embedding = self.get_embedding(hi_text)
            embeddings_list.append(hi_embedding)
            metadata_list.append({
                'id': faq['id'],
                'category': faq['category'],
                'language': 'hi',
                'question': faq['question_hi'],
                'answer': faq['answer_hi']
            })

            print(f"Processed FAQ {idx + 1}/{len(faqs)}")

        # Convert to numpy array
        embeddings_array = np.array(embeddings_list).astype('float32')

        # Create FAISS index
        index = faiss.IndexFlatL2(self.dimension)
        index.add(embeddings_array)

        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Save index and metadata
        index_path = os.path.join(output_dir, 'faqs.index')
        metadata_path = os.path.join(output_dir, 'metadata.pkl')

        faiss.write_index(index, index_path)
        with open(metadata_path, 'wb') as f:
            pickle.dump(metadata_list, f)

        print(f"\nVector database built successfully!")
        print(f"Index saved to: {index_path}")
        print(f"Metadata saved to: {metadata_path}")
        print(f"Total vectors: {index.ntotal}")

def main():
    """Main function to build vector database"""
    # Get project root directory
    project_root = Path(__file__).parent.parent
    faq_file = project_root / "data" / "faq_data.json"
    output_dir = project_root / "data" / "faiss_index"

    # Build the vector database
    builder = VectorDBBuilder()
    builder.build_index(str(faq_file), str(output_dir))

if __name__ == "__main__":
    main()
