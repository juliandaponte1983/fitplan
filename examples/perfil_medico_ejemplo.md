---
schema: perfil_medico/v1
generado: 2026-09-28
fuentes:
  - { id: D1, tipo: analitica, fecha: 2026-06-10, descripcion: "Analítica general (EJEMPLO FICTICIO)" }
condiciones:
  - nombre: "Hipercolesterolemia leve"
    cie10: "E78.0"
    estado: activa
    fecha_diagnostico: null
    fuente: D1
    impacto_ejercicio: bajo
    impacto_dieta: medio
    notas: "Ejemplo ficticio para probar el esquema"
medicacion: []
alergias_intolerancias: []
analitica:
  - { parametro: "LDL", valor: 150, unidad: "mg/dL", rango_referencia: "<130", fecha: 2026-06-10, estado: alto, fuente: D1 }
restricciones_ejercicio: []
restricciones_dieta:
  - { id: RD1, nivel: limitar, alimento_o_grupo: "grasas saturadas", limite: "< 10 % de las kcal", motivo: "LDL elevado", fuente: D1 }
  - { id: RD2, nivel: limitar, alimento_o_grupo: "embutidos", limite: "máx. 1 vez/semana", motivo: "LDL elevado", fuente: D1 }
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
  - "Mareo o desmayo durante el ejercicio"
requiere_valoracion_medica: { valor: false, motivo: null }
confianza: media
datos_faltantes:
  - "Tensión arterial reciente"
---

# Perfil médico — resumen
EJEMPLO FICTICIO para probar el esquema. No corresponde a ninguna persona real.

## Condiciones relevantes
## Medicación y efectos prácticos
## Implicaciones para el entrenamiento
## Implicaciones para la alimentación
## Analítica destacada
## Señales de alarma
## Dudas y datos que faltan
## Aviso
Este documento resume informes médicos para adaptar un plan de ejercicio y alimentación. No sustituye la valoración de un profesional sanitario.
