# 배포 점검

이 목록은 현재 코드 기준이며 서버 검증 완료를 뜻하지 않습니다.
소스 push만으로 컨테이너·공간 DB·타일·모델·환경변수가 갱신되지 않습니다.

## 구성·접근

- [ ] 배포 source commit과 전달본 commit을 구분하고, 미커밋 파일은 패키지에 포함되지 않음을 확인한다.
- [ ] 현재 VM은 고정 runtime/compose.json + private/service-env이며 모델 요청은 PC로 전달한다.
- [ ] 로컬은 루트 Compose + deployment/compose.pc-ai.yml을 사용한다. 이전 GPU 템플릿과 혼용하지 않는다.
- [ ] 현재 모델은 gemma4:e2b-it-qat이며 Whisper small·Laya ONNX는 PC CPU에서 실행한다. 일반 템플릿의 gemma4:26b와 구분한다.
- [ ] VM backend의 Ollama :11439, Whisper :11440, Laya :18763과 실제 모델에 연결되는지 확인한다.
- [ ] PC 모델 준비 후 명시적으로 -ConnectVm -TunnelOnly를 실행하고 연결 관리자·지문·전용 키·재연결을 확인한다.
- [ ] VM 전달기의 바인딩/CIDR, 고정 Laya checkpoint 해시와 실제 8개 카드 응답을 확인한다. 모델 포트를 외부 공개하지 않는다.
- [ ] 현재 연결은 외부 HTTPS :21802 → VM :8081 → frontend :80(TLS). HTTP 자동 이동·자체 서명 인증서 경고·마이크 권한과 인증서 만료를 확인한다.
- [ ] runtime/update.py status로 버전·HTTPS·정적 파일·DB·PC 모델 endpoint를 확인하고 실제 검색/녹음은 별도 검증한다.
- [ ] 새 배포는 tar.gz와 .sha256을 함께 업로드하고 update --archive로 갱신한다. DB 볼륨·TLS·터널을 보존한다.
- [ ] Compose/DB init/Nginx 변경은 고정 운영 설정과 별도 검토한다. 새 migration은 검토 후 --allow-migration으로만 승인하며, DB 변경 후 자동 앱 롤백이 불가능할 수 있음을 확인한다.
- [ ] DB/backend/Ollama를 외부 공개하지 않는다. user_id는 로그인 기능이 아니다.
- [ ] 키·비밀번호·SSH 개인키·백업을 Git/소스 압축파일/로그에 넣지 않는다. [공개 저장소 점검](public-repository-security.md)에 따라 현재 파일·Git 이력·이전 압축본도 검사한다.
- [ ] 브라우저 OSM와 서버 Nominatim/KMA/KASI 접속 정책을 확인한다. Jev를 선택할 때만 입력 문장의 외부 TypeSafe 전송·과금을 확인한다.

## 데이터·모델

- [ ] 별도 백업·체크섬을 확인하고 빈 대상에만 복원한다. 기존 DB를 자동 삭제하지 않는다.
- [ ] Alembic current/heads는 0016 단일 head. 0011 등 기존 이력을 보존한다.
- [ ] 도로/계단/건널목·육교 연결·정밀 시설·건물·장소를 백업 원본과 대조한다.
- [ ] 과거 41 Way/77 segment는 해당 snapshot 기록이며 실제 대상 DB와 대조한다.
- [ ] demo가 운영 분석값을 덮어쓰지 않도록 설정·재분석을 확인한다.
- [ ] 원천·가공·타일·모델은 소스와 별도 관리하고 가로등 갱신 후 히트맵을 재생성한다.
- [ ] 실제 모델 준비/추론 후 ollama ps에서 GPU 사용을 확인한다.
- [ ] 실제 음성 응답의 `model=small`, `device=cpu`와 텍스트를 확인한다. 현재는 PC CPU 처리가 정상이며 STT_LOCAL_FALLBACK=false로 VM 대체 실행을 막는다.
- [ ] PC Whisper 모델 캐시·HTTPS 마이크·음성 크기/길이 제한과 동시 요청 제한을 확인한다.
- [ ] Jev는 별도 승인 키로만 활성화하고 실패를 성공처럼 처리하지 않는다.
- [ ] 현재 Laya 구성에서는 Jev를 비활성화하고 자동 유료 fallback이 없음을 확인한다. 복구 시 provider 설정 백업을 복원하고 backend만 재생성한다.
- [ ] PC pc-laya·pc-whisper와 Ollama 상태를 확인한다. PC 종료·절전·로그아웃 시 AI 중단을 고려하고 기존 외부 GPU 서비스는 재시작하지 않는다.
- [ ] KMA/KASI 수집/5분 재시도·DB 캐시를 확인한다.

## UI·운영

- [ ] 직접/문장/지도 좌표 검색과 공통 resolver를 검증한다.
- [ ] 최단/맞춤 보행 정책·동일 경로 dedup·strong avoid를 확인한다.
- [ ] UI 기본 50, 값 0/50/100과 stairs/crossing 0/0.5/1을 확인한다.
- [ ] 시설 통합 토글·건물 상세·경로 marker·2D/3D 선택 유지·소개창을 확인한다.
- [ ] 입력 중 조건 카드와 최종 조건을 구분하고 실패가 성공 날씨 기준을 덮어쓰지 않게 한다.
- [ ] routing/지도 일출·일몰 판정 및 명시 fallback을 확인한다.
- [ ] [전체 테스트](testing.md)와 production build; skip/fixture/live 범위를 구분한다.
- [ ] 운영 DB에 테스트 fixture를 실행하지 않는다.
- [ ] 배포 전 DB·설정 백업과 이전 이미지·소스 압축본을 보관하고 복원 연습을 한다. 풀어놓은 main-* 폴더를 다시 만들 필요는 없다.
- [ ] 현재 Nginx의 stream buffering off, query timeout 660초, 음성 8MB/180초를 유지한다. 외부 HTTP proxy를 추가하는 경우에도 같은 제한을 반영한다.
- [ ] 재부팅 후 컨테이너/터널 복구·동시 부하·로그/디스크를 확인한다.
- [ ] 이미지 롤백과 DB 복원은 별도이며 자동 downgrade/볼륨 삭제를 하지 않는다.
- [ ] 배포 성공 후 이미지 자동 정리가 현재·직전 복구 및 모든 컨테이너의 이미지를 보존하는지 확인한다. Workhub 등 다른 프로젝트·공유 이미지·볼륨·빌드 캐시는 정리하지 않는다. 수동 미리보기는 `runtime/update.py clean-images --dry-run`을 사용한다.
- [ ] 현재 VM의 앱 태그는 `safealley-release/<서비스>:한국일시-짧은커밋`, DB는 `safealley-release/database:postgres17-postgis3.5`에 digest를 고정한다. 운영·직전 복구 설정이 실제 동일 이미지 ID를 가리키는지 확인하며 이름 변경 때문에 DB를 교체하지 않는다.

[구성별 명령](../deployment/README.md).
