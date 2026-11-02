from fastapi.testclient import TestClient
from pocket_orchestra.app import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").status_code == 200
    page = client.get("/")
    assert page.status_code == 200
    assert "Pocket Orchestra" in page.text
    assert 'id="density"' in page.text


def test_generate_and_download():
    result = client.post("/api/generate", json={"config": {"bars": 8,
                           "ensemble": "orchestra_choir", "seed": 4}, "render_preview": False})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["quality"]["passed"] == data["quality"]["total"]
    assert "choir.musicxml" in data["urls"]
    assert "orchestra.musicxml" in data["urls"]
    for url in data["urls"].values():
        r = client.get(url)
        assert r.status_code == 200
        assert len(r.content) > 10
    assert client.get(f"/api/artifacts/{data['job_id']}/not_allowed.env").status_code == 404
    assert client.get("/api/artifacts/not-a-uuid/score.mid").status_code == 400


def test_bad_request():
    r = client.post("/api/generate", json={"config": {"tempo": -10}})
    assert r.status_code == 422
