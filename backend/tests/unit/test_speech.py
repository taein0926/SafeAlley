# Adapted from pilot2/agent d3aea330 (local speech input).
from io import BytesIO
import wave
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
import httpx
from app.main import app
from app.services import speech_service as speech

client = TestClient(app)


@pytest.fixture(autouse=True)
def default_speech_environment(monkeypatch):
    monkeypatch.delenv('STT_REMOTE_URL', raising=False)
    monkeypatch.setenv('STT_LOCAL_FALLBACK', 'true')


def wav(seconds=1, value=0):
    output = BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(int(value).to_bytes(2, 'little', signed=True) * int(seconds * 16000))
    return output.getvalue()


@pytest.mark.parametrize('payload,content_type,expected', [
    (b'', 'audio/wav', 422), (b'bad', 'audio/wav', 422),
    (b'bad', 'text/plain', 415), (b'x' * (speech.MAX_BYTES + 1), 'audio/webm', 413),
    (wav(), 'audio/wav', 422), (wav(31, 500), 'audio/wav', 413),
])
def test_audio_limits(payload, content_type, expected):
    assert client.post('/api/speech/transcribe', content=payload,
                       headers={'Content-Type': content_type}).status_code == expected


def test_transcription_returns_text_not_search(monkeypatch):
    class FakeModel:
        def transcribe(self, audio, **options):
            assert options['language'] == 'ko'
            return iter([SimpleNamespace(text='금천구 안에 있는 시설물을 보여줘')]), None
    monkeypatch.setattr(speech, '_model', FakeModel())
    response = client.post('/api/speech/transcribe', content=wav(1, 500),
                           headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 200
    assert response.json()['text'] == '금천구 안에 있는 시설물을 보여줘'
    assert 'result' not in response.json()


def test_busy_returns_retryable_error():
    with speech._lock:
        response = client.post('/api/speech/transcribe', content=wav(), headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 503


def test_error_releases_inference_lock(monkeypatch):
    class BrokenModel:
        def transcribe(self, *_args, **_kwargs):
            raise RuntimeError('private implementation error')
    monkeypatch.setattr(speech, '_model', BrokenModel())
    response = client.post('/api/speech/transcribe', content=wav(1, 500),
                           headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 503
    assert response.json()['detail'] == '음성 인식 모델을 실행하지 못했습니다. 서비스 상태를 확인해 주세요.'
    assert 'private implementation error' not in response.text
    assert not speech._lock.locked()


@pytest.mark.parametrize('text', ['', 'a' * 501])
def test_empty_and_overlong_transcriptions_are_rejected(monkeypatch, text):
    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return iter([SimpleNamespace(text=text)]), None
    monkeypatch.setattr(speech, '_model', FakeModel())
    response = client.post('/api/speech/transcribe', content=wav(1, 500),
                           headers={'Content-Type': 'audio/wav; codecs=pcm'})
    assert response.status_code == 422
    assert not speech._lock.locked()


def test_private_gpu_transcription(monkeypatch):
    def fake_post(url, **kwargs):
        assert url == 'http://host.docker.internal:11436/transcribe'
        assert kwargs['content'].startswith(b'RIFF')
        return httpx.Response(200, json={'text': '계단 피해서 안내해', 'language': 'ko',
                                         'model': 'small', 'duration_s': 1.0, 'latency_ms': 300})
    monkeypatch.setenv('STT_REMOTE_URL', 'http://host.docker.internal:11436')
    monkeypatch.setattr(httpx, 'post', fake_post)
    response = client.post('/api/speech/transcribe', content=wav(1, 500),
                           headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 200
    assert response.json()['text'] == '계단 피해서 안내해'


def test_gpu_unavailable_falls_back_to_cpu(monkeypatch):
    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return iter([SimpleNamespace(text='CPU 대체 처리')]), None
    monkeypatch.setenv('STT_REMOTE_URL', 'http://host.docker.internal:11436')
    monkeypatch.setattr(httpx, 'post', lambda *_args, **_kwargs: (_ for _ in ()).throw(
        httpx.ConnectError('unavailable')))
    monkeypatch.setattr(speech, '_model', FakeModel())
    response = client.post('/api/speech/transcribe', content=wav(1, 500),
                           headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 200
    assert response.json()['text'] == 'CPU 대체 처리'


def test_gpu_rejects_invalid_audio_without_cpu_fallback(monkeypatch):
    monkeypatch.setenv('STT_REMOTE_URL', 'http://host.docker.internal:11436')
    monkeypatch.setattr(httpx, 'post', lambda *_args, **_kwargs: httpx.Response(
        422, json={'detail': '음성이 감지되지 않았습니다.'}))
    response = client.post('/api/speech/transcribe', content=wav(1, 500),
                           headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 422


@pytest.mark.parametrize('remote', ['', 'http://pc-whisper:18081'])
@pytest.mark.parametrize('failure', ['connect', 'busy'])
def test_remote_only_never_starts_local_model(monkeypatch, remote, failure):
    class ForbiddenModel:
        def transcribe(self, *_args, **_kwargs):
            pytest.fail('PC 전용 모드에서는 API 서버가 모델을 실행하면 안 됩니다.')
    def unavailable(*_args, **_kwargs):
        if failure == 'connect':
            raise httpx.ConnectError('unavailable')
        return httpx.Response(503, json={'detail': 'busy'})
    monkeypatch.setenv('STT_REMOTE_URL', remote)
    monkeypatch.setenv('STT_LOCAL_FALLBACK', 'false')
    monkeypatch.setattr(speech, '_model', ForbiddenModel())
    monkeypatch.setattr(httpx, 'post', unavailable)
    response = client.post('/api/speech/transcribe', content=wav(1, 500),
                           headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 503
    assert not speech._lock.locked()
