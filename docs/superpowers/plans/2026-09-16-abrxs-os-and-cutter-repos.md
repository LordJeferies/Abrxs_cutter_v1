# Abrxs OS + Cutter Repositories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current ABRXOS ecosystem safely publishable as `Abrxs_os_v1` and provide a separate reproducible `Abrxs_cutter_v1` repository that can capture the installed Cutter and reinstall its runtime dependencies from scratch on macOS.

**Architecture:** The OS repository remains the source of truth for Geometra + Content Builder + Brand Builder and never tracks machine-generated launchers or user data. The Cutter repository is independent: it captures the current installed Cutter source into `apps/cutter/current`, infers runtime requirements, records an entrypoint/version manifest, and provides dependency/install/verify/rollback tools without embedding user media or outputs.

**Tech Stack:** zsh, Python 3 stdlib, rsync, Git/GitHub CLI, Homebrew optional bootstrap, FFmpeg/ffprobe, Python venv/pip, macOS osacompile/osascript.

**Spec:** Approved in conversation on 2026-09-16: repo name `Abrxs_os_v1`, separate Cutter repo, reinstall-from-zero workflow, framework/model installer, reversible/non-destructive tooling.

## Global Constraints

- Never delete or move user data directories.
- Never run `git add .` against `$HOME` or a parent repository.
- Never delete `$HOME/.git`; nested repo initialization is sufficient.
- Machine-specific launchers are generated artifacts and are excluded from source snapshots.
- Cutter media/output/cache folders are never captured into Git.
- Required heavy models are installed only when declared/detected; no speculative model downloads.
- FFmpeg and ffprobe are required Cutter runtime dependencies.
- Apple Silicon hardware encoder check (`h264_videotoolbox`) is part of preflight.

---

### Task 1: Harden Abrxs_os_v1 repository tooling

**Files:**
- Create: `ABRXS_OS_V1_REPO_FIX/APLICAR_FIX_REPO.command`
- Create: `ABRXS_OS_V1_REPO_FIX/VERIFICAR_FIX_REPO.command`
- Test: `ABRXS_OS_V1_REPO_FIX/tests/test_repo_fix.py`

**Interfaces:**
- Consumes: existing `ABRXOS_ECOSYSTEM_V3_1_1_R6_1_GITHUB_REPO_FIXED` directory.
- Produces: a nested Git repository rooted exactly at that directory, source snapshot without generated launchers, GitHub next steps naming `Abrxs_os_v1`.

- [ ] Write failing tests for launcher exclusion and root-local git initialization.
- [ ] Run tests and verify RED.
- [ ] Implement minimal tooling patch.
- [ ] Run tests GREEN.

### Task 2: Build Cutter repository capture and runtime contract

**Files:**
- Create: `Abrxs_cutter_v1_GITHUB_REPO_STARTER/tools/capture_cutter.py`
- Create: `tools/CAPTURAR_CUTTER_ACTUAL.command`
- Create: `tools/VERIFY_ALL.command`
- Create: `tools/PREPARAR_REPO_GITHUB.command`
- Create: `CURRENT_CUTTER.json`
- Create: `requirements-runtime.txt`
- Create: `models/MODELS_MANIFEST.json`
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: candidate installs under `~/ABRXOS_CUTTER_APP`, `~/ABRXOS_MULTI_CUTTER`, and optional standalone Cutter scripts.
- Produces: `apps/cutter/current`, `CURRENT_CUTTER.json`, inferred Python requirements and detected model references.

- [ ] Write failing tests for candidate selection, entrypoint detection, import inference, path sanitization.
- [ ] Verify RED.
- [ ] Implement capture helper and shell wrapper.
- [ ] Verify GREEN.

### Task 3: Cutter dependency/model bootstrap and reinstall-from-zero

**Files:**
- Create: `install/INSTALAR_DEPENDENCIAS_MAC.command`
- Create: `install/INSTALAR_MODELOS.command`
- Create: `install/INSTALAR_CUTTER_DESDE_CERO.command`
- Create: `tools/PREFLIGHT.command`
- Test: `tests/test_install_contract.py`

**Interfaces:**
- Runtime destination: `~/ABRXOS_CUTTER_APP`.
- Desktop launcher: `~/Desktop/ABRXOS Cutter.app` when osacompile is available, otherwise `.command` fallback.
- Runtime venv: `~/.abrxos/cutter/venv`.

- [ ] Write failing tests for dry-run dependency plan and install contract.
- [ ] Verify RED.
- [ ] Implement Homebrew/Python/FFmpeg/venv/model logic.
- [ ] Verify GREEN.

### Task 4: Documentation, manifests and package verification

**Files:**
- Create: `README.md`, `START_HERE.txt`, docs/tutorials, `.gitignore`, `REPO_MANIFEST.json`, `MANIFEST_SHA256.txt`.
- Test: full pytest + shell syntax + zip integrity.

- [ ] Add operational documentation and GitHub instructions for `Abrxs_cutter_v1`.
- [ ] Run complete tests.
- [ ] Verify shell syntax and JSON parse.
- [ ] Build ZIPs and verify with `unzip -t`.
