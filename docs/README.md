# 문서 안내

현재 사용 문서는 코드와 함께 갱신합니다. 제거된 UI/이전 DB·저정밀 좌표 기반 결과와
낡은 품질 전달 기록은 정리했습니다. 현재 검증 절차는 테스트·평가 도구를 따릅니다.

현재 VM은 `runtime/`(고정 실행 설정), `private/`(환경설정·인증서·복구 백업),
`packages/`(현재·직전 소스 압축본) 구조입니다. 풀어놓은 소스는 서버에 상시 보관하지 않습니다.
VM 운영·한 명령 업데이트의 정본은 [서버 배포](../deployment/README.md)입니다.
저장소 루트의 `docker compose` 예시는 별도 표시가 없으면 소스가 있는 로컬 개발 환경용이며,
현재 VM에서는 `runtime/compose.json`과 `runtime/update.py`를 사용합니다.

## 현재 안내

서비스 구성도 편집 원본은 [SVG](assets/service-architecture.svg)이며 소스 전달본에도 포함합니다.
로컬 `output`의 발표자료·화면정의서·구성도 이미지는 Git/배포 소스 압축본과 별도로 관리합니다.
기존 `SafeAlley_발표자료_v3.pptx`와 이전 발표자료는 당시 상태의 보관 자료입니다.
현재 PC 모델 구성은 이 문서들과 SVG를 기준으로 확인하고 새 발표자료를 내보낼 때 반영합니다.

- [시작](../README.md), [아키텍처](architecture.md), [DB](database-schema.md), [라우팅](routing.md)
- [데이터 운영](data-pipeline.md), [건물 원천/매핑](building-data.md)
- [날씨](weather.md), [음성](speech-input.md), [소개창](welcome-intro.md)
- [검색 진행·후보/조건 카드](route-progress-floating-cards.md)
- [테스트](testing.md), [배포](../deployment/README.md), [배포 점검](deployment-checklist.md)
- [PC 모델 실행·VM 연결](../deployment/pc_ai/README.md), [공개 저장소 민감정보 점검](public-repository-security.md)
- [2026-11-03 VM 배포·DB/설정 보존 검증 기록](vm-deployment-2026-11-03.md)

## 데이터·해석·운영

- [보행/시설 품질 원칙](pedestrian-data-quality.md)
- [건널목과 육교](intersection-routing.md)
- [문장 해석·Laya/Jev](natural-language.md)
- [Laya 연결·모델·전환·복구](laya-preview-provider.md)
- [PC AI 연결/복구](ai-setup.md)
- [검색 처리와 캐시](ai-search-performance.md)

[출처/라이선스](../NOTICE.md), [수정 규칙](../AGENTS.md).
