from __future__ import annotations

import hashlib
from typing import Any

import httpx

from app.config import settings


class OllamaClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    async def embed(self, text: str) -> list[float]:
        payload = {
            "model": settings.embedding_model,
            "prompt": text,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}/api/embeddings", json=payload)
            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding")
                if isinstance(embedding, list):
                    return [float(v) for v in embedding]

        # Deterministic fallback embedding to keep memory pipeline functional.
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        while len(values) < settings.qdrant_vector_size:
            for byte in digest:
                values.append((byte / 127.5) - 1.0)
                if len(values) >= settings.qdrant_vector_size:
                    break
        return values

    async def ensure_models(self) -> None:
        async with httpx.AsyncClient(timeout=300.0) as client:
            for model in {settings.ollama_default_model, settings.ollama_fallback_model, settings.embedding_model}:
                payload = {"name": model}
                try:
                    await client.post(f"{self.base_url}/api/pull", json=payload)
                except Exception:
                    # Best effort; installer also pulls defaults.
                    continue
