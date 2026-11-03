# 2026-11-03 VM 배포 검증 기록

이 기록은 한국 시간 2026-11-03 15:11에 완료한 배포 결과다.
이후 문서 커밋이나 전달본 갱신은 이 시점의 실행 이미지 재배포를 뜻하지 않는다.
현재 실행 버전은 VM `runtime/state.json`과 `runtime/update.py status`로 확인한다.

## 적용한 소스와 전달본

| 항목 | 확인값 |
| --- | --- |
| 배포 전 실행 소스 | `f9b09e2e0f144d1ae9a93ad9584c293542f92a60` |
| 적용한 실행 소스 | `e2f16a5b9426a3927340bd520d27f9f5e639f6f6` |
| 당시 GitHub·GitLab 전달본 게시 커밋 | `6412bdf54d4495f35196993dd1a7f51f34566f50` |
| 당시 적용 압축파일 SHA-256 | `34dc9f3f181fa25b4dbd450ee1c2207b6deb6747b22e52651b6e8104dbf5ee16` |
| 압축파일 내부 실행 코드·문서 | 407개 파일, manifest·개별 해시 검증 |
| DB 스키마 | 배포 전후 `0016` |

관리자 SSH 비밀번호를 터미널에 직접 입력해 인증했다. 비밀번호는 파일·명령 인수·로그에 보관하지 않았다.
PC AI 전용 키는 터널용이며 관리자 셸 실행에 사용할 수 없음을 확인했다.
검토한 기존 updater를 사용해 DB 백업·체크섬 검증 후 backend와 frontend를 빌드·교체했다.
이전 이미지·복구 체크포인트를 유지했고 완료 후 미해결 `pending.json`이 없음을 확인했다.

## DB·비공개 설정 보존

배포 전후 DB 컨테이너 ID·시작 시각·마운트·스키마가 일치했다.
비공개 환경파일·TLS·빌드 설정 총 8개 파일의 해시와 서비스 환경변수,
이미지 참조를 제외한 실행 설정도 일치했다. 실제 비밀값과 파일 내용은 공개하지 않는다.
DB 백업은 VM의 접근 제한된 `private/updates/` 체크포인트에 보관하고 SHA-256을 확인했다.

공간 테이블의 실제 행 수를 배포 전후 비교해 모두 동일함을 확인했다.
이 수치는 아래 점검 시점의 값이며 이후 데이터 갱신의 고정 기대값이 아니다.

| 테이블 | 행 수 |
| --- | ---: |
| buildings | 38,543 |
| cctvs | 1,698 |
| help_points | 17 |
| osm_display_roads | 3,741 |
| pedestrian_references | 350 |
| places | 28 |
| public_crosswalks | 98 |
| road_safety_segments | 36,360 |
| road_segments | 16,587 |
| streetlights | 5,313 |

## 동작 확인

- 외부 HTTPS 진입 페이지와 JS/CSS가 HTTP 200으로 응답했다.
  새 JS에서 조건 분석 상태 자동 복구 코드가 제공됨을 확인했다.
- 내부 HTTPS는 보관한 서버 인증서로 검증했고 HTTP→HTTPS 이동도 통과했다.
  외부 응답 검사는 자체 서명 인증서의 공개 신뢰 검증과 구분했다.
- DB health는 PostgreSQL/PostGIS 연결 정상, 조건 분석 상태의 enabled/configured/available은 모두 true였다.
- PC 모델은 Gemma E2B·Whisper small CPU·Laya ONNX CPU가 준비 상태였다.
  중단되어 있던 PC AI 터널 관리자를 명시적으로 기동해 VM 연결을 복구했다.
- 실제 Laya 요청에서 모델 `laya-b3522f4d7939`와 8개 카드 응답을 확인했다.
  가로등·CCTV·계단 회피·건널목 회피·야간 조건이 적용됐다.
- `주안역에서 인천사랑병원까지 최단거리로 안내해줘`를 실제 Gemma에 요청했다.
  `gemma4:e2b-it-qat` 응답으로 후보 2개와 선택 경로를 받았으며 WGS84 LineString을 확인했다.
  후보 수와 좌표 수는 API 응답 검증이며 화면의 중복 경로 표시 정책과 구분한다.
- 날씨 API는 forecast_status=available, theme_source=official_solar였다.

Whisper 준비·VM 연결까지 확인했으며 이 배포에서 실제 마이크 녹음·전사 정확도와 전체 브라우저 UI 테스트는 실행하지 않았다.
모델 준비 상태·API 성공을 현장 통행 안전이나 전체 입력 정확도의 보장으로 해석하지 않는다.

검증 로그는 로컬 `output/deployment/`, 보존 비교 결과는 VM `private/deployment-audits/`에 비공개로 보관한다.
후속 배포는 [배포 안내](../deployment/README.md), 반복 점검은 [체크리스트](deployment-checklist.md)를 따른다.
