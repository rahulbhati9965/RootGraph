import math
import re
from typing import List, Dict, Any, Optional
from collections import Counter

from app.vector.chunker import DocumentChunk
from app.core.config import settings


class LocalSemanticEmbedding:
    """Fast, zero-dependency semantic vector encoder using subword and character n-gram frequencies.
    Produces dense normalized embeddings for cosine similarity search without requiring remote API keys.
    """

    def __init__(self, dim: int = 128):
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        tokens = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
        vec = [0.0] * self.dim

        for token in tokens:
            # Hash tokens and 3-grams across vector dimensions
            idx = hash(token) % self.dim
            vec[idx] += 1.0

            for i in range(len(token) - 2):
                gram = token[i:i+3]
                g_idx = hash(gram) % self.dim
                vec[g_idx] += 0.5

        # Normalize to unit length (L2 norm)
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class VectorStore:
    """Semantic vector database supporting chunk indexing, cosine similarity ranking,
    and metadata filtering.
    """

    def __init__(self):
        self._chunks: Dict[str, DocumentChunk] = {}
        self._embeddings: Dict[str, List[float]] = {}
        self._embedder = LocalSemanticEmbedding(dim=128)

    def add_chunks(self, chunks: List[DocumentChunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.id] = chunk
            # Embed content enriched with title and section
            searchable_text = f"{chunk.title} {chunk.section}\n{chunk.content}"
            self._embeddings[chunk.id] = self._embedder.embed(searchable_text)

    def search(
        self,
        query: str,
        service_filter: Optional[str] = None,
        top_k: int = 5
    ) -> List[DocumentChunk]:
        """Performs cosine similarity semantic search with optional metadata filtering."""
        if not self._chunks:
            return []

        query_vec = self._embedder.embed(query)
        scored_results = []

        for chunk_id, doc_vec in self._embeddings.items():
            chunk = self._chunks[chunk_id]

            # Apply service metadata filter if requested
            if service_filter:
                chunk_service = chunk.metadata.get("service")
                if chunk_service and chunk_service != service_filter:
                    continue

            # Compute dot product of unit vectors (cosine similarity)
            score = sum(q * d for q, d in zip(query_vec, doc_vec))

            # Bonus for exact keyword matches in section title or content
            query_terms = set(re.findall(r"\b\w+\b", query.lower()))
            content_lower = chunk.content.lower()
            matches = sum(1 for term in query_terms if term in content_lower)
            adjusted_score = score + (0.1 * matches)

            result_chunk = chunk.model_copy()
            result_chunk.score = round(adjusted_score, 4)
            scored_results.append(result_chunk)

        # Sort descending by score
        scored_results.sort(key=lambda c: c.score, reverse=True)
        return scored_results[:top_k]

    def clear(self) -> None:
        self._chunks.clear()
        self._embeddings.clear()
