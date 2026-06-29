from __future__ import annotations

from app.models.schemas import CharacterProfile


def build_system_prompt(character: CharacterProfile, memory_snippets: list[str]) -> str:
    memory_block = "\n".join(f"- {snippet}" for snippet in memory_snippets) if memory_snippets else "- None yet"
    boundaries = "\n".join(f"- {item}" for item in character.boundaries)

    return (
        "You are roleplaying as an adult fictional companion character.\n"
        f"Name: {character.name}\n"
        f"Age: {character.age}\n"
        f"Personality: {character.personality}\n"
        f"Biography: {character.biography}\n"
        f"Appearance: {character.appearance_description}\n"
        f"Relationship history: {character.relationship_history}\n"
        f"Interests: {', '.join(character.interests)}\n"
        f"Speech style: {character.speech_style}\n"
        "Boundaries (must never be violated):\n"
        f"{boundaries}\n"
        "Relevant long-term memory:\n"
        f"{memory_block}\n"
        "Safety rules: Never generate or support minors, age ambiguity, non-consent, exploitation, or unauthorized real-person content."
    )


def compose_image_prompt(character: CharacterProfile, user_prompt: str) -> str:
    tokens = [
        f"character portrait of {character.name}",
        f"adult age {character.age}",
        character.appearance_description,
        character.speech_style,
        user_prompt,
    ]
    if character.lora:
        trigger = character.lora.get("trigger", "")
        strength = character.lora.get("strength", 0.8)
        if trigger:
            tokens.append(f"<lora:{trigger}:{strength}>")
    return ", ".join(token for token in tokens if token)


def is_image_request(text: str) -> bool:
    triggers = ("draw", "image", "picture", "render", "portrait", "illustration", "generate")
    lowered = text.lower()
    return any(word in lowered for word in triggers)
