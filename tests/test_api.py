from fastapi.testclient import TestClient
from pocket_orchestra.app import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").status_code == 200
    page = client.get("/")
    assert page.status_code == 200
    assert "Pocket Orchestra" in page.text
    assert 'id="density"' in page.text
    assert 'id="ensembleHelp"' in page.text
    assert 'id="llmHelp"' in page.text
    assert 'id="choirVowelField"' in page.text


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


def test_each_ensemble_isolated_and_combined():
    """Smoke all five modes via FastAPI without external Ollama or FluidSynth."""
    sets = {
        "orchestra": (12, set()),
        "quartet": (4, set()),
        "choir": (4, {"choir.mid", "choir.musicxml"}),
        "orchestra_choir": (16, {"choir.mid", "choir.musicxml",
                                 "orchestra.mid", "orchestra.musicxml"}),
        "quartet_choir": (8, {"choir.mid", "choir.musicxml",
                              "quartet.mid", "quartet.musicxml"}),
    }
    for ensemble, (part_count, stems) in sets.items():
        response = client.post("/api/generate", json={
            "config": {"ensemble": ensemble, "bars": 8, "seed": 42,
                       "use_ollama": False},
            "render_preview": False,
        })
        assert response.status_code == 200, (ensemble, response.text)
        result = response.json()
        assert len(result["composition"]["parts"]) == part_count, ensemble
        assert result["quality"]["passed"] == result["quality"]["total"], ensemble
        assert {"musicxml", "midi", "report"} | stems <= set(result["urls"]), ensemble
        assert ("choir.mid" in result["urls"]) == ("choir" in ensemble), ensemble
        assert ("orchestra.mid" in result["urls"]) == (ensemble == "orchestra_choir"), ensemble
        assert ("quartet.mid" in result["urls"]) == (ensemble == "quartet_choir"), ensemble
        assert "wav" not in result["urls"], ensemble
