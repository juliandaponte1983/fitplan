"""Importa la respuesta de Claude (plan semanal), la valida y la guarda."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from app.packages import validador

CORRECCION = """El plan anterior no pasó la validación de FitPlan. Corrige SOLO estos puntos y devuelve el JSON completo:
{errores}
Recuerda: responde solo con el bloque ```json."""


def extraer_json(texto: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", texto, re.S)
    bruto = m.group(1) if m else texto.strip()
    if not bruto.startswith("{"):
        i = bruto.find("{")
        if i < 0:
            raise ValueError(f"el fichero no contiene ningún JSON (empieza por: {texto.strip()[:60]!r}). "
                             "¿Se pegó la respuesta de Claude o se copió otra cosa?")
        bruto = bruto[i:bruto.rfind("}") + 1]
    try:
        return json.loads(bruto)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON incompleto o mal formado (línea {e.lineno}, columna {e.colno}): {e.msg}. "
                         "Si la respuesta de Claude se cortó, pídele que continúe y pega el JSON completo.") from None


def importar(conn: sqlite3.Connection, pid: int, ruta: Path | str, carpeta: Path | str) -> dict:
    plan = extraer_json(Path(ruta).read_text(encoding="utf-8"))
    fila = conn.execute("SELECT json FROM paquete WHERE id=? AND perfil_id=?", (plan.get("paquete_id"), pid)).fetchone()
    if not fila:
        raise LookupError("el plan no corresponde a ningún paquete exportado para este perfil (paquete_id desconocido)")
    paquete = json.loads(fila[0])
    hallazgos = validador.validar(plan, paquete)
    res = validador.resumen(hallazgos)
    estado = "rechazado" if res["bloqueos"] else "aceptado"
    with conn:
        if estado == "aceptado":
            conn.execute("UPDATE plan SET estado='sustituido' WHERE perfil_id=? AND semana_inicio=? AND estado='aceptado'",
                         (pid, plan["semana_inicio"]))
        conn.execute("INSERT INTO plan (perfil_id, paquete_id, semana_inicio, estado, json, validacion_json) VALUES (?,?,?,?,?,?)",
                     (pid, plan["paquete_id"], plan["semana_inicio"], estado, json.dumps(plan, ensure_ascii=False),
                      json.dumps(res, ensure_ascii=False)))
    res["estado"] = estado
    carpeta = Path(carpeta)
    if estado == "rechazado":
        errores = "\n".join(f"- [{h.regla}] {h.mensaje}" for h in hallazgos if h.severidad == "bloqueo")
        destino = carpeta / "paquetes" / f"correccion_{plan['semana_inicio']}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(CORRECCION.format(errores=errores), encoding="utf-8")
        res["correccion"] = str(destino)
    else:
        destino = carpeta / "planes" / f"plan_{plan['semana_inicio']}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        res["plan"] = str(destino)
    return res
