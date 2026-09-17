# ABRXS Cutter 3.1.1 · Process Control Hotfix

Fecha: 2026-09-17

## Motivo

Corrige el falso positivo del updater 3.1.0 que podía detectar su propio `awk` como si fuera un render de `ABRXOS_MULTI_HTML_CUTTER_V2.py`.

## Cambios

- Detección exacta de renders por argv real del proceso Python.
- `setup --no-run`, `awk`, `grep` y `python -c` no se consideran renders.
- Estado visible: `INACTIVO`, `RENDERIZANDO`, `CANCELANDO`, `ERROR`.
- Botón `Ver procesos` dentro del Cutter.
- Botón `Cancelar render` que termina el engine y sus descendientes (incluido FFmpeg), primero con SIGTERM y luego SIGKILL sólo si fuese necesario.
- Botón `Cerrar Cutter…` con tres opciones:
  - Cancelar render y salir.
  - Dejar render en segundo plano y salir.
  - Volver.
- Protección `beforeunload` cuando existe un render activo.
- Control manual de emergencia instalado en Desktop: `ABRXS Cutter Process Control.command`.
- Mantiene intactos los modos CapCut 3.1.0.

## Versiones

- Cutter: `3.1.1`
- Engine: `2.1.0`
- Process Control: `3.1.1`
