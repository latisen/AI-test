from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import settings
from app.models.schemas import (
    CharacterProfile,
    ChatRequest,
    ChatResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    LoRALinkRequest,
)
from app.modules.character_manager import CharacterManager
from app.modules.comfyui_client import ComfyUIClient
from app.modules.memory_manager import MemoryManager
from app.modules.ollama_client import OllamaClient
from app.modules.prompt_builder import build_system_prompt, compose_image_prompt, is_image_request
from app.modules.safety import assert_safe_text

router = APIRouter()


def get_character_manager() -> CharacterManager:
    return CharacterManager(settings.characters_dir)


def get_ollama_client() -> OllamaClient:
    return OllamaClient(settings.ollama_url)


def get_memory_manager(ollama: OllamaClient = Depends(get_ollama_client)) -> MemoryManager:
    manager = MemoryManager(settings.qdrant_url, settings.qdrant_collection, ollama)
    manager.ensure_collection()
    return manager


def get_comfyui_client() -> ComfyUIClient:
    return ComfyUIClient(settings.comfyui_url, settings.workflows_dir, settings.images_dir)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/characters")
async def list_characters(cm: CharacterManager = Depends(get_character_manager)) -> dict[str, list[str]]:
    return {"characters": cm.list_characters()}


@router.get("/characters/{character_id}", response_model=CharacterProfile)
async def get_character(character_id: str, cm: CharacterManager = Depends(get_character_manager)) -> CharacterProfile:
    try:
        return cm.load_character(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/characters/{character_id}", response_model=CharacterProfile)
async def upsert_character(
    character_id: str,
    profile: CharacterProfile,
    cm: CharacterManager = Depends(get_character_manager),
) -> CharacterProfile:
    try:
        return cm.save_character(character_id, profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/characters/{character_id}/link-lora", response_model=CharacterProfile)
async def link_lora(
    character_id: str,
    request: LoRALinkRequest,
    cm: CharacterManager = Depends(get_character_manager),
) -> CharacterProfile:
    try:
        return cm.link_lora(
            character_id=character_id,
            lora_name=request.lora_name,
            trigger=request.trigger,
            strength=request.strength,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/characters/{character_id}/references")
async def upload_reference_photo(
    character_id: str,
    file: UploadFile = File(...),
    cm: CharacterManager = Depends(get_character_manager),
) -> dict[str, str]:
    try:
        cm.load_character(character_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    char_dir = Path(settings.reference_photos_dir) / character_id
    char_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "reference.jpg").suffix or ".jpg"
    target = char_dir / f"ref_{len(list(char_dir.glob('*')))+1:03d}{suffix}"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    target.write_bytes(data)
    return {"status": "stored", "path": str(target)}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    cm: CharacterManager = Depends(get_character_manager),
    mm: MemoryManager = Depends(get_memory_manager),
    ollama: OllamaClient = Depends(get_ollama_client),
    comfy: ComfyUIClient = Depends(get_comfyui_client),
) -> ChatResponse:
    try:
        assert_safe_text(request.message)
        character = cm.load_character(request.character_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    memory_hits = await mm.retrieve_relevant_memories(
        user_id=request.user_id,
        character_id=request.character_id,
        query_text=request.message,
        top_k=settings.retrieval_top_k,
    )

    if is_image_request(request.message):
        prompt = compose_image_prompt(character, request.message)
        prompt_id, output_hint = await comfy.queue_prompt(
            workflow_name="sdxl_character.json",
            prompt_text=prompt,
            negative_prompt=(
                "minor, child, underage, teen, non-consensual, real person, celebrity, low quality, blurry"
            ),
        )
        await mm.write_memory(request.user_id, request.character_id, "user", request.message)
        await mm.write_memory(
            request.user_id,
            request.character_id,
            "assistant",
            f"Queued image request {prompt_id} with workflow sdxl_character.json",
            metadata={"response_type": "image", "prompt_id": prompt_id},
        )
        return ChatResponse(
            response_type="image",
            text="Image request queued in ComfyUI.",
            image_url=f"{output_hint}/(watch ComfyUI history for prompt_id: {prompt_id})",
            memory_hits=memory_hits,
        )

    system_prompt = build_system_prompt(character, memory_hits)
    messages = [{"role": "system", "content": system_prompt}]
    if request.history:
        messages.extend(request.history[-settings.summary_window :])
    messages.append({"role": "user", "content": request.message})

    model = request.model or settings.ollama_default_model
    try:
        assistant_reply = await ollama.chat(model, messages)
    except Exception:
        assistant_reply = await ollama.chat(settings.ollama_fallback_model, messages)

    await mm.write_memory(request.user_id, request.character_id, "user", request.message)
    await mm.write_memory(request.user_id, request.character_id, "assistant", assistant_reply)

    return ChatResponse(response_type="text", text=assistant_reply, memory_hits=memory_hits)


@router.post("/images", response_model=ImageGenerationResponse)
async def create_image(
    request: ImageGenerationRequest,
    cm: CharacterManager = Depends(get_character_manager),
    comfy: ComfyUIClient = Depends(get_comfyui_client),
) -> ImageGenerationResponse:
    try:
        character = cm.load_character(request.character_id)
        assert_safe_text(request.prompt)
        assert_safe_text(request.negative_prompt)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prompt = compose_image_prompt(character, request.prompt)
    try:
        prompt_id, output_hint = await comfy.queue_prompt(
            workflow_name=request.workflow,
            prompt_text=prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg=request.cfg,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ImageGenerationResponse(prompt_id=prompt_id, workflow=request.workflow, output_hint=output_hint)
