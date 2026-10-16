"""Private GPU Whisper endpoint; bind only to loopback behind an SSH tunnel."""
import os
from contextlib import asynccontextmanager
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.services.speech_service import MAX_BYTES, SpeechError, decode_audio

_model = None
_lock = Lock()


@asynccontextmanager
async def lifespan(_app):
    global _model
    from faster_whisper import WhisperModel
    _model = WhisperModel(os.getenv('STT_MODEL', 'small'), device='cuda',
                          compute_type='int8_float16', num_workers=1,
                          download_root=os.getenv('STT_MODEL_DIR'))
    yield
    _model = None


app = FastAPI(lifespan=lifespan)


@app.get('/health')
def health():
    if _model is None:
        raise HTTPException(503, 'Speech model is not ready')
    return {'ready': True, 'device': 'cuda'}


def _transcribe(payload):
    if not _lock.acquire(blocking=False):
        raise SpeechError('다른 음성을 변환 중입니다. 잠시 후 다시 시도해 주세요.', 503)
    started = perf_counter()
    try:
        audio = decode_audio(payload)
        segments, _ = _model.transcribe(audio, language='ko', beam_size=5,
                                        vad_filter=True, condition_on_previous_text=False)
        text = ' '.join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise SpeechError('음성이 감지되지 않았습니다. 조용한 곳에서 다시 말해 주세요.')
        if len(text) > 500:
            raise SpeechError('인식된 질문이 너무 깁니다. 짧게 다시 녹음해 주세요.')
        return {'text': text, 'language': 'ko', 'model': os.getenv('STT_MODEL', 'small'),
                'device': 'cuda',
                'duration_s': round(len(audio) / 16000, 2),
                'latency_ms': round((perf_counter() - started) * 1000, 1)}
    except SpeechError:
        raise
    except Exception as exc:
        raise SpeechError('GPU 음성 모델을 실행하지 못했습니다.', 503) from exc
    finally:
        _lock.release()


@app.post('/transcribe')
async def transcribe(request: Request):
    if request.headers.get('content-type', '').split(';')[0].lower() not in {
        'audio/webm', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/mp4'
    }:
        raise HTTPException(415, '지원하지 않는 음성 형식입니다.')
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, '녹음 크기는 8MB 이하여야 합니다.')
        payload.extend(chunk)
    if not payload:
        raise HTTPException(422, '녹음 내용이 없습니다.')
    try:
        return await run_in_threadpool(_transcribe, bytes(payload))
    except SpeechError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
