import importlib

from fastapi.testclient import TestClient

from app import config


def _client(monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "a.js").write_text("console.log(1)")
    (tmp_path / "manifest.webmanifest").write_text("{}")
    monkeypatch.setattr(config, "FRONTEND_DIST", tmp_path)
    import app.main as m

    importlib.reload(m)
    return TestClient(m.app), m


def test_built_app_is_served_with_spa_fallback(monkeypatch, tmp_path):
    c, m = _client(monkeypatch, tmp_path)
    try:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/coach").text == "<html>app</html>"  # client-side route
        assert c.get("/assets/a.js").text == "console.log(1)"
        assert c.get("/manifest.webmanifest").text == "{}"
        assert c.get("/health").json() == {"ok": True}
        assert c.get("/api/does-not-exist").status_code == 404  # API misses are not swallowed
        assert c.get("/../../etc/passwd").status_code in (200, 404)
        assert "root:" not in c.get("/..%2f..%2f..%2fetc/passwd").text
    finally:
        monkeypatch.undo()
        importlib.reload(m)


def test_api_still_works_with_static_mounted(monkeypatch, tmp_path):
    c, m = _client(monkeypatch, tmp_path)
    try:
        assert c.get("/api/profile").status_code == 200
    finally:
        monkeypatch.undo()
        importlib.reload(m)
