"""Provider opt-in and HTTP contracts; never connect to a model or database."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.main import app
from app.services import laya_preview_service
from app.services.jev_preview_service import PreviewUnavailable


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.delenv("INTENT_PREVIEW_PROVIDER", raising=False)
    monkeypatch.delenv("LAYA_PREVIEW_ENABLED", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_preserve_jev_and_disable_laya():
    settings = get_settings()
    assert settings.intent_preview_provider == "jev"
    assert settings.laya_preview_enabled is False


def test_default_http_dispatch_still_uses_jev(monkeypatch):
    import app.api.intent_preview as api
    monkeypatch.setattr(laya_preview_service, "analyze_preview", lambda *a, **k: pytest.fail("Laya must be opt-in"))
    monkeypatch.setattr(api, "analyze_preview", lambda q, **kw: {"query": q, "model": "jev-fixture", "conditions": []})
    response = TestClient(app).post("/api/agent/intent-preview", json={"query": "CCTV 많은 길"})
    assert response.status_code == 200
    assert response.json()["model"] == "jev-fixture"


def test_laya_status_dispatch_preserves_status_schema(monkeypatch):
    import app.api.intent_preview as api
    monkeypatch.setenv("INTENT_PREVIEW_PROVIDER", "laya")
    get_settings.cache_clear()
    monkeypatch.setattr(api, "preview_status", lambda: pytest.fail("Do not probe Jev"))
    monkeypatch.setattr(laya_preview_service, "preview_status", lambda: {"enabled": True, "configured": True, "available": True})
    assert TestClient(app).get("/api/agent/intent-preview/status").json() == {"enabled": True, "configured": True, "available": True}


def test_selected_but_disabled_laya_returns_503_without_network(monkeypatch):
    monkeypatch.setenv("INTENT_PREVIEW_PROVIDER", "laya")
    get_settings.cache_clear()
    monkeypatch.setattr(laya_preview_service.httpx, "post", lambda *a, **k: pytest.fail("Disabled provider made a request"))
    response = TestClient(app).post("/api/agent/intent-preview", json={"query": "가로등 많은 길"})
    assert response.status_code == 503


def test_laya_http_failure_never_falls_back_to_jev(monkeypatch):
    import app.api.intent_preview as api
    monkeypatch.setenv("INTENT_PREVIEW_PROVIDER", "laya")
    get_settings.cache_clear()
    monkeypatch.setattr(api, "analyze_preview", lambda *a, **k: pytest.fail("Paid Jev fallback"))
    def unavailable(query):
        raise PreviewUnavailable("Laya unavailable")
    monkeypatch.setattr(laya_preview_service, "analyze_preview", unavailable)
    assert TestClient(app).post("/api/agent/intent-preview", json={"query": "계단 없는 길"}).status_code == 503


def test_provider_and_hash_configuration_reject_invalid_values():
    with pytest.raises(ValidationError):
        Settings(intent_preview_provider="unknown")
    with pytest.raises(ValidationError):
        Settings(laya_checkpoint_sha256="not-a-model-hash")


@pytest.mark.parametrize("answer", [
    {"type": "choice", "choice": [], "confidence": .99},
    {"type": "choice", "choice": {}, "confidence": .99},
    {"type": "choice", "choice": True, "confidence": .99},
    {"type": "choice", "choice": None, "confidence": .99},
    {"type": "choice", "choice": 1, "confidence": .99},
    {"type": "choice", "choice": "unknown", "confidence": .99},
    {"type": "text", "choice": "apply", "confidence": .99},
    {"choice": "apply", "confidence": .99},
])
def test_invalid_laya_answer_returns_503_not_500(monkeypatch, answer):
    from app.schemas.intent_preview import CARD_ORDER

    monkeypatch.setenv("INTENT_PREVIEW_PROVIDER", "laya")
    monkeypatch.setenv("LAYA_PREVIEW_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(laya_preview_service, "monotonic_ns", lambda: 123)
    body = {
        "query": "CCTV 많은 길", "version": 123,
        "checkpoint_sha256": get_settings().laya_checkpoint_sha256,
        "answers": {f: {"type": "choice", "choice": "skip", "confidence": .99} for f in CARD_ORDER},
    }
    body["answers"]["cctv"] = answer

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return body

    monkeypatch.setattr(laya_preview_service.httpx, "post", lambda *a, **kw: Reply())
    response = TestClient(app).post("/api/agent/intent-preview", json={"query": body["query"]})
    assert response.status_code == 503
    assert "Laya 조건 판단값" in response.json()["detail"]
