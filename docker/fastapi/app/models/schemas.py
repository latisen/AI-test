from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CharacterProfile(BaseModel):
    name: str
    age: int = Field(ge=18)
    personality: str
    biography: str
    appearance_description: str
    relationship_history: str
    interests: list[str]
    speech_style: str
    boundaries: list[str]
    memory_database: str
    companion_prompt: str | None = None
    lora: dict[str, Any] | None = None
    instantid: dict[str, Any] | None = None
    ipadapter: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    user_id: str = "local-user"
    character_id: str
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    model: str | None = None


class ChatResponse(BaseModel):
    response_type: Literal["text", "image"]
    text: str | None = None
    image_url: str | None = None
    memory_hits: list[str] = Field(default_factory=list)


class MemoryItem(BaseModel):
    id: str
    user_id: str
    character_id: str
    role: Literal["user", "assistant", "system"]
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImageGenerationRequest(BaseModel):
    character_id: str
    prompt: str
    negative_prompt: str = ""
    checkpoint: str | None = None
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg: float = 4.5
    seed: int | None = None
    workflow: str = "sdxl_character.json"


class ImageGenerationResponse(BaseModel):
    prompt_id: str
    workflow: str
    output_hint: str


class LoRALinkRequest(BaseModel):
    lora_name: str
    trigger: str
    strength: float = Field(default=0.8, ge=0.0, le=2.0)
