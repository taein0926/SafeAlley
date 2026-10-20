# 날씨와 낮·밤 판정

## 수집 → DB → 화면

data_pipeline/collectors/weather.py + weather_worker.py → loaders/weather.py → DB.
FastAPI /api/weather는 DB 캐시만 읽으며 웹 요청마다 공식 API를 호출하지 않습니다.

| 자료 | 기준 | 수집 |
| --- | --- | --- |
| KMA getVilageFcst | 주안역 대표 격자 55,124 | 시작 즉시, 02/05/08/11/14/17/20/23시 발표 후 15분(KST) |
| KASI getAreaRiseSetInfo | 인천 당일 일출·일몰 | 시작 즉시, 한국시간 자정 |

15분은 최신 발표본 제공을 기다리는 운영 여유입니다. 실패한 출처만 5분 후 재시도합니다.
기존 캐시는 유지하고 절전 복귀 시 최신 회차를 수집합니다.
반환된 시간별 예보의 미래 범위를 저장하며 현재 시각을 가운데 둔 과거/미래 값을 생성하지 않습니다.
TMP 기온, WSD 풍속, SKY 하늘 상태, PTY 강수 형태, POP 강수 확률을 사용합니다.
사용자 GPS/목적지가 아니라 대표 고정 격자 기준이며 다른 기관 예보로 대체하지 않습니다.

## 설정과 확인

로컬 .env: KMA_SERVICE_KEY, KASI_SERVICE_KEY(서비스별 승인 키), KASI_LOCATION=인천.
현재 VM의 수집 키·격자·지역 설정은 `private/service-env/weather.env`에서 관리한다.
KMA_GRID_NX/NY는 둘 다 공란이면 55,124를 산출합니다.
키를 VITE_*, Git, 인증 URL/로그에 넣지 않습니다.

아래는 소스가 있는 로컬 개발 환경 명령이며 현재 VM에서 실행하지 않는다.

```powershell
docker compose up -d --build weather
# 즉시 별도 수집이 필요한 경우만
docker compose --profile tools run --rm pipeline collect-weather
Invoke-RestMethod 'http://localhost:8000/api/weather?departure_time=22:00'
```

현재 VM의 코드 업데이트는 [배포 도구](../deployment/README.md)의 `update --archive`를 사용한다.
VM에서 키만 변경했다면 비공개 `weather.env`를 편집한 뒤 고정 설정으로 weather만 재생성한다.
키를 새 압축본에 넣거나 과거 `.env`·Compose 파일을 복사하지 않는다.

```bash
docker compose -p safealley-deploy -f ~/safealley-deploy/runtime/compose.json up -d --no-deps --no-build --pull never --force-recreate weather
python3 ~/safealley-deploy/runtime/update.py status
```

실제 예보 표시와 `forecast_status`는 브라우저의 `/api/weather` 응답으로 별도 확인한다.

forecast_status/provider, solar.provider/date, theme_source를 확인합니다.
날씨 migration은 0013/0014, 전체 head는 0016입니다.
[기상청 원천](https://www.data.go.kr/data/15084084/openapi.do),
[한국천문연구원 원천](https://www.data.go.kr/data/15012688/openapi.do).

## 조회·시간

오늘 한국시간의 해당 시간 예보만 표시합니다. 18:30은 18시 예보이며
없다고 다른 시간으로 대체하지 않습니다. 날짜 선택은 미지원입니다.
해당 시간대의 예보가 있으면 발표 후 경과 시간과 관계없이 표시합니다. 발표 후 6시간 초과로
숨기는 제한은 없으며, 발표 시각이나 갱신 지연 안내도 화면에 추가하지 않습니다.
API의 `forecast_status`는 `available`/`unavailable` 두 상태만 사용하며 폐기된 `stale`
상태와 해당 전용 대기 문구는 제거했습니다.
발표 시각이 미래이거나 누락된 비정상 자료는 표시하지 않습니다.
유효 예보와 당일 일출·일몰이 모두 있으면 15분 주기로 재조회합니다.
미연결/오류 또는 일출·일몰이 없으면 1분 후 재조회합니다.
적용 시각·분 단위 clock·날짜 변경·포커스/온라인 복귀에도 조회가 생길 수 있으므로
브라우저 요청이 항상 정확히 15분 간격인 것은 아닙니다. 외부 재수집과 웹 재조회는 독립입니다.

## 현재 화면과 테마

검색 버튼 아래에 배경 상자 없는 두 줄을 중앙 정렬합니다.
상단 구분선 없이 여백으로 버튼 영역과 구분하며, 버튼 하단부터 날씨 내용까지와
날씨 내용부터 영역 하단까지의 간격은 각각 10px입니다.

- 현재 미추홀구 MM/DD HH:mm 기준의 예보입니다.
- 검색 성공 후 기준 시간이 적용되면 요청하신 … 으로 바뀝니다.
  편집/대기/실패는 마지막 성공 기준을 덮어쓰지 않습니다.
- 공식 기상청 심볼+문구 로고 / 날씨 텍스트 / 기온 / 풍속.
  날씨·바람 픽토그램은 표시하지 않습니다.
- 없는 자료는 자동 재조회 상태로 표시하며 오류에 비밀정보를 노출하지 않습니다.

지도/routing은 같은 당일 일출·일몰을 사용합니다. 일출 이상~일몰 미만이 낮이며
자료가 없으면 06–20시 낮 fallback을 명시합니다. 낮에는 가로등을 비용/추천에서 제외하고
CCTV/안전시설 비율을 재정규화합니다. 시설 토글은 별개이며 UI 흰 테마는 밤에도 유지합니다.
예보는 실제 조도·시설 작동·침수·결빙·통행 안전을 보장하지 않습니다.
합성 예보는 [UI 테스트](testing.md)에만 사용합니다.
