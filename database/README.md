# Database

`init/`에는 빈 PostgreSQL 데이터 볼륨을 최초 생성할 때 실행할 최소 초기화 SQL만 둡니다.

PostGIS extension은 `init/001_extensions.sql`에서 활성화합니다. 애플리케이션 테이블은 기존 volume에도 반복 적용할 수 있도록 `backend/alembic/` migration으로 관리합니다.

Phase 2의 `road_segments`는 `geometry(LineString, 5179)`와 GiST 공간 인덱스를 사용합니다.
