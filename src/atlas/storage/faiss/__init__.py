"""FAISS-based vector storage with enhanced matching and pattern learning."""

from atlas.storage.faiss.vector_faiss import FaissVectorIndex
from atlas.storage.faiss.enhanced_vector_faiss import (
    EnhancedFaissVectorIndex,
    MatchResult,
    Pattern,
)
from atlas.storage.faiss.noop_index import NoOpVectorIndex

__all__ = [
    "FaissVectorIndex",
    "EnhancedFaissVectorIndex",
    "MatchResult",
    "Pattern",
    "NoOpVectorIndex",
]
