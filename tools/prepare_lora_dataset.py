from __future__ import annotations

import argparse
import json
from pathlib import Path


def collect_images(folder: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted([p for p in folder.rglob("*") if p.suffix.lower() in exts])


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a LoRA dataset metadata bundle for a character.")
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--character-file", required=True, help="Path to character JSON profile.")
    parser.add_argument("--reference-dir", required=True, help="Path to approved reference photos.")
    parser.add_argument("--output-dir", required=True, help="Output directory for training metadata and captions.")
    parser.add_argument("--default-caption", default="adult character portrait")
    args = parser.parse_args()

    character_path = Path(args.character_file)
    reference_dir = Path(args.reference_dir)
    output_dir = Path(args.output_dir)

    profile = json.loads(character_path.read_text(encoding="utf-8"))
    age = int(profile.get("age", 0))
    if age < 18:
        raise ValueError("Character age must be 18+ for this stack.")

    images = collect_images(reference_dir)
    if not images:
        raise ValueError("No reference images found.")

    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir = output_dir / args.character_id
    dataset_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "character_id": args.character_id,
        "character_name": profile.get("name"),
        "age": age,
        "lora_trigger": profile.get("lora", {}).get("trigger", ""),
        "source_images": [],
    }

    for index, image_path in enumerate(images, start=1):
        target_image = dataset_dir / f"{args.character_id}_{index:04d}{image_path.suffix.lower()}"
        caption_path = dataset_dir / f"{args.character_id}_{index:04d}.txt"

        target_image.write_bytes(image_path.read_bytes())
        caption = f"{args.default_caption}, {profile.get('appearance_description', '')}".strip(", ")
        caption_path.write_text(caption + "\n", encoding="utf-8")

        manifest["source_images"].append(
            {
                "original": str(image_path),
                "dataset_image": str(target_image),
                "caption": caption,
            }
        )

    manifest_path = dataset_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Prepared {len(images)} images in {dataset_dir}")


if __name__ == "__main__":
    main()
