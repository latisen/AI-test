from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings


class OllamaClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        payload = {"model": model, "messages": messages, "stream": False}
        timeout = httpx.Timeout(settings.ollama_chat_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                if response.status_code == 404:
                    chat_error = self._extract_error_text(response)
                    if self._is_model_not_found_error(chat_error):
                        raise RuntimeError(
                            f"Model '{model}' not found in Ollama. Pull it in the running Ollama service and retry. "
                            f"Details: {chat_error}"
                        )

                    # Backward compatibility for Ollama variants exposing only /api/generate.
                    prompt = self._messages_to_prompt(messages)
                    generate_payload = {
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                    }
                    gen_response = await client.post(f"{self.base_url}/api/generate", json=generate_payload)
                    if gen_response.status_code != 404:
                        gen_response.raise_for_status()
                        gen_data = gen_response.json()
                        text = gen_data.get("response")
                        if isinstance(text, str):
                            return text
                        raise ValueError("Ollama /api/generate response missing 'response' text.")

                    gen_error = self._extract_error_text(gen_response)
                    if self._is_model_not_found_error(gen_error):
                        raise RuntimeError(
                            f"Model '{model}' not found in Ollama. Pull it in the running Ollama service and retry. "
                            f"Details: {gen_error}"
                        )

                    # Final fallback for OpenAI-compatible servers.
                    oai_payload = {
                        "model": model,
                        "messages": messages,
                        "stream": False,
                    }
                    oai_response = await client.post(f"{self.base_url}/v1/chat/completions", json=oai_payload)
                    if oai_response.status_code == 404:
                        raise RuntimeError(
                            "No supported chat endpoint found on upstream LLM service. "
                            "Tried /api/chat, /api/generate, and /v1/chat/completions."
                        )
                    oai_response.raise_for_status()
                    oai_data = oai_response.json()
                    choices = oai_data.get("choices", [])
                    if isinstance(choices, list) and choices:
                        first = choices[0]
                        if isinstance(first, dict):
                            message = first.get("message", {})
                            if isinstance(message, dict):
                                content = message.get("content")
                                if isinstance(content, str):
                                    return content
                            text = first.get("text")
                            if isinstance(text, str):
                                return text
                    raise ValueError("OpenAI-compatible response missing assistant text.")

                response.raise_for_status()
                data = response.json()
                return data["message"]["content"]
        except httpx.ReadTimeout as exc:
            raise RuntimeError(
                f"Timed out waiting for model '{model}' after {settings.ollama_chat_timeout_seconds}s. "
                "Increase OLLAMA_CHAT_TIMEOUT_SECONDS or reduce generation load."
            ) from exc

    async def chat_stream(self, model: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        timeout = httpx.Timeout(settings.ollama_chat_timeout_seconds)
        payload = {"model": model, "messages": messages, "stream": True}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status_code == 404:
                        body = await response.aread()
                        detail = self._extract_error_text_from_raw(body)
                        if self._is_model_not_found_error(detail):
                            raise RuntimeError(
                                f"Model '{model}' not found in Ollama. Pull it in the running Ollama service and retry. "
                                f"Details: {detail}"
                            )

                        async for chunk in self._stream_generate(client, model, messages):
                            yield chunk
                        return

                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message = item.get("message")
                        if isinstance(message, dict):
                            content = message.get("content")
                            if isinstance(content, str) and content:
                                yield content
        except httpx.ReadTimeout as exc:
            raise RuntimeError(
                f"Timed out waiting for model '{model}' after {settings.ollama_chat_timeout_seconds}s. "
                "Increase OLLAMA_CHAT_TIMEOUT_SECONDS or reduce generation load."
            ) from exc

    async def _stream_generate(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        prompt = self._messages_to_prompt(messages)
        payload = {"model": model, "prompt": prompt, "stream": True}
        async with client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
            if response.status_code == 404:
                body = await response.aread()
                detail = self._extract_error_text_from_raw(body)
                if self._is_model_not_found_error(detail):
                    raise RuntimeError(
                        f"Model '{model}' not found in Ollama. Pull it in the running Ollama service and retry. "
                        f"Details: {detail}"
                    )
                raise RuntimeError(
                    "No supported chat endpoint found on upstream LLM service. "
                    "Tried /api/chat and /api/generate for streaming mode."
                )

            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = item.get("response")
                if isinstance(text, str) and text:
                    yield text

    async def list_models(self) -> list[str]:
        names: set[str] = set()
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Installed models
            try:
                tags_response = await client.get(f"{self.base_url}/api/tags")
                tags_response.raise_for_status()
                tags_data = tags_response.json()
                tags_models = tags_data.get("models", [])
                if isinstance(tags_models, list):
                    for item in tags_models:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("model")
                            if isinstance(name, str) and name.strip():
                                names.add(name.strip())
            except Exception:
                pass

            # Currently loaded/running models (some builds expose names here only)
            try:
                ps_response = await client.get(f"{self.base_url}/api/ps")
                ps_response.raise_for_status()
                ps_data = ps_response.json()
                ps_models = ps_data.get("models", [])
                if isinstance(ps_models, list):
                    for item in ps_models:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("model")
                            if isinstance(name, str) and name.strip():
                                names.add(name.strip())
            except Exception:
                pass

            # OpenAI-compatible model listing fallback.
            try:
                v1_models_response = await client.get(f"{self.base_url}/v1/models")
                v1_models_response.raise_for_status()
                v1_data = v1_models_response.json()
                data_items = v1_data.get("data", [])
                if isinstance(data_items, list):
                    for item in data_items:
                        if isinstance(item, dict):
                            model_id = item.get("id")
                            if isinstance(model_id, str) and model_id.strip():
                                names.add(model_id.strip())
            except Exception:
                pass

        return sorted(names)

    @staticmethod
    def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"{role.upper()}: {content}")
        lines.append("ASSISTANT:")
        return "\n\n".join(lines)

    @staticmethod
    def _extract_error_text(response: httpx.Response) -> str:
        text = response.text.strip()
        try:
            payload = response.json()
            if isinstance(payload, dict):
                candidate = payload.get("error") or payload.get("message")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        except Exception:
            pass
        return text

    @staticmethod
    def _extract_error_text_from_raw(raw: bytes) -> str:
        text = raw.decode("utf-8", errors="ignore").strip()
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                candidate = payload.get("error") or payload.get("message")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        except Exception:
            pass
        return text

    @staticmethod
    def _is_model_not_found_error(detail: str) -> bool:
        lowered = detail.lower()
        if "model" in lowered and "not found" in lowered:
            return True
        return bool(re.search(r"pull|manifest|unknown model", lowered))

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
