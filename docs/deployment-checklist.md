# 배포 점검

이 목록은 현재 코드 기준이며 서버 검증 완료를 뜻하지 않습니다.
소스 push만으로 컨테이너·공간 DB·타일·모델·환경변수가 갱신되지 않습니다.

## 구성·접근

- [ ] 배포 commit과 미커밋 포함 여부를 기록한다.
- [ ] VM/GPU: 루트 Compose + compose.vm.override.yml, 기존 GPU Ollama와 승인된 SSH 터널.
- [ ] 단일 GPU 대안: deployment/compose.yml + manage.py. VM override와 혼용하지 않는다.
- [ ] VM backend에서 host gateway 11435와 설정 모델 qwen3.6:35b에 접속할 수 있는지 확인한다.
- [ ] frontend loopback 8080에 승인된 포워딩/HTTPS·접근제어 proxy를 연결한다.
- [ ] DB/backend/Ollama를 외부 공개하지 않는다. user_id는 로그인 기능이 아니다.
- [ ] 키·비밀번호·SSH 개인키·백업을 Git/소스 ZIP/로그에 넣지 않는다.
- [ ] 브라우저 OSM와 서버 Nominatim/Jev/KMA/KASI 접속 정책을 확인한다.

## 데이터·모델

- [ ] 별도 백업·체크섬을 확인하고 빈 대상에만 복원한다. 기존 DB를 자동 삭제하지 않는다.
- [ ] Alembic current/heads는 0016 단일 head. 0011 등 기존 이력을 보존한다.
- [ ] 도로/계단/건널목·육교 연결·정밀 시설·건물·장소를 백업 원본과 대조한다.
- [ ] 과거 41 Way/77 segment는 해당 snapshot 기록이며 실제 대상 DB와 대조한다.
- [ ] demo가 운영 분석값을 덮어쓰지 않도록 설정·재분석을 확인한다.
- [ ] 원천·가공·타일·모델은 소스와 별도 관리하고 가로등 갱신 후 히트맵을 재생성한다.
- [ ] 실제 모델 준비/추론 후 ollama ps에서 GPU 사용을 확인한다.
- [ ] Whisper CPU 모델 캐시·HTTPS 마이크·자원 제한을 확인한다.
- [ ] Jev는 별도 승인 키로만 활성화하고 실패를 성공처럼 처리하지 않는다.
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
- [ ] 배포 전 백업과 이전 이미지·소스·설정을 보관하고 복원 연습을 한다.
- [ ] 외부 proxy에도 stream buffering off, query timeout 660초, 음성 8MB/180초를 반영한다.
- [ ] 재부팅 후 컨테이너/터널 복구·동시 부하·로그/디스크를 확인한다.
- [ ] 이미지 롤백과 DB 복원은 별도이며 자동 downgrade/볼륨 삭제를 하지 않는다.

[구성별 명령](../deployment/README.md).
