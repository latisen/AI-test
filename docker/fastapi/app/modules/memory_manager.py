from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.models.schemas import MemoryItem
from app.modules.ollama_client import OllamaClient


class MemoryManager:
    def __init__(self, qdrant_url: str, collection: str, ollama_client: OllamaClient) -> None:
        self.collection = collection
        self.ollama_client = ollama_client
        self.client = QdrantClient(url=qdrant_url)

    def ensure_collection(self) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection in existing:
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=settings.qdrant_vector_size, distance=Distance.COSINE),
        )

    async def write_memory(
        self,
        user_id: str,
        character_id: str,
        role: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        memory_id = str(uuid.uuid4())
        embedding = await self.ollama_client.embed(text)
        item = MemoryItem(
            id=memory_id,
            user_id=user_id,
            character_id=character_id,
            role=role,
            text=text,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )

        self.client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=memory_id,
                    vector=embedding,
                    payload=item.model_dump(mode="json"),
                )
            ],
        )
        return memory_id

    async def retrieve_relevant_memories(
        self,
        user_id: str,
        character_id: str,
        query_text: str,
        top_k: int,
    ) -> list[str]:
        query_vector = await self.ollama_client.embed(query_text)
        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
            query_filter={
                "must": [
                    {"key": "user_id", "match": {"value": user_id}},
                    {"key": "character_id", "match": {"value": character_id}},
                ]
            },
        )

        snippets: list[str] = []
        for result in results:
            payload = result.payload or {}
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                snippets.append(text)
        return snippets
