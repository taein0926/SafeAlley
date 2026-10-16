from io import BytesIO
import wave
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services import gpu_stt_server as gpu


def wav():
    output = BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes((500).to_bytes(2, 'little', signed=True) * 16000)
    return output.getvalue()


def test_gpu_endpoint_and_health(monkeypatch):
    class FakeModel:
        def transcribe(self, audio, **options):
            assert len(audio) == 16000
            assert options['language'] == 'ko'
            return iter([SimpleNamespace(text='밝은 길로 안내해')]), None
    monkeypatch.setattr(gpu, '_model', FakeModel())
    client = TestClient(gpu.app)
    assert client.get('/health').json()['device'] == 'cuda'
    response = client.post('/transcribe', content=wav(), headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 200
    assert response.json()['text'] == '밝은 길로 안내해'


def test_gpu_endpoint_rejects_bad_audio():
    client = TestClient(gpu.app)
    assert client.post('/transcribe', content=b'bad', headers={'Content-Type': 'audio/wav'}).status_code == 422
