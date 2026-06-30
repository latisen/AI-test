from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import httpx


class ComfyUIClient:
    def __init__(self, base_url: str, workflows_dir: str, output_dir: str, models_dir: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.workflows_dir = Path(workflows_dir)
        self.output_dir = output_dir
        self.models_dir = Path(models_dir)

    def _load_workflow(self, workflow_name: str) -> dict[str, Any]:
        path = self.workflows_dir / workflow_name
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_name}")
        return json.loads(path.read_text(encoding="utf-8"))

    async def queue_prompt(
        self,
        workflow_name: str,
        prompt_text: str,
        negative_prompt: str,
        seed: int | None = None,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        checkpoint: str | None = None,
    ) -> tuple[str, str]:
        workflow = self._load_workflow(workflow_name)

        if checkpoint and "4" in workflow:
            workflow["4"]["inputs"]["ckpt_name"] = checkpoint

        if "4" in workflow:
            ckpt_name = workflow["4"]["inputs"].get("ckpt_name")
            if ckpt_name:
                ckpt_path = self.models_dir / "checkpoints" / ckpt_name
                if not ckpt_path.exists():
                    raise FileNotFoundError(
                        f"Checkpoint not found: {ckpt_name}. Place it in {ckpt_path.parent} or choose another checkpoint."
                    )

        if "6" in workflow:
            workflow["6"]["inputs"]["text"] = prompt_text
        if "7" in workflow:
            workflow["7"]["inputs"]["text"] = negative_prompt
        if seed is not None and "3" in workflow:
            workflow["3"]["inputs"]["seed"] = seed
        if steps is not None and "3" in workflow:
            workflow["3"]["inputs"]["steps"] = steps
        if cfg is not None and "3" in workflow:
            workflow["3"]["inputs"]["cfg"] = cfg
        if width is not None and "5" in workflow:
            workflow["5"]["inputs"]["width"] = width
        if height is not None and "5" in workflow:
            workflow["5"]["inputs"]["height"] = height

        client_id = str(uuid.uuid4())
        payload = {
            "prompt": workflow,
            "client_id": client_id,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(f"{self.base_url}/prompt", json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip()[:1000]
                raise RuntimeError(
                    f"ComfyUI returned HTTP {exc.response.status_code} while queueing prompt: {detail}"
                ) from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Could not reach ComfyUI at {self.base_url}: {exc}") from exc

            data = response.json()
            prompt_id = data.get("prompt_id", "unknown")

        return prompt_id, self.output_dir
