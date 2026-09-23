# AI 검색 음성 입력

원본: `http://ltmetric-pms.synology.me:41717/pilot2/agent`, commit
`d3aea3306cde7dc4dbaf7d86d1c6324a0e0d112a`의 `backend/app/api/speech.py`,
`backend/app/services/speech.py`, `frontend/speech.js`, `backend/tests/test_speech.py`.
백엔드 서비스/API를 이식하고 프런트엔드는 React 생명주기에 맞춰 재구성했습니다.
기존 LLM/경로 탐색/DB 구조는 변경하지 않습니다.

## 사용

AI 검색 → 음성 입력 → 사용자가 마이크 권한 허용 → 같은 버튼을 다시 눌러 녹음 중지·텍스트 변환 →
출발지/도착지/선호조건 확인·수정 → 경로 검색.
최대 30초 녹음(브라우저는 29초에 자동 중지), 최대 8MB, 결과 최대 500자.
자동 검색하지 않으며 변환 중 수정한 입력은 보존하고 인식 결과를 따로 보여줍니다.
별도 중지/취소 버튼 없이 하나의 버튼을 사용합니다. 권한 확인·변환 중에는 중복 클릭을 막습니다.
검색 탭 전환, 검색창 접기, 페이지 이탈 시 마이크를 해제합니다.
변환 취소 시 브라우저는 응답을 적용하지 않습니다. 이미 서버에서 시작한 추론은
완료될 때까지 실행될 수 있으며 그동안 다른 변환 요청은 503으로 거절합니다.

## 실행

`docker compose up -d --build backend frontend`

별도 STT 컨테이너 없이 기존 backend에서 faster-whisper 1.2.1 / Whisper small
한국어 CPU INT8(2 threads, 동시 추론 1개)을 사용합니다.
공식 구현: https://github.com/SYSTRAN/faster-whisper
최초 공개 모델 다운로드는 시간이 걸리고 디스크/RAM/CPU를 사용합니다.
모델은 `stt_models` Docker 볼륨에 캐시되며 음성을 저장하는 볼륨이 아닙니다.
`.env.example`의 `STT_MODEL=small`은 비밀정보가 아닙니다.
키나 유료 STT API는 필요하지 않습니다.

`POST /api/speech/transcribe`는 raw audio body를 받고 text/language/model/duration_s/latency_ms를 반환합니다.
지원 형식: WebM, Ogg, WAV, MP4. 413 크기/길이 초과, 415 미지원 형식,
422 무음/손상/빈 음성, 503 모델 오류 또는 다른 변환 진행 중.
STT는 별도 스레드에서 실행되며 검색이나 LLM을 자동 호출하지 않습니다.

## 개인정보와 배포

사용자가 버튼을 눌렀을 때만 마이크 권한을 요청합니다. 실제 음성은 SafeAlley
백엔드로 전송되고 외부 STT API로 전달하지 않습니다. 앱은 음성 및 STT 텍스트를
파일/DB/로그에 저장하지 않습니다. Nginx의 음성 요청 버퍼링도 비활성화합니다.
인식 후 경로 검색을 누르면 기존 AI 검색 요청 흐름을 따릅니다.
localhost는 개발용으로 사용 가능하며 다른 컴퓨터에서 마이크를 쓰려면 HTTPS가 필요합니다.
외부 공개 전 인증/요청 제한/미디어 디코더 자원 제한을 추가 검토해야 합니다.
API 크기·시간 제한과 직렬 추론만으로 공개 서비스의 전체 부하를 제어하지는 못합니다.

테스트는 합성 음성과 mock을 사용합니다. 실제 사용자 마이크의 인식 정확도는
별도 확인이 필요하며, 인식된 지명을 자동 보정하거나 정확하다고 보장하지 않습니다.

## 로컬 검증 (2026-09-23)

- 백엔드 단위 테스트 121 passed (음성 테스트 11개 포함), 프런트엔드 62 passed,
  production build 성공. 실제 DB를 쓰는 전체 통합 테스트는 이번 STT 검증에서 실행하지 않았습니다.
- Windows Heami 합성 음성을 메모리에서 생성해 3000번 Nginx → FastAPI → 실제
  Whisper small 경로로 전송했습니다. 원음 파일이나 사용자 마이크 녹음은 남기지 않았습니다.
- 입력: “주안역에서 인천사랑병원까지 계단이 적은 길로 안내해 줘”.
  결과: “주한역에서 인천사랑병원까지 계단이 적은 길로 안내해줘”.
  5.01초 음성, 서버 처리 12.697초(모델은 미리 다운로드, 첫 서버 모델 적재 포함).
  지명 오류가 있으므로 정확도 통과로 해석하지 않습니다.
- Chrome에서 음성 입력 버튼 표시 확인. 사용자 마이크 권한·실제 발화 및
  브라우저 WebM → STT 실녹음 경로는 미검증입니다. 녹음 수명주기는 mock으로 검사했습니다.
