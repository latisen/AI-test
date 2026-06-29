from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import CharacterProfile
from app.modules.safety import assert_adult_age, assert_safe_text


class CharacterManager:
    def __init__(self, characters_dir: str) -> None:
        self.characters_dir = Path(characters_dir)
        self.characters_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, character_id: str) -> Path:
        return self.characters_dir / f"{character_id}.json"

    def list_characters(self) -> list[str]:
        return sorted(path.stem for path in self.characters_dir.glob("*.json"))

    def load_character(self, character_id: str) -> CharacterProfile:
        path = self._path_for(character_id)
        if not path.exists():
            raise FileNotFoundError(f"Character profile not found: {character_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return CharacterProfile(**data)

    def save_character(self, character_id: str, profile: CharacterProfile) -> CharacterProfile:
        assert_adult_age(profile.age)
        for field in (
            profile.personality,
            profile.biography,
            profile.appearance_description,
            profile.relationship_history,
            profile.speech_style,
            " ".join(profile.boundaries),
        ):
            assert_safe_text(field)

        path = self._path_for(character_id)
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        return profile

    def link_lora(
        self,
        character_id: str,
        lora_name: str,
        trigger: str,
        strength: float = 0.8,
    ) -> CharacterProfile:
        profile = self.load_character(character_id)
        profile.lora = {
            "name": lora_name,
            "trigger": trigger,
            "strength": strength,
        }
        return self.save_character(character_id, profile)
