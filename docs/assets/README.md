# 서비스 구성도 원본

`service-architecture.svg`는 사용자가 보관하던 서비스 구성도의 편집 원본을 현재 구조로
갱신한 파일이다. 기존 디자인과 내장 아이콘을 유지하며, 외부 이미지를 실행 시 요청하지 않는다.
그림의 로고는 구성 요소 식별용이며 기관의 후원·협약을 의미하지 않는다.

- 사용자 브라우저: HTTPS `:21802`로 VM에 접속한다.
- VM: Nginx·React/Cesium, FastAPI, PostgreSQL/PostGIS, 날씨 수집기를 실행한다.
- GPU 서버: Ollama `gemma4:26b`, 별도 faster-whisper `small`을 실행한다.
- VM↔GPU: 비공개 SSH 터널을 사용하며 사용자 PC의 SSH 창과는 별개다.
- Jev·Nominatim: VM이 호출하는 외부 연동이다. Jev는 입력 중 조건 분석용이다.
- 데이터 구축: 별도 승인된 데이터 작업 환경에서 필요할 때 실행한다. 고정 VM runtime의
  네 컨테이너에 pipeline 서비스가 추가된다는 뜻은 아니다.

이 파일을 변경하면 로컬 `output/SafeAlley_서비스_구성도_서버배포.svg`·`.png`와
`SafeAlley_발표자료_v3.pptx`의 구성도도 함께 갱신한다. 과거 발표자료는 당시 기록으로 보존한다.
폰트·아이콘·서비스 의미를 확인한 뒤 렌더링하고, 실제 적용 커밋은 VM `runtime/state.json`으로 확인한다.
