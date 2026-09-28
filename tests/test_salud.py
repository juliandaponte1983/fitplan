from fastapi.testclient import TestClient

from app.main import app


def test_salud():
    r = TestClient(app).get("/salud")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"
