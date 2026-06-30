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
            if response.status_code == 404:
                # Backward compatibility for Ollama variants exposing only /api/generate.
                prompt = self._messages_to_prompt(messages)
                generate_payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                }
                gen_response = await client.post(f"{self.base_url}/api/generate", json=generate_payload)
                gen_response.raise_for_status()
                gen_data = gen_response.json()
                text = gen_data.get("response")
                if isinstance(text, str):
                    return text
                raise ValueError("Ollama /api/generate response missing 'response' text.")

            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()

        models = data.get("models", [])
        names: list[str] = []
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("model")
                    if isinstance(name, str) and name.strip():
                        names.append(name.strip())

        # Keep stable ordering and remove duplicates.
        return sorted(set(names))

    @staticmethod
    def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"{role.upper()}: {content}")
        lines.append("ASSISTANT:")
        return "\n\n".join(lines)

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
