# Adapted from pilot2/agent d3aea330 (local speech input).
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.services import speech_service as speech

router = APIRouter(prefix='/api/speech', tags=['speech'])
SUPPORTED = {'audio/webm', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/mp4'}


@router.post('/transcribe')
async def transcribe(request: Request):
    """Raw audio body, not multipart. Never executes a search."""
    if request.headers.get('content-type', '').split(';')[0].lower() not in SUPPORTED:
        raise HTTPException(415, '지원하지 않는 음성 형식입니다.')
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > speech.MAX_BYTES:
            raise HTTPException(413, '녹음 크기는 8MB 이하여야 합니다.')
        payload.extend(chunk)
    if not payload:
        raise HTTPException(422, '녹음 내용이 없습니다.')
    try:
        return await run_in_threadpool(speech.transcribe, bytes(payload))
    except speech.SpeechError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
