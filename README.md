# Abrxs_cutter_v1

Repositorio reproducible del **ABRXOS Cutter** para macOS.

## Frontera del producto

El Cutter consume el contrato de corte (`canonicalId/type/source/sourceRanges`) y ejecuta cortes/ensamblado. No es propietario del modelo editorial de Geometra, XR, Calendar o Kanban.

## Capturar el Cutter que funciona hoy

```bash
zsh tools/DEJAR_REPO_LISTO.command
```

El capturador busca `~/ABRXOS_CUTTER_APP` y `~/ABRXOS_MULTI_CUTTER`, prioriza el control panel actual, detecta entrypoint, versión, imports Python y referencias literales de modelos, y elimina launchers/caches/output/media dependientes de la máquina.

## Reinstalar desde cero

```bash
zsh install/INSTALAR_ENTORNO_COMPLETO_MAC.command
```

Para instalación no interactiva de Homebrew/dependencias cuando aceptas ese cambio explícitamente:

```bash
zsh install/INSTALAR_ENTORNO_COMPLETO_MAC.command --yes
```

## Dependencias base

- macOS
- Python >= 3.11
- FFmpeg + ffprobe
- `h264_videotoolbox` recomendado en Apple Silicon
- paquetes Python detectados del código actual dentro de un venv dedicado
- modelos sólo si `models/MODELS_MANIFEST.json` los declara

## GitHub

Nombre recomendado: **Abrxs_cutter_v1** (privado).

```bash
zsh tools/PREPARAR_REPO_GITHUB.command
git commit -m "Abrxs_cutter_v1 · reproducible current snapshot"
gh repo create Abrxs_cutter_v1 --private --source=. --remote=origin --push
```
