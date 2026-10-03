import importlib

from fastapi.testclient import TestClient


def test_the_vercel_entrypoint_starts_from_the_demo_data(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_DB", str(tmp_path / "demo.db"))
    import app
    importlib.reload(app)            # app.py builds its database when it is imported
    listing = TestClient(app.app).get("/api/candidates").json()
    assert listing["demo"] is True and len(listing["candidates"]) == 16
