# InstantID/IPAdapter Workflow Notes

This repository provides infrastructure only. To enable character consistency:

1. Install ComfyUI custom nodes in the ComfyUI container for InstantID and IPAdapter.
2. Place approved reference images in `reference_photos/<character_id>/`.
3. Duplicate `workflows/sdxl_character.json` into:
   - `workflows/sdxl_instantid.json`
   - `workflows/sdxl_ipadapter.json`
4. Add nodes for InstantID/IPAdapter and wire them into the base graph.
5. Keep adult-only safety filters in positive/negative prompts.

Never add workflows intended for minors, ambiguous ages, or non-consensual content.
