# FitPlan — instrucciones para Claude Code

App personal local-first que ajusta entreno y alimentación con datos de Hevy, Garmin (FIT) y Fitdays.
Lee `README.md` para la arquitectura, el flujo de datos y las reglas del validador (V1–V15).

## Principios
- **La app calcula, el LLM redacta.** kcal, macros, progresiones, volumen y restricciones salen del motor local (`engine/`). Los LLM solo reciben paquetes (`prompts/03_plan_semanal.md`) y devuelven JSON validado.
- Los contratos de `schemas/` son la fuente de verdad. Si cambias un esquema, actualiza los ejemplos y ejecuta `python tools/validar.py`.
- Seguridad de datos de salud: nada de datos personales en el repo. Los datos reales viven en `../datos/<perfil>/` (fuera del repo). Perfil médico: solo se guarda el bloque YAML, cifrado.
- Multiperfil: toda consulta filtra por `profile_id`.

## Stack
- Python 3.14, entorno en `~/.venvs/fitplan` (fuera de OneDrive, no crear `.venv` dentro del repo).
- Backend FastAPI + SQLite (BD fuera del repo, en ~/Library/Application Support/FitPlan; campos sensibles cifrados con Fernet, clave en el Llavero). CLI: `python -m app.cli`. Frontend web propio. Lectores: `fitdecode` (FIT), CSV de Hevy (fechas en español: "25 sept 2026, 7:04"), API de Hevy Pro.

## Convenciones
- Código e identificadores en español cuando describen el dominio (`perfil`, `sesion`, `receta`); inglés para lo técnico estándar.
- Tests con pytest en `tests/`. Cada lector y cada regla del validador con su test.
- Commits pequeños, mensaje en español en imperativo.

## Comprobaciones antes de dar algo por terminado
```bash
python tools/validar.py && python tools/coincidencias.py | tail -1
```
