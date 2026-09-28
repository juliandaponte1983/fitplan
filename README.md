# FitPlan — Fase 1: contratos

Esta fase define **qué entra y qué sale** de la app antes de escribir código. Todo lo demás (lectores, motor, frontend) se construirá contra estos contratos.

```
fitplan/
├── prompts/
│   ├── 01_perfil_medico.md     → lo lleva el usuario a un LLM junto con sus informes
│   ├── 02_fitdays.md           → imagen de Fitdays → JSON
│   └── 03_plan_semanal.md      → plantilla del paquete semanal + corrección
├── schemas/
│   ├── perfil_medico.schema.json         (bloque YAML del .md médico)
│   ├── composicion_corporal.schema.json  (cada medición de la báscula)
│   ├── paquete_semanal.schema.json       (app → LLM)
│   ├── plan_semanal.schema.json          (LLM → app → Hevy)
│   └── alimento_nutricion.schema.json    (base nutricional local)
├── data/
│   ├── alimentos_grupos.json   diccionario de alérgenos, restricciones y derivados (regla V5)
│   └── periodizacion.json      bloques de 4 semanas y reglas de progresión
├── examples/                   ejemplos que validan contra los esquemas
└── tools/
    ├── validar.py              valida esquemas y ejemplos
    └── coincidencias.py        matcher de alimentos ↔ restricciones (+30 casos de prueba)
```

## Flujo de datos

```
Informes médicos ─(01)─► LLM ─► perfil_medico.md ──┐
Fitdays (imagen) ─(02)─► LLM ─► composicion.json ──┤
Hevy (CSV / API) ───────────────────────────────────┼─► FitPlan: motor local ─► paquete_semanal (03) ─► Claude
Garmin FIT ─────────────────────────────────────────┘        ▲                                           │
                                                             └── validador ◄──── plan_semanal.json ◄────┘
                                                                     │
                                                                     └─► calendario, menú, lista de la compra, rutinas en Hevy
```

## Principio clave

**La app calcula y el LLM redacta.** Lo siguiente sale del motor local y llega al LLM como límite duro:

- kcal y macros,
- progresiones por ejercicio,
- volumen semanal,
- restricciones,
- catálogo de ejercicios permitidos.

El LLM solo elige cómo materializarlo (orden, distribución, recetas, variedad). Después, la app **vuelve a verificarlo todo** sin fiarse del `autochequeo` del LLM.

## Reglas del validador (importación del plan)

| # | Regla | Severidad |
|---|---|---|
| V1 | El JSON cumple `plan_semanal.schema.json` | bloqueo |
| V2 | `paquete_id` y `semana_inicio` coinciden con el paquete | bloqueo |
| V3 | Todo `exercise_template_id` está en `catalogo_ejercicios` | bloqueo |
| V4 | Ningún ejercicio tiene un patrón incluido en una restricción `prohibido` | bloqueo |
| V5 | Ningún ingrediente ni alimento coincide con una restricción de dieta `prohibido`, ni con sus sinónimos o derivados (diccionario local), ni con un alérgeno declarado | bloqueo |
| V6 | Todas las restricciones `prohibido` de dieta aparecen en `alimentos_evitar` | bloqueo |
| V7 | kcal de cada día dentro de ±tolerancia de su objetivo | bloqueo |
| V8 | Proteína ≥ objetivo − 5 %; grasa ≥ mínimo; fibra ≥ mínimo | bloqueo |
| V9 | Totales del día = suma de items (±2 %); macros de receta ≈ ingredientes según la BD local (±10 %) | aviso → bloqueo si > 20 % |
| V10 | `4·P + 4·C + 9·G` ≈ kcal (±8 %) | aviso |
| V11 | Progresiones prescritas respetadas; resto ≤ `incremento_carga_max_pct` | bloqueo |
| V12 | Nº de sesiones de fuerza/cardio, min Z2 (±10 %) y días de descanso | bloqueo |
| V13 | Sesiones dentro de la disponibilidad; comidas a ±60 min del horario | aviso |
| V14 | Si `usar_rpe_en_lugar_de_fc` → ningún bloque con `zona`; nunca por encima de `rpe_max` | bloqueo |
| V15 | Lista de la compra ≥ suma de ingredientes (±10 %) | aviso |

Si hay algún bloqueo, la app genera el **paquete de corrección** con la lista de errores. Los avisos se muestran y el usuario decide si acepta el plan.

## Decisiones tomadas

- Stack: FastAPI + SQLite + frontend web; multiperfil con MFA. BD en `~/Library/Application Support/FitPlan/` (fuera de OneDrive). Cifrado de campos sensibles (perfil médico, claves de API) con Fernet; clave maestra en el Llavero de macOS. SQLCipher descartado por problemas de compilación con Python 3.14.
- LLM: paquetes manuales (la API queda preparada para más adelante).
- Fuentes: Hevy (fuerza) · Garmin FIT (FC, carga, cardio) · Fitdays (composición).
- Hevy Pro: la app sube las rutinas por API; el CSV queda como alternativa.
- Dieta: menú de 7 días + recetas + lista de la compra.
- **Perfil médico: solo se guarda el bloque YAML**, cifrado. Al importar, la app muestra el `.md` completo para que lo revises, valida el YAML y descarta la parte narrativa. Solo conserva el SHA-256 del fichero y la fecha, para trazabilidad. Si hay informes nuevos, se genera un perfil nuevo; las versiones anteriores del YAML se conservan.
- **Diccionario de alimentos** (`data/alimentos_grupos.json`): los 14 alérgenos UE más lactosa, sodio, azúcares añadidos, alcohol, grasas saturadas, carne procesada, carne roja, cafeína, purinas, pomelo, vitamina K y potasio.
  - Cada grupo tiene sus términos, sus excepciones y un alias en lenguaje natural («marisco» → crustáceos + moluscos).
  - Si una restricción no coincide con ningún grupo, se busca como término literal.
  - Además del filtro por términos, la app **suma nutrientes** (sodio, grasas saturadas, potasio, cafeína) con la base nutricional.
- **Base nutricional:** BEDCA como fuente principal (alimentos españoles) y USDA FoodData Central (dominio público) como respaldo. Antes de importar BEDCA hay que revisar sus condiciones de uso. Se añadirá una tabla de factores de cocción para pasar de crudo a cocido.
- **Periodización** (`data/periodizacion.json`): bloques de 4 semanas (3 de carga + 1 de descarga).
  - El primer bloque arranca en reintroducción (RPE 6,5, 70 % del volumen).
  - Progresión por doble progresión, con subida máxima del 5 %.
  - Si hay un parón de 14 días o más, el bloque se reinicia.
  - Hay descarga anticipada si la carga aguda/crónica supera 1,5, si la FC en reposo sube o si la adherencia cae.

Fase 1 cerrada. **Siguiente: fase 2** (backend base: perfiles, lectores de Hevy CSV/API, Garmin FIT y Fitdays).
