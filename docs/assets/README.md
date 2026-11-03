# 서비스 구성도 원본

`service-architecture.svg`는 사용자가 보관하던 서비스 구성도의 편집 원본을 현재 구조로
갱신한 파일이다. 기존 디자인과 내장 아이콘을 유지하며, 외부 이미지를 실행 시 요청하지 않는다.
그림의 로고는 구성 요소 식별용이며 기관의 후원·협약을 의미하지 않는다.

- 사용자 브라우저: HTTPS `:21802`로 VM에 접속한다.
- VM: Nginx·React/Cesium, FastAPI, PostgreSQL/PostGIS, 날씨 수집기를 실행한다.
- 사용자 PC: Ollama `gemma4:e2b-it-qat`는 GPU, Whisper `small`과 Laya ONNX는 CPU에서 실행한다.
- VM↔PC: PC 연결 관리자의 명시적 SSH 역방향 터널과 VM 전달기를 사용한다. PC가 켜져 있어야 한다.
- Nominatim은 VM이 호출하는 외부 장소 연동이다. Jev는 명시적 선택·복구용 외부 미리보기이며, 현재 Laya 구성에서는 호출하지 않는다.
- 데이터 구축: 별도 승인된 데이터 작업 환경에서 필요할 때 실행한다. 고정 VM runtime의
  네 컨테이너에 pipeline 서비스가 추가된다는 뜻은 아니다.

구성도에서 파생한 과거 로컬 `output/SafeAlley_서비스_구성도_서버배포.svg`·`.png`와
`SafeAlley_발표자료_v3.pptx`는 당시 기록으로 보존한다. 새로 내보낼 때는 이 SVG를 기준으로 생성한다.
폰트·아이콘·서비스 의미를 확인한 뒤 렌더링하고, 실제 적용 커밋은 VM `runtime/state.json`으로 확인한다.
