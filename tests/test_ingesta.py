import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

EJ = Path(__file__).parents[1] / "examples"
FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("FITPLAN_CLAVE", Fernet.generate_key().decode())
    from app.db import cripto
    cripto._fernet.cache_clear()
    from app.db.conexion import conectar
    c = conectar(tmp_path / "t.db")
    yield c
    c.close()
    cripto._fernet.cache_clear()


@pytest.fixture
def pid(conn):
    from app.ingesta import crear_perfil
    return crear_perfil(conn, "prueba", "H", "1986-01-01", 175)


def test_migracion_idempotente(conn):
    from app.db.conexion import migrar
    assert migrar(conn) == 2 and migrar(conn) == 2


def test_hevy_dedup_por_fichero_y_por_serie(conn, pid, tmp_path):
    from app.ingesta import importar_hevy
    inf = importar_hevy(conn, pid, FIX / "hevy_mini.csv")
    assert inf.nuevos == 6 and inf.duplicados == 0 and len(inf.errores) == 1
    assert importar_hevy(conn, pid, FIX / "hevy_mini.csv").ya_importado
    # exportación posterior: mismo contenido + una serie nueva → solo 1 nueva
    nuevo = tmp_path / "hevy_2.csv"
    txt = (FIX / "hevy_mini.csv").read_text(encoding="utf-8")
    nuevo.write_text(txt + '"Espalda","25 Sep 2026, 07:04","25 Sep 2026, 08:01","","Pull Up",1,"",2,"normal",,8,,,\n',
                     encoding="utf-8")
    inf2 = importar_hevy(conn, pid, nuevo)
    assert (inf2.nuevos, inf2.duplicados) == (1, 6)


def test_hevy_hora_local_a_utc(conn, pid):
    from app.ingesta import importar_hevy
    importar_hevy(conn, pid, FIX / "hevy_mini.csv")
    fila = conn.execute("SELECT inicio_utc FROM hevy_entreno ORDER BY inicio_utc LIMIT 1").fetchone()
    assert fila[0] == "2026-09-02T05:10:00+00:00"  # 07:10 en Madrid (CEST, UTC+2)


def test_composicion_y_duplicado(conn, pid):
    from app.ingesta import importar_composicion
    assert importar_composicion(conn, pid, EJ / "composicion_2026-09-22.json").nuevos == 1
    assert importar_composicion(conn, pid, EJ / "composicion_2026-09-22.json").ya_importado


def test_perfil_medico_se_guarda_cifrado(conn, pid):
    from app.ingesta import importar_perfil_medico, perfil_medico_vigente
    inf = importar_perfil_medico(conn, pid, EJ / "perfil_medico_ejemplo.md")
    assert inf.nuevos == 1, inf.errores
    crudo = conn.execute("SELECT yaml_cifrado FROM perfil_medico").fetchone()[0]
    assert b"Hipercolesterolemia" not in crudo
    assert perfil_medico_vigente(conn, pid)["condiciones"][0]["nombre"] == "Hipercolesterolemia leve"


def test_aislamiento_entre_perfiles(conn, pid):
    from app.ingesta import crear_perfil, importar_hevy
    otro = crear_perfil(conn, "otro", "M", None, 160)
    importar_hevy(conn, pid, FIX / "hevy_mini.csv")
    inf = importar_hevy(conn, otro, FIX / "hevy_mini.csv")
    assert inf.nuevos == 6  # el mismo fichero en otro perfil no se considera duplicado
    n = conn.execute("SELECT COUNT(*) FROM hevy_serie WHERE perfil_id=?", (otro,)).fetchone()[0]
    assert n == 6
