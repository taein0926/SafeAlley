import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
VERSION = "a" * 24


def test_manifest_and_sparse_tiles_are_cacheable_without_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HEATMAP_TILE_ROOT", str(tmp_path))
    data = {"version": VERSION, "minzoom": 12, "maxzoom": 17, "bounds": [126, 37, 127, 38]}
    root = tmp_path / VERSION
    root.mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps(data))
    (root / "manifest.json").write_text(json.dumps(data))
    response = client.get("/api/streetlight-heatmap/manifest")
    assert response.json() == data
    assert response.headers["cache-control"] == "no-store"
    empty = client.get(f"/api/streetlight-heatmap/{VERSION}/12/1/1.png")
    assert empty.status_code == 200
    assert empty.content.startswith(b"\x89PNG")
    assert "immutable" in empty.headers["cache-control"]
    path = root / "12" / "1"
    path.mkdir(parents=True)
    (path / "2.png").write_bytes(empty.content)
    assert client.get(f"/api/streetlight-heatmap/{VERSION}/12/1/2.png").content == empty.content


def test_missing_generation_and_invalid_tiles_are_not_success(tmp_path, monkeypatch):
    monkeypatch.setenv("HEATMAP_TILE_ROOT", str(tmp_path))
    assert client.get("/api/streetlight-heatmap/manifest").status_code == 503
    for suffix in [f"{VERSION}/99/0/0.png", f"{VERSION}/12/-1/0.png", "unknown/12/1/1.png"]:
        assert client.get(f"/api/streetlight-heatmap/{suffix}").status_code == 404
