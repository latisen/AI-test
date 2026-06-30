from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from slugify import slugify

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://fastapi-bridge:8080")
REFERENCE_DIR = Path(os.getenv("REFERENCE_PHOTOS_DIR", "/data/reference_photos"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", "/data/images"))
DEFAULT_USER_ID = os.getenv("UI_USER_ID", "local-user")



def api_get(path: str) -> dict[str, Any]:
    response = requests.get(f"{FASTAPI_URL}{path}", timeout=20)
    response.raise_for_status()
    return response.json()



def api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{FASTAPI_URL}{path}", json=payload, timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text
        try:
            parsed = response.json()
            detail = parsed.get("detail", detail)
        except ValueError:
            pass
        raise requests.HTTPError(f"{exc} :: {detail}") from exc
    return response.json()



def api_post_file(path: str, file_storage) -> dict[str, Any]:
    files = {"file": (file_storage.filename, file_storage.stream, file_storage.mimetype)}
    response = requests.post(f"{FASTAPI_URL}{path}", files=files, timeout=60)
    response.raise_for_status()
    return response.json()



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

    payload = {
        "user_id": DEFAULT_USER_ID,
        "character_id": character_id,
        "message": message,
        "history": history,
    }

    try:
        response = api_post("/chat", payload)
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

        result = api_post("/images", payload)
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
