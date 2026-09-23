# Adapted from pilot2/agent d3aea330 (local speech input).
"""Local CPU STT; audio lives only in request memory, never in application logs."""
from io import BytesIO
import os
from threading import Lock
from time import perf_counter

MAX_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 30
_lock = Lock()
_model = None


class SpeechError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def decode_audio(payload):
    import av
    import numpy as np
    chunks, samples = [], 0
    # Reject playlists/URLs before format probing; the endpoint accepts media bytes only.
    if not (payload.startswith((b'RIFF', b'OggS', b'\x1aE\xdf\xa3')) or payload[4:8] == b'ftyp'):
        raise SpeechError('음성 파일을 읽을 수 없습니다. 다시 녹음해 주세요.')
    try:
        with av.open(BytesIO(payload), options={'protocol_whitelist': 'pipe'}) as container:
            resampler = av.AudioResampler(format='flt', layout='mono', rate=16000)
            for frame in container.decode(audio=0):
                for output in resampler.resample(frame):
                    samples += output.samples
                    if samples > MAX_SECONDS * 16000:
                        raise SpeechError('음성은 30초 이내로 녹음해 주세요.', 413)
                    chunks.append(output.to_ndarray().flatten())
            for output in resampler.resample(None):
                samples += output.samples
                chunks.append(output.to_ndarray().flatten())
    except SpeechError:
        raise
    except Exception as exc:
        raise SpeechError('음성 파일을 읽을 수 없습니다. 다시 녹음해 주세요.') from exc
    if samples > MAX_SECONDS * 16000:
        raise SpeechError('음성은 30초 이내로 녹음해 주세요.', 413)
    if samples < 1600 or not chunks:
        raise SpeechError('녹음이 너무 짧습니다. 질문을 말한 뒤 중지해 주세요.')
    audio = np.concatenate(chunks)
    if not np.isfinite(audio).all() or np.max(np.abs(audio)) < .001:
        raise SpeechError('음성이 감지되지 않았습니다. 마이크를 확인해 주세요.')
    return audio


def transcribe(payload):
    global _model
    if not _lock.acquire(blocking=False):
        raise SpeechError('다른 음성을 변환 중입니다. 잠시 후 다시 시도해 주세요.', 503)
    started = perf_counter()
    try:
        audio = decode_audio(payload)
        model_name = os.getenv('STT_MODEL', 'small')
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(model_name, device='cpu', compute_type='int8',
                                  cpu_threads=2, num_workers=1,
                                  download_root=os.getenv('STT_MODEL_DIR', '/models/stt'))
        segments, _ = _model.transcribe(audio, language='ko', beam_size=5,
                                        vad_filter=True, condition_on_previous_text=False)
        text = ' '.join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise SpeechError('음성이 감지되지 않았습니다. 조용한 곳에서 다시 말해 주세요.')
        if len(text) > 500:
            raise SpeechError('인식된 질문이 너무 깁니다. 짧게 다시 녹음해 주세요.')
        return dict(text=text, language='ko', model=model_name,
                    duration_s=round(len(audio) / 16000, 2),
                    latency_ms=round((perf_counter() - started) * 1000, 1))
    except SpeechError:
        raise
    except Exception as exc:
        raise SpeechError('로컬 음성 모델을 실행하지 못했습니다. 모델 준비 상태를 확인해 주세요.', 503) from exc
    finally:
        _lock.release()
