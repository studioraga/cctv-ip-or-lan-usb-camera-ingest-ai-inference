from __future__ import annotations

class QdrantStore:
    """Optional local vector DB adapter.

    Install qdrant-client and run Qdrant before using this class.
    This adapter is intentionally lazy so the core CCTV pipeline works without Qdrant.
    """
    def __init__(self, url: str = "http://localhost:6333", collection: str = "ai_camera_events"):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(url=url)
        self.collection = collection

    def upsert_embedding(self, embedding_id: str, vector, payload: dict):
        # Fill in collection creation/point schema once embedding dimension is selected.
        raise NotImplementedError("Select embedding model/dimension before enabling Qdrant upsert")
