# Local AI Companion Stack (Windows 11 + Docker + WSL2)

This repository provides a complete local AI companion infrastructure stack designed for Windows 11 Pro with:

- 12 CPU cores
- 64 GB RAM
- NVIDIA RTX 4070 (12 GB VRAM)
- 2 TB SSD

It includes:

- Persistent web chat UI via Open WebUI
- LLM backend via Ollama
- Long-term memory via Qdrant
- Character profile system with JSON storage
- FastAPI middleware bridge for chat/memory/image orchestration
- ComfyUI for local image generation
- Character consistency hooks for LoRA, InstantID, and IPAdapter workflows
- Backup and restore scripts
- One-command Windows installer (`install.ps1`)

## Safety and Scope

This stack is infrastructure-only and enforces policy boundaries:

- Only fictional adult characters or adults with explicit rights and consent.
- No minors or age ambiguity.
- No non-consensual or exploitative content.
- No real-person exploitation workflows.

Guardrails are enforced in the bridge service (`safety.py`) and reflected in default prompting and negative prompts.

## Exposed Services

After install/startup:

- Open WebUI: http://localhost:3000
- ComfyUI: http://localhost:8188
- Qdrant: http://localhost:6333
- FastAPI: http://localhost:8080 (docs: http://localhost:8080/docs)
- Ollama API: http://localhost:11434

## Repository Layout

The installer syncs this project to `C:\AICompanion` and ensures this structure:

```text
C:\AICompanion\
├── characters\
├── memories\
├── images\
├── models\
│   └── ollama\
├── loras\
├── workflows\
├── qdrant\
├── logs\
├── backups\
├── reference_photos\
├── docker\
├── tools\
├── docker-compose.yml
├── .env
└── install.ps1
```

## Core Components

### Frontend

- Open WebUI container (`open-webui` service).

### LLM Backend

- Ollama container (`ollama` service).
- Default models:
	- `qwen2.5:14b`
	- `llama3.1:8b`
- Embeddings model:
	- `nomic-embed-text`

### Memory

- Qdrant vector DB (`qdrant` service).
- FastAPI bridge stores/retrieves user+character scoped memories.

### Image Generation

- ComfyUI container (`comfyui` service).
- SDXL workflow template included (`workflows/sdxl_character.json`).
- Optional Flux can be added by installing Flux models/workflows in `workflows` and `models`.

### Middleware

- FastAPI bridge (`fastapi-bridge` service).
- Responsibilities:
	- Receives chat requests
	- Loads character profiles
	- Retrieves long-term memories from Qdrant
	- Builds augmented prompts
	- Calls Ollama for text
	- Detects image intent and queues ComfyUI jobs
	- Writes chat/image events back into memory

## Windows Installation

Open elevated PowerShell and run:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

### What the Installer Does

- Verifies Administrator privileges
- Installs required tools (winget-based):
	- Git
	- Python 3.12
	- Docker Desktop
	- Ollama
	- Ubuntu 24.04 (WSL)
- Checks WSL2 and enables required Windows features
- Validates NVIDIA GPU + CUDA via `nvidia-smi`
- Attempts NVIDIA Container Toolkit setup inside Ubuntu WSL
- Creates full folder structure under `C:\AICompanion`
- Syncs repository files into install root
- Creates `.env` from `.env.example`
- Pulls and starts Docker services
- Pulls default Ollama models
- Creates desktop URL shortcuts

If WSL or virtualization features were newly enabled, reboot once for full GPU container support.

## Manual Start/Stop

From `C:\AICompanion`:

```powershell
docker compose up -d --build
docker compose ps
```

Stop:

```powershell
docker compose down
```

## Environment Configuration

Copy and edit `.env`:

```powershell
Copy-Item .env.example .env
```

Main settings:

- Models, ports, and service URLs
- Safety toggles
- Data mount paths
- Retrieval and summarization window sizes

## Character Framework

Characters are JSON files in `characters/`.

Each profile includes:

- name
- age
- personality
- biography
- appearance_description
- relationship_history
- interests
- speech_style
- boundaries
- memory_database
- optional lora/instantid/ipadapter blocks

Sample profile: `characters/sample_companion.json`

### API Endpoints

- `GET /characters`
- `GET /characters/{character_id}`
- `POST /characters/{character_id}`
- `POST /characters/{character_id}/link-lora`
- `POST /characters/{character_id}/references` (file upload)

## Memory System

Qdrant collection is created automatically on first bridge request.

Memory pipeline:

1. User message is embedded (Ollama embeddings with deterministic fallback)
2. Message stored in Qdrant with user+character metadata
3. Relevant memories retrieved for future prompts
4. Assistant response is stored as another memory item

## Chat and Image Orchestration

Bridge endpoint:

- `POST /chat`

Behavior:

- Detects image-intent keywords (`draw`, `image`, `portrait`, etc.)
- Text requests go to Ollama with memory-augmented system prompt
- Image requests queue ComfyUI workflow (`sdxl_character.json`)
- Returns either text response or image-queue response

Direct image endpoint:

- `POST /images`

## LoRA / InstantID / IPAdapter Workflow

### Reference Photo Flow

1. Create or update character profile (`POST /characters/{character_id}`)
2. Upload approved reference photos (`POST /characters/{character_id}/references`)
3. Prepare LoRA dataset metadata with:

```powershell
python .\tools\prepare_lora_dataset.py --character-id aria_vale --character-file .\characters\sample_companion.json --reference-dir .\reference_photos\aria_vale --output-dir .\loras\datasets
```

4. Train LoRA with your preferred trainer (outside this repo)
5. Place resulting LoRA in `loras/`
6. Link LoRA metadata:

```http
POST /characters/aria_vale/link-lora
{
	"lora_name": "aria_vale_v1.safetensors",
	"trigger": "ariaValeStyle",
	"strength": 0.8
}
```

7. Future image prompts automatically include LoRA trigger syntax

### InstantID/IPAdapter

- Implementation notes are in `workflows/instantid_ipadapter_notes.md`
- Add custom nodes and clone SDXL workflow for:
	- `workflows/sdxl_instantid.json`
	- `workflows/sdxl_ipadapter.json`

## Backups and Restore

Backup (PowerShell):

```powershell
.\tools\backup.ps1
```

Backup (WSL/Linux):

```bash
bash ./docker/scripts/backup.sh
```

Restore:

```powershell
.\tools\restore.ps1 -BackupZip .\backups\backup_YYYYMMDD_HHMMSS.zip
```

## Open WebUI Integration Notes

You can connect Open WebUI directly to Ollama for baseline chat and optionally call the bridge API from custom tools/actions.

Recommended bridge endpoint for companion flow:

- `POST http://localhost:8080/chat`

## Validation Checklist

After startup:

1. `docker compose ps` shows all services healthy/running
2. Open WebUI reachable at `http://localhost:3000`
3. ComfyUI reachable at `http://localhost:8188`
4. Qdrant dashboard endpoint reachable at `http://localhost:6333`
5. FastAPI docs reachable at `http://localhost:8080/docs`
6. `ollama list` includes required models

## Notes

- This project does not include copyrighted model weights.
- You provide legally obtained models/checkpoints/LoRAs in local folders.
- Keep all generated and source assets compliant with law, consent, and age-safety requirements.