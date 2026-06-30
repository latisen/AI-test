from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

import requests
from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from slugify import slugify

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://fastapi-bridge:8080")
LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", os.getenv("OLLAMA_URL", "http://host.docker.internal:1234/v1")).rstrip("/")
REFERENCE_DIR = Path(os.getenv("REFERENCE_PHOTOS_DIR", "/data/reference_photos"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", "/data/images"))
DEFAULT_USER_ID = os.getenv("UI_USER_ID", "local-user")
DEFAULT_CHAT_MODEL = os.getenv("LMSTUDIO_DEFAULT_TEXT_MODEL", os.getenv("OLLAMA_DEFAULT_TEXT_MODEL", ""))
FALLBACK_CHAT_MODEL = os.getenv("LMSTUDIO_FALLBACK_TEXT_MODEL", os.getenv("OLLAMA_FALLBACK_TEXT_MODEL", ""))
EXTRA_CHAT_MODELS = [m.strip() for m in os.getenv("LMSTUDIO_EXTRA_MODELS", os.getenv("OLLAMA_EXTRA_MODELS", "")).split(",") if m.strip()]
CHAT_TIMEOUT_SECONDS = int(os.getenv("CHAT_TIMEOUT_SECONDS", "240"))



def api_get(path: str) -> dict[str, Any]:
    response = requests.get(f"{FASTAPI_URL}{path}", timeout=20)
    response.raise_for_status()
    return response.json()



def api_post(path: str, payload: dict[str, Any], timeout_seconds: int = 30) -> dict[str, Any]:
    response = requests.post(f"{FASTAPI_URL}{path}", json=payload, timeout=timeout_seconds)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text or "(empty response body)"
        try:
            parsed = response.json()
            detail = parsed.get("detail", detail)
            if isinstance(parsed, dict) and parsed.get("traceback"):
                detail = f"{detail} | traceback: {parsed.get('traceback')}"
        except ValueError:
            pass
        raise requests.HTTPError(
            f"{exc} :: status={response.status_code} content-type={response.headers.get('content-type', '')} body={detail}"
        ) from exc
    return response.json()



def api_post_file(path: str, file_storage) -> dict[str, Any]:
    files = {"file": (file_storage.filename, file_storage.stream, file_storage.mimetype)}
    response = requests.post(f"{FASTAPI_URL}{path}", files=files, timeout=60)
    response.raise_for_status()
    return response.json()


def lmstudio_get(path: str) -> dict[str, Any]:
    response = requests.get(f"{LMSTUDIO_URL}{path}", timeout=20)
    response.raise_for_status()
    return response.json()


def list_lmstudio_models() -> list[str]:
    names: set[str] = set()
    try:
        payload = lmstudio_get("/v1/models")
    except requests.RequestException:
        return []

    for item in payload.get("data", []):
        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.strip():
                names.add(model_id.strip())

    return sorted(names)


def build_chat_messages(character: dict[str, Any], memory_hits: list[str], history: list[dict[str, str]], message: str) -> list[dict[str, str]]:
    personality = character.get("personality", "")
    biography = character.get("biography", "")
    appearance = character.get("appearance_description", "")
    relationship_history = character.get("relationship_history", "")
    interests = ", ".join(character.get("interests", []))
    speech_style = character.get("speech_style", "")
    boundaries = "\n".join(f"- {item}" for item in character.get("boundaries", []))
    memory_block = "\n".join(f"- {snippet}" for snippet in memory_hits) if memory_hits else "- None yet"

    system_prompt = (
        "You are roleplaying as an adult fictional companion character.\n"
        f"Name: {character.get('name', 'Companion')}\n"
        f"Age: {character.get('age', 'unknown')}\n"
        f"Personality: {personality}\n"
        f"Biography: {biography}\n"
        f"Appearance: {appearance}\n"
        f"Relationship history: {relationship_history}\n"
        f"Interests: {interests}\n"
        f"Speech style: {speech_style}\n"
        "Boundaries (must never be violated):\n"
        f"{boundaries}\n"
        "Relevant long-term memory:\n"
        f"{memory_block}\n"
        "Safety rules: Never generate or support minors, age ambiguity, non-consent, exploitation, or unauthorized real-person content."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": message})
    return messages


def stream_lmstudio_chat(model: str, messages: list[dict[str, str]]):
    payload = {"model": model, "messages": messages, "stream": True}
    with requests.post(
        f"{LMSTUDIO_URL}/chat/completions",
        json=payload,
        stream=True,
        timeout=(15, CHAT_TIMEOUT_SECONDS),
    ) as response:
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason or "LM Studio request failed"
            yield f"[ERROR] {detail}"
            return

        yield "\n"
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_text = line[5:].strip()
            if data_text == "[DONE]":
                continue
            try:
                data = json.loads(data_text)
            except Exception:
                continue
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    delta = first_choice.get("delta") or first_choice.get("message") or {}
                    if isinstance(delta, dict):
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            yield content



def list_companions() -> list[dict[str, Any]]:
    companion_ids = api_get("/characters").get("characters", [])
    companions: list[dict[str, Any]] = []
    for character_id in companion_ids:
        try:
            profile = api_get(f"/characters/{character_id}")
        except requests.RequestException:
            continue

        avatar_url = None
        avatar_dir = REFERENCE_DIR / character_id
        if avatar_dir.exists():
            files = sorted(
                [p for p in avatar_dir.iterdir() if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if files:
                avatar_url = url_for("static_avatar", character_id=character_id, filename=files[0].name)

        companions.append(
            {
                "character_id": character_id,
                "name": profile.get("name", character_id),
                "age": profile.get("age", "?"),
                "interests": profile.get("interests", []),
                "nationality": profile.get("nationality", "Unknown"),
                "avatar_url": avatar_url,
            }
        )

    companions.sort(key=lambda c: c["name"].lower())
    return companions



def build_profile(form: dict[str, str]) -> dict[str, Any]:
    interests = [item.strip() for item in form.get("interests", "").split(",") if item.strip()]
    boundaries = [
        "Only consensual adult interactions",
        "No minors or age ambiguity",
        "No coercive or exploitative scenarios",
    ]

    nationality = form.get("nationality", "")
    biography = form.get("biography", "")
    if nationality:
        biography = f"{biography} Nationality: {nationality}.".strip()

    profile = {
        "name": form.get("name", "").strip(),
        "age": int(form.get("age", "18")),
        "personality": form.get("personality", "Confident and warm."),
        "biography": biography or "A fictional adult companion.",
        "appearance_description": form.get("appearance_description", "Adult character portrait."),
        "relationship_history": form.get("relationship_history", "Prefers clear communication and consent."),
        "interests": interests,
        "speech_style": form.get("speech_style", "Playful, empathetic, and direct."),
        "boundaries": boundaries,
        "memory_database": f"{slugify(form.get('name', 'companion'))}-memory",
        "instantid": {
            "enabled": True,
            "reference_folder": f"reference_photos/{slugify(form.get('name', 'companion'))}",
        },
        "ipadapter": {
            "enabled": True,
            "reference_folder": f"reference_photos/{slugify(form.get('name', 'companion'))}",
        },
    }
    return profile


def _clean(value: str | None) -> str:
    return (value or "").strip()


def build_image_prompt_from_form(form: dict[str, str]) -> str:
    scene = _clean(form.get("scene"))
    pose = _clean(form.get("pose"))
    outfit = _clean(form.get("outfit"))
    mood = _clean(form.get("mood"))
    lighting = _clean(form.get("lighting"))
    style = _clean(form.get("style"))
    camera_angle = _clean(form.get("camera_angle"))
    framing = _clean(form.get("framing"))
    hair_color = _clean(form.get("hair_color"))
    hair_length = _clean(form.get("hair_length"))
    hair_texture = _clean(form.get("hair_texture"))
    body_type = _clean(form.get("body_type"))
    height_type = _clean(form.get("height_type"))
    extra_details = _clean(form.get("extra_details"))

    tokens = [
        "high quality portrait",
        "adult fictional character",
    ]

    for value in (
        scene,
        pose,
        outfit,
        mood,
        lighting,
        style,
        camera_angle,
        framing,
    ):
        if value:
            tokens.append(value)

    look_tokens = []
    if hair_color:
        look_tokens.append(f"hair color: {hair_color}")
    if hair_length:
        look_tokens.append(f"hair length: {hair_length}")
    if hair_texture:
        look_tokens.append(f"hair texture: {hair_texture}")
    if body_type:
        look_tokens.append(f"body build: {body_type}")
    if height_type:
        look_tokens.append(f"height profile: {height_type}")
    if look_tokens:
        tokens.append(", ".join(look_tokens))

    if extra_details:
        tokens.append(extra_details)

    return ", ".join(tokens)


def list_recent_generated_images(limit: int = 30) -> list[dict[str, str]]:
    if not IMAGES_DIR.exists():
        return []

    files = [
        p
        for p in IMAGES_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    images: list[dict[str, str]] = []
    for item in files[:limit]:
        rel = item.relative_to(IMAGES_DIR).as_posix()
        images.append({"filename": item.name, "relpath": rel})
    return images


@app.route("/api/lmstudio/test")
@app.route("/api/ollama/test")
def lmstudio_test():
    prompt = _clean(request.args.get("prompt")) or "Säg hej på svenska i en enda kort mening."
    model = _clean(request.args.get("model")) or session.get("chat_model") or DEFAULT_CHAT_MODEL
    if model:
        session["chat_model"] = model

    messages = [
        {"role": "system", "content": "You are a concise assistant. Reply with one short sentence only."},
        {"role": "user", "content": prompt},
    ]

    chunks: list[str] = []
    try:
        for chunk in stream_lmstudio_chat(model, messages):
            if chunk.startswith("[ERROR]"):
                return Response(chunk, status=502, mimetype="text/plain; charset=utf-8")
            chunks.append(chunk)
    except requests.RequestException as exc:
        return Response(f"[ERROR] {exc}", status=502, mimetype="text/plain; charset=utf-8")

    text = "".join(chunks).strip() or "(no response)"
    return Response(text, mimetype="text/plain; charset=utf-8")



@app.route("/")
def index():
    companions = list_companions()
    active_id = request.args.get("character_id")
    if not active_id and companions:
        active_id = companions[0]["character_id"]

    active_profile = None
    chat_history = []
    last_image = None
    image_status = None
    available_models: list[str] = []
    selected_model = session.get("chat_model")
    model_warning = None
    recent_images = list_recent_generated_images()

    try:
        available_models = list_lmstudio_models()
        if not selected_model:
            selected_model = available_models[0] if available_models else DEFAULT_CHAT_MODEL
    except requests.RequestException:
        model_warning = "Kunde inte hämta modellistan direkt från LM Studio. Visar lokal fallback-lista."

    fallback_models = [DEFAULT_CHAT_MODEL, FALLBACK_CHAT_MODEL, *EXTRA_CHAT_MODELS]
    if selected_model:
        fallback_models.append(selected_model)

    merged_models: list[str] = []
    for model_name in [*available_models, *fallback_models]:
        if model_name and model_name not in merged_models:
            merged_models.append(model_name)

    available_models = merged_models
    if not selected_model and available_models:
        selected_model = available_models[0]
    if active_id:
        try:
            active_profile = api_get(f"/characters/{active_id}")
            chat_history = session.get(f"chat::{active_id}", [])
            last_image = session.get(f"image::{active_id}")
            if last_image and last_image.get("prompt_id"):
                image_status = api_get(f"/images/{last_image['prompt_id']}/status")
        except requests.RequestException as exc:
            flash(f"Could not load companion: {exc}", "error")

    return render_template(
        "index.html",
        companions=companions,
        active_id=active_id,
        active_profile=active_profile,
        chat_history=chat_history,
        last_image=last_image,
        image_status=image_status,
        recent_images=recent_images,
        available_models=available_models,
        selected_model=selected_model,
        model_warning=model_warning,
    )


@app.route("/companions/new", methods=["GET", "POST"])
def create_companion():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            if not name:
                raise ValueError("Name is required.")

            age = int(request.form.get("age", "18"))
            if age < 18:
                raise ValueError("Companion age must be 18 or older.")

            character_id = slugify(name)
            profile = build_profile(request.form)
            api_post(f"/characters/{character_id}", profile)

            avatar = request.files.get("avatar")
            if avatar and avatar.filename:
                api_post_file(f"/characters/{character_id}/references", avatar)

            flash(f"Companion '{name}' created.", "success")
            return redirect(url_for("index", character_id=character_id))
        except (ValueError, requests.RequestException) as exc:
            flash(str(exc), "error")

    return render_template("new_companion.html")


@app.route("/chat/<character_id>", methods=["POST"])
def chat(character_id: str):
    message = request.form.get("message", "").strip()
    if not message:
        return redirect(url_for("index", character_id=character_id))

    history_key = f"chat::{character_id}"
    history = session.get(history_key, [])

    selected_model = _clean(request.form.get("custom_model")) or _clean(request.form.get("model"))

    payload = {
        "user_id": DEFAULT_USER_ID,
        "character_id": character_id,
        "message": message,
        "history": history,
        "model": selected_model or None,
    }

    if selected_model:
        session["chat_model"] = selected_model

    try:
        # First response from larger models can take a while.
        response = api_post("/chat", payload, timeout_seconds=CHAT_TIMEOUT_SECONDS)
        assistant_text = response.get("text") or response.get("image_url") or "No response"

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": assistant_text})
        session[history_key] = history[-20:]
    except requests.RequestException as exc:
        flash(f"Chat failed: {exc}", "error")

    return redirect(url_for("index", character_id=character_id))


@app.route("/images/<character_id>", methods=["POST"])
def generate_image(character_id: str):
    try:
        prompt = build_image_prompt_from_form(request.form)
        negative_prompt = _clean(request.form.get("negative_prompt"))

        payload = {
            "character_id": character_id,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "checkpoint": _clean(request.form.get("checkpoint")) or None,
            "width": int(request.form.get("width", "1024")),
            "height": int(request.form.get("height", "1024")),
            "steps": int(request.form.get("steps", "30")),
            "cfg": float(request.form.get("cfg", "4.5")),
            "seed": int(request.form["seed"]) if _clean(request.form.get("seed")) else None,
            "workflow": _clean(request.form.get("workflow")) or "sdxl_character.json",
        }

        result = api_post("/images", payload, timeout_seconds=90)
        session[f"image::{character_id}"] = result
        flash(
            f"Bildjobb köat. prompt_id: {result.get('prompt_id', 'n/a')}",
            "success",
        )
    except (ValueError, requests.RequestException) as exc:
        flash(f"Bildgenerering misslyckades: {exc}", "error")

    return redirect(url_for("index", character_id=character_id))


@app.route("/media/reference/<character_id>/<filename>")
def static_avatar(character_id: str, filename: str):
    target_dir = REFERENCE_DIR / character_id
    if not target_dir.exists():
        abort(404)
    return send_from_directory(target_dir, filename)


@app.route("/media/generated/<path:filename>")
def generated_image(filename: str):
    return send_from_directory(IMAGES_DIR, filename)


@app.route("/api/chat/stream/<character_id>", methods=["POST"])
def chat_stream_proxy(character_id: str):
    payload_in = request.get_json(silent=True) or {}
    message = _clean(payload_in.get("message"))
    if not message:
        return Response("Message is required.", status=400, mimetype="text/plain")

    model = _clean(payload_in.get("model")) or session.get("chat_model") or DEFAULT_CHAT_MODEL
    if model:
        session["chat_model"] = model

    history_key = f"chat::{character_id}"
    history = session.get(history_key, [])

    try:
        character = api_get(f"/characters/{character_id}")
    except requests.RequestException as exc:
        return Response(f"[ERROR] Could not load companion profile: {exc}", status=502, mimetype="text/plain")

    memory_hits: list[str] = []
    messages = build_chat_messages(character, memory_hits, history, message)

    def generate():
        try:
            for chunk in stream_lmstudio_chat(model, messages):
                if chunk.startswith("[ERROR]"):
                    yield chunk
                    return
                yield chunk
        except requests.RequestException as exc:
            yield f"[ERROR] {exc}"
        except Exception as exc:
            yield f"[ERROR] {exc}"

    return Response(generate(), mimetype="text/plain; charset=utf-8")


@app.route("/api/chat/store/<character_id>", methods=["POST"])
def chat_store(character_id: str):
    payload = request.get_json(silent=True) or {}
    user_text = _clean(payload.get("user"))
    assistant_text = _clean(payload.get("assistant"))
    if not user_text:
        return {"status": "ignored"}, 200

    history_key = f"chat::{character_id}"
    history = session.get(history_key, [])
    history.append({"role": "user", "content": user_text})
    if assistant_text:
        history.append({"role": "assistant", "content": assistant_text})
    session[history_key] = history[-30:]
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
