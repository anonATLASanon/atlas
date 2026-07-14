"""Ray-based parallel processing for Atlas labeling system.

This module provides parallel processing capabilities using Ray for distributed
document labeling. It includes:

- RayStorageActor: Thread-safe storage actor for SQLite and FAISS operations
- RayLabelingWorker: Stateless worker for parallel document processing
- RayLabelingOrchestrator: Coordinator for the entire parallel workflow
- RateLimiter: Token bucket rate limiter for API calls

Usage:
    from atlas.parallel import RayLabelingOrchestrator
    
    orchestrator = RayLabelingOrchestrator(
        store=store,
        index_dir=index_dir,
        config=config,
        context=context,
        num_workers=4
    )
    
    results = orchestrator.label_documents_parallel(documents)
"""

from atlas.parallel.rate_limiter import RateLimiter
from atlas.parallel.ray_storage import RayStorageActor
from atlas.parallel.ray_worker import RayLabelingWorker
from atlas.parallel.ray_orchestrator import RayLabelingOrchestrator

__all__ = [
    "RateLimiter",
    "RayStorageActor",
    "RayLabelingWorker",
    "RayLabelingOrchestrator",
]


