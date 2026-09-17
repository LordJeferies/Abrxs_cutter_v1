# ABRXOS Cutter 3.1.0 — CapCut Export

Date: 2026-09-17

## Added
- Three output modes: complete only, complete + individual sections, sections only.
- Default for new setups: complete + individual sections.
- Visible CapCut package per orientation under each content folder.
- `01_SECCIONES/` with human-readable ordered files.
- `02_COMPLETO/` when the selected mode includes a complete video.
- `ORDEN_CAPCUT.txt` and `SECCIONES.json` preserving editorial order and source timestamps.
- Backward-compatible behavior for legacy configs without `output_mode`: complete only.

## Preserved
- `sourceRanges` remain the only source-of-truth for physical cuts.
- Existing cache-part rendering and resume behavior remain authoritative.
- Existing final output path remains for modes that include a complete video.
- No changes to Geometra, Content Builder, Brand Builder, R6/R6.1 contracts, or persistent data.
