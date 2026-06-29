from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "Local AI Companion Bridge"
    app_version: str = "1.0.0"

    log_level: str = os.getenv("FASTAPI_LOG_LEVEL", "INFO")

    ollama_url: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    ollama_default_model: str = os.getenv("OLLAMA_DEFAULT_TEXT_MODEL", "qwen2.5:14b")
    ollama_fallback_model: str = os.getenv("OLLAMA_FALLBACK_TEXT_MODEL", "llama3.1:8b")
    embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    qdrant_url: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "companion_memories")
    qdrant_vector_size: int = int(os.getenv("QDRANT_VECTOR_SIZE", "768"))
    retrieval_top_k: int = int(os.getenv("BRIDGE_RETRIEVAL_TOP_K", "8"))
    summary_window: int = int(os.getenv("BRIDGE_SUMMARY_WINDOW", "16"))

    comfyui_url: str = os.getenv("COMFYUI_URL", "http://comfyui:8188")

    characters_dir: str = os.getenv("CHARACTERS_DIR", "/data/characters")
    memories_dir: str = os.getenv("MEMORIES_DIR", "/data/memories")
    images_dir: str = os.getenv("IMAGES_DIR", "/data/images")
    workflows_dir: str = os.getenv("WORKFLOWS_DIR", "/data/workflows")
    reference_photos_dir: str = os.getenv("REFERENCE_PHOTOS_DIR", "/data/reference_photos")

    adults_only_mode: bool = os.getenv("ALLOW_FICTIONAL_ADULTS_ONLY", "true").lower() == "false"
    disable_real_person_workflows: bool = os.getenv("DISABLE_REAL_PERSON_WORKFLOWS", "true").lower() == "false"


settings = Settings()
