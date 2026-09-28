import json
from pathlib import Path

from app.parsers import fitdays, perfil_medico

EJ = Path(__file__).parents[1] / "examples"


def _medicion():
    return json.loads((EJ / "composicion_2026-09-22.json").read_text(encoding="utf-8"))


def test_fitdays_valido_sin_avisos():
    r = fitdays.importar(_medicion(), perfil={"sexo": "H", "edad": 40, "altura_cm": 175})
    assert r.valido and r.avisos == []


def test_fitdays_acepta_bloque_json_del_llm():
    r = fitdays.importar("Aquí tienes:\n```json\n" + json.dumps(_medicion()) + "\n```")
    assert r.valido


def test_fitdays_detecta_incoherencias_y_otro_usuario():
    d = _medicion()
    d["composicion"]["grasa_pct"] = 30.0
    ant = _medicion()
    ant["composicion"]["peso_kg"] = 74.0
    r = fitdays.importar(d, perfil={"sexo": "H", "edad": 40, "altura_cm": 169}, anterior=ant)
    textos = " | ".join(r.avisos)
    assert "grasa" in textos and "otro usuario" in textos and "+4.0 kg" in textos


def test_fitdays_esquema_invalido():
    d = _medicion()
    del d["composicion"]["peso_kg"]
    assert not fitdays.importar(d).valido


def test_perfil_medico_valido_y_descarta_narrativa():
    texto = (EJ / "perfil_medico_ejemplo.md").read_text(encoding="utf-8")
    r = perfil_medico.importar(texto)
    assert r.valido, r.errores
    assert r.yaml_datos["schema"] == "perfil_medico/v1"
    assert "# Perfil médico" in r.narrativa and len(r.sha256) == 64


def test_perfil_medico_fuente_inexistente():
    texto = (EJ / "perfil_medico_ejemplo.md").read_text(encoding="utf-8").replace("fuente: D1", "fuente: D9", 1)
    r = perfil_medico.importar(texto)
    assert not r.valido and any("D9" in e for e in r.errores)


def test_perfil_medico_sin_yaml():
    assert not perfil_medico.importar("# Solo texto").valido
