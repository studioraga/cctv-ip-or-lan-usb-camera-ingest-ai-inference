from __future__ import annotations

from typing import Any


class QdrantStore:
    """Optional local vector DB adapter.

    The core indexer writes JSONL without Qdrant.  This adapter becomes active
    only when qdrant-client is installed and --qdrant-url is supplied.
    """

    def __init__(self, url: str = "http://localhost:6333", collection: str = "ai_camera_events", dimension: int = 256):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(url=url)
        self.collection = collection
        self.dimension = int(dimension)

    def ensure_collection(self) -> None:
        from qdrant_client.http import models
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=self.dimension, distance=models.Distance.COSINE),
            )

    def upsert_embedding(self, embedding_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        from qdrant_client.http import models
        point_id = abs(hash(embedding_id)) % (2**63)
        self.client.upsert(
            collection_name=self.collection,
            points=[models.PointStruct(id=point_id, vector=vector, payload={"embedding_id": embedding_id, **payload})],
        )
