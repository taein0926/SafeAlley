# 문장 입력의 음성 입력

마이크 버튼으로 녹음한 음성을 FastAPI가 받아 GPU 서버의 Whisper로 우선 변환한다.
문장 해석·경로 탐색·실시간 조건 분석 서비스와 별개의 입력 보조 기능이다.

## 사용 흐름

마이크 버튼 → 권한 허용 → 녹음 → 같은 버튼으로 중지·변환 →
입력 내용 확인·수정 → 길찾기.

최대 30초·8MB, 인식 결과는 최대 500자다. 브라우저는 29초에 자동 중지한다.
변환 후 길찾기를 자동 실행하지 않는다. 변환 도중 사용자가 수정한 입력은
보존하며 인식 결과를 따로 안내한다.
권한 확인·변환 중에는 중복 클릭을 막고, 입력 모드 전환·검색창 접기·
페이지 이탈 시 마이크를 해제한다.

변환 취소는 브라우저의 결과 적용을 중단한다. 이미 시작한 서버 추론은
완료될 수 있으며 그동안 추가 변환은 503으로 거절한다.

## 실행 구조

```powershell
docker compose up -d --build backend frontend
```

VM 배포에서는 브라우저 → VM FastAPI → 비공개 SSH 터널 → GPU 서버의
faster-whisper 순서로 처리한다. GPU 서버의 별도 Python 서비스는 시작할 때
`STT_MODEL=small`을 CUDA(`int8_float16`)로 올려두며 동시 추론을 한 건으로 제한한다.
VM backend는 `STT_REMOTE_URL`로 이 서비스에 접속한다. 연결이 실패하면
VM의 faster-whisper `small` CPU INT8·2 threads로 대체한다. 로컬 Docker는
원격 주소가 설정되지 않았으면 CPU 경로를 사용하며, 승인된 로컬 터널을
설정한 경우 GPU 우선 경로를 사용할 수 있다. [배포 안내](../deployment/README.md)를 따른다.

GPU 서비스와 CPU 대체 구현은 각각
[gpu_stt_server.py](../backend/app/services/gpu_stt_server.py),
[speech_service.py](../backend/app/services/speech_service.py)에 있다.
CPU 모델의 첫 다운로드·적재에는 네트워크와 디스크·RAM·CPU가 필요하다.
`stt_models` 볼륨은 CPU 대체 모델 캐시이며 녹음 보관소가 아니다.

`POST /api/speech/transcribe`는 raw audio body를 받고
`text / language / model / device / duration_s / latency_ms`를 반환한다.
`device=cuda`는 GPU 처리, `device=cpu`는 대체 처리를 뜻한다.
`latency_ms`는 각 인식 함수 내부의 디코딩·추론 시간으로, 브라우저 전송과
VM↔GPU 전송을 모두 포함한 사용자 체감 시간이 아니다.

- 지원 형식: WebM, Ogg, WAV, MP4.
- 413: 크기·길이 초과.
- 415: 미지원 형식.
- 422: 무음·손상·빈 음성 등.
- 503: 모델 오류 또는 다른 변환 진행 중.

## 개인정보·제한

사용자가 누를 때만 마이크 권한을 요청한다. 음성은 SafeAlley backend를
거쳐 사내 GPU 서버로 전달될 수 있으며 공개 외부 STT API에는 보내지 않는다.
앱은 음성과 STT 텍스트를
파일·DB·로그에 저장하지 않고 Nginx 음성 요청 버퍼링도 비활성화한다.
이후 길찾기나 실시간 조건 분석에 전달되는 문장은 각 서비스의 정책을 따른다.

localhost는 개발에 사용할 수 있지만 다른 컴퓨터에서 마이크를 쓰려면
HTTPS가 필요하다. 공개 서비스에서는 인증·요청 제한·디코더 자원 제한을
추가 검토해야 한다. 현재의 크기 제한과 직렬 추론만으로 전체 부하가 제어되지는 않는다.

테스트 방법은 [테스트 안내](testing.md)를 따른다. mock 테스트는 사용자
마이크·실제 발화의 정확도를 보장하지 않는다. 과거 합성 음성의 처리 시간과
당시 테스트 개수는 현재 성능 안내에서 제거했다.
