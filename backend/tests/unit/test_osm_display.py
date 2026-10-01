from fastapi.testclient import TestClient
from app.main import app
from app.services import road_service
from app.api import roads
from app.repositories.road_repository import RoadRepositoryError


def test_display_endpoint_keeps_motorway_and_wgs84(monkeypatch):
    monkeypatch.setattr(road_service, 'list_osm_display_roads', lambda bbox: [
        {'id':1,'highway':'motorway','name':None,
         'geometry':{'type':'LineString','coordinates':[[126.66,37.46],[126.67,37.47]]}}])
    response = TestClient(app).get('/api/osm-roads?bbox=126,37,127,38')
    assert response.status_code == 200
    assert response.json()['features'][0]['properties']['highway'] == 'motorway'
    assert response.json()['metadata']['display_only'] is True
    assert response.json()['metadata']['crs'] == 'EPSG:4326'


def test_invalid_display_bbox():
    assert TestClient(app).get('/api/osm-roads?bbox=bad').status_code == 400


def test_display_database_failure_is_sanitized(monkeypatch):
    def fail(_):
        raise RoadRepositoryError('private detail')
    monkeypatch.setattr(roads,'get_osm_display_collection',fail)
    response = TestClient(app).get('/api/osm-roads')
    assert response.status_code == 503
    assert 'private' not in response.text
