# 공간 데이터베이스

`init/001_extensions.sql`은 빈 PostgreSQL 볼륨을 최초 생성할 때 PostGIS를
활성화한다. 애플리케이션 테이블·인덱스는
[backend/alembic](../backend/alembic)의 migration으로 관리한다.
기존 볼륨에서는 init SQL을 다시 실행하지 않으므로 schema 변경은 Alembic으로 적용한다.

현재 migration head는 0016이다. backend 시작 시 `alembic upgrade head`를
실행하며 기존 migration 이력은 제거하지 않는다.

거리·공간 분석은 EPSG:5179, API/GeoJSON은 EPSG:4326을 사용한다.
도로는 LineString, 건물은 MultiPolygon, 시설은 Point와 GiST 공간 인덱스를 사용한다.
상세 테이블은 [DB 설계](../docs/database-schema.md)를 참고한다.

데이터는 `postgis_data` 볼륨에 보존한다. 초기화·볼륨 삭제·원본 재적재는
백업과 대상 확인 없이 수행하지 않는다.
Git clone은 실제 공간 데이터를 복원하지 않는다.
