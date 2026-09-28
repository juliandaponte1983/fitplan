# Prompt 01 — Perfil médico para FitPlan

> **Cómo usarlo**
> 1. **Anonimiza** los informes antes de subirlos: tapa nombre, DNI/NIE, nº de historia clínica, dirección y teléfono. No hacen falta.
> 2. Abre un chat nuevo en el LLM que prefieras, adjunta los informes (PDF o imagen) y pega **todo** el texto de abajo, desde «INICIO DEL PROMPT».
> 3. Revisa la respuesta. Si algo no cuadra con lo que sabes de tu salud, corrígelo.
> 4. Guarda la respuesta como `perfil_medico_AAAA-MM-DD.md` y súbela a FitPlan.
>
> FitPlan no diagnostica. Este perfil solo sirve para que el plan de entreno y dieta **respete** lo que dicen tus informes.

---

## INICIO DEL PROMPT

Actúa como médico especialista en medicina deportiva y nutrición clínica. Tu tarea es **extraer y estructurar** la información de los informes médicos adjuntos para que una aplicación diseñe planes de entrenamiento y alimentación seguros. **No es un diagnóstico.**

### Datos declarados por el usuario (rellena o borra)
- Sexo: …  · Edad: …  · Altura (cm): …
- Condiciones que conozco aunque no estén en los informes: …
- Medicación actual: …
- Alergias / intolerancias: …
- Lesiones o molestias actuales: …
- Tipo de actividad habitual: gimnasio (fuerza), cinta, carrera en exterior, remo, bici indoor

### Reglas estrictas
1. **No inventes nada.** Cada hallazgo debe salir de un documento (`D1`, `D2`…) o de los datos declarados (`declarado_usuario`). Si algo no aparece, no lo incluyas: añádelo a `datos_faltantes`.
2. Si un dato es ambiguo o ilegible, márcalo como `sospecha` o déjalo fuera, y explícalo en «Dudas».
3. Traduce cada condición y cada fármaco en **consecuencias prácticas** para el entreno y la dieta. Ejemplos: un betabloqueante → `usar_rpe_en_lugar_de_fc: true`; hipertensión → evitar `valsalva` e isométricos intensos; una hernia lumbar → limitar `carga_axial` y `flexion_columna_cargada`.
4. En `ambito` usa **solo** estos valores: `carga_axial, flexion_columna_cargada, rotacion_columna_cargada, overhead, impacto, carrera, saltos, valsalva, isometrico_intenso, alta_intensidad_cardio, hiit, rodilla_flexion_profunda, hombro_rotacion_externa, agarre, inversion_cabeza_abajo, calor, ayuno_entreno, otro`.
5. En `alimento_o_grupo` escribe los nombres en minúsculas y en español, lo más genéricos posible («marisco», «gluten», «sal», «alcohol», «azúcares añadidos»).
6. Pon `requiere_valoracion_medica.valor: true` si hay algo que deba ver un médico **antes** de empezar o intensificar un programa de ejercicio. Por ejemplo: cardiopatía, dolor torácico, síncope, hipertensión no controlada, diabetes con hipoglucemias, embarazo, cirugía reciente o valores analíticos muy alterados.
7. Fechas en formato `AAAA-MM-DD`. Unidades del SI.
8. Responde **solo** con el documento Markdown del formato de abajo, sin texto antes ni después.

### Formato de salida (obligatorio)

El documento debe empezar con un bloque YAML entre `---` que cumpla exactamente esta estructura, seguido de las secciones Markdown indicadas.

```
---
schema: perfil_medico/v1
generado: AAAA-MM-DD
fuentes:
  - { id: D1, tipo: analitica, fecha: AAAA-MM-DD, descripcion: "Analítica general" }
condiciones:
  - nombre: "…"
    cie10: "…"            # o null
    estado: activa        # activa | controlada | resuelta | sospecha
    fecha_diagnostico: null
    fuente: D1
    impacto_ejercicio: medio   # ninguno | bajo | medio | alto
    impacto_dieta: bajo
    notas: "…"
medicacion:
  - { principio_activo: "…", pauta: "…", efecto_ejercicio: "…", efecto_dieta: null, fuente: declarado_usuario }
alergias_intolerancias:
  - { sustancia: "…", tipo: alergia, gravedad: moderada, fuente: D2 }
analitica:
  - { parametro: "LDL", valor: 160, unidad: "mg/dL", rango_referencia: "<130", fecha: AAAA-MM-DD, estado: alto, fuente: D1 }
restricciones_ejercicio:
  - id: RE1
    nivel: limitar        # prohibido | limitar | precaucion
    ambito: [carga_axial]
    descripcion: "…"
    limite: "…"           # o null
    motivo: "…"
    fuente: D3
restricciones_dieta:
  - { id: RD1, nivel: limitar, alimento_o_grupo: "sal", limite: "sodio < 2000 mg/día", motivo: "…", fuente: D1 }
limites:
  fc_max_segura_ppm: null
  usar_rpe_en_lugar_de_fc: false
  rpe_max: null
  tension_arterial_objetivo: null
  kcal_min_diarias: null
  proteina_max_g_kg: null
  sodio_max_mg: null
  otros: []
senales_alarma:
  - "Dolor u opresión en el pecho"
requiere_valoracion_medica: { valor: false, motivo: null }
confianza: media          # alta | media | baja
datos_faltantes:
  - "…"
---
```

Las listas vacías van como `[]`. Después del YAML, estas secciones y en este orden:

```
# Perfil médico — resumen
(3–5 líneas en lenguaje claro)

## Condiciones relevantes
## Medicación y efectos prácticos
## Implicaciones para el entrenamiento
(qué se puede hacer, qué hay que limitar y qué evitar; por tipo de actividad: fuerza, cinta, carrera en exterior, remo, bici)
## Implicaciones para la alimentación
## Analítica destacada
## Señales de alarma
## Dudas y datos que faltan
(incluye preguntas concretas para llevar al médico)
## Aviso
Este documento resume informes médicos para adaptar un plan de ejercicio y alimentación. No sustituye la valoración de un profesional sanitario.
```

## FIN DEL PROMPT
