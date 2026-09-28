# Prompt 02 — Extracción del informe Fitdays

> **Uso:** FitPlan envía este prompt junto con la imagen del informe (en modo API) o lo incluye en el paquete para que lo lleves a Claude (en modo manual). La respuesta se valida contra `schemas/composicion_corporal.schema.json`, y se hacen además las comprobaciones cruzadas de abajo.

---

## INICIO DEL PROMPT

Extrae los datos del informe de composición corporal de la imagen adjunta. Responde **solo** con un objeto JSON válido que siga exactamente esta estructura, sin comentarios ni texto adicional:

```json
{
  "schema": "composicion_corporal/v1",
  "fuente": "fitdays",
  "fecha_hora": "AAAA-MM-DDTHH:MM:SS",
  "perfil": { "sexo": "H|M", "edad": 0, "altura_cm": 0 },
  "composicion": {
    "peso_kg": 0, "grasa_kg": 0, "grasa_pct": 0,
    "masa_muscular_kg": 0, "musculo_esqueletico_kg": 0,
    "masa_osea_kg": 0, "proteina_kg": 0, "agua_kg": 0,
    "masa_magra_kg": 0, "grasa_subcutanea_pct": 0,
    "grasa_visceral": 0, "imc": 0, "tmb_kcal": 0,
    "asmi": 0, "whr": 0, "edad_corporal": 0, "puntuacion": 0
  },
  "segmentario": {
    "grasa_kg":   { "brazo_izq": 0, "brazo_der": 0, "tronco": 0, "pierna_izq": 0, "pierna_der": 0 },
    "musculo_kg": { "brazo_izq": 0, "brazo_der": 0, "tronco": 0, "pierna_izq": 0, "pierna_der": 0 }
  },
  "impedancia_ohm": {
    "20kHz":  { "brazo_izq": 0, "brazo_der": 0, "tronco": 0, "pierna_izq": 0, "pierna_der": 0 },
    "100kHz": { "brazo_izq": 0, "brazo_der": 0, "tronco": 0, "pierna_izq": 0, "pierna_der": 0 }
  },
  "extraccion": { "metodo": "llm_vision", "campos_dudosos": [], "incoherencias": [] }
}
```

Reglas:
1. En la tabla principal usa el **valor medido**, no el rango entre paréntesis. Ejemplo: «84.2 (53.4-72.3)» → `84.2`.
2. En el diagrama segmentario, **L = izquierda** y **R = derecha**. Toma los kg, no los porcentajes.
3. **Ignora** el peso objetivo, los «controles», el consumo por ejercicio y la evaluación del equilibrio: los calcula la app.
4. Si un campo no aparece o no se lee, pon `null` y añádelo a `campos_dudosos`.
5. Antes de responder, comprueba:
   - que `grasa_kg / peso_kg × 100` ≈ `grasa_pct` (±1),
   - que `peso_kg / (altura_cm/100)²` ≈ `imc` (±0,3),
   - que `peso_kg − grasa_kg` ≈ `masa_magra_kg` (±0,5).

   Si alguna no cuadra, relee el valor. Si sigue sin cuadrar, descríbelo en `incoherencias`.

## FIN DEL PROMPT

---

### Comprobaciones que hace FitPlan al importar
- Las tres de arriba, recalculadas por la app.
- La fecha no puede ser futura ni estar ya importada (clave: perfil + `fecha_hora`).
- Si el peso cambia más de 2 kg respecto a la medición anterior, pide confirmación.
- Si el sexo, la edad o la altura no coinciden con el perfil, avisa: la báscula podría estar usando otro usuario.
