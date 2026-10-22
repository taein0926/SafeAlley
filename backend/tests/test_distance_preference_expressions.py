"""Distance-only source corrections; model fixtures, no training or API charges."""
from datetime import time
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.schemas.intent_preview import CARD_ORDER
from app.services import laya_preview_service as laya, local_llm_service as llm


POSITIVE = [
    '가까운 거리 우선', '가까운거리우선', '최단거리로 안내해줘', '최단으로 가줘',
    '거리가 짧은 길로 가줘', '거리는 최대한 짧게', '걷는 거리를 줄이고 싶어',
    '이동 거리를 최소로 해줘', '최소한의 거리로 가고 싶어', '짧은 길이 좋아',
    '길이 짧았으면 좋겠어', '빠른 길로 안내해줘', '빨리 도착하고 싶어',
    '빠르게 가고 싶어', '지름길로 가줘', '덜 걷고 싶어', '적게 걷는 길로 가줘',
    '가까운 길로 가줘', '경찰서까지 거리가 짧은 길로 가줘',
    '가로등이 많고 가까운 거리 우선', '거리는 짧게, 경찰서가 가까운 길로 가줘',
]
NEGATIVE = [
    '최단거리는 필요 없어', '가까운 거리는 싫어', '최단거리 말고 CCTV 많은 길',
    '최단거리보다 안전한 길이 좋아', '짧은 길이 아니어도 괜찮아',
    '가까운 거리 우선 안 할래', '가까운 거리로 가고 싶지 않아', '거리는 상관없어',
    '경찰서에 가까운 길로 가줘', '병원과의 거리가 짧은 길로 가줘', '최단거리 뜻을 알려줘',
    '집까지 최단거리로 가고 CCTV 많은 길로 안내해줘. 최단거리는 빼고 가줘',
]


@pytest.fixture
def analyze(monkeypatch):
    monkeypatch.setenv('INTENT_PREVIEW_PROVIDER','laya')
    monkeypatch.setenv('LAYA_PREVIEW_ENABLED','true')
    get_settings.cache_clear()
    monkeypatch.setattr(laya,'resolve_route_time',lambda clock:
                        SimpleNamespace(is_night=clock<time(6) or clock>=time(20)))

    def run(query,**native):
        def fixture(url,*,json,**kwargs):
            body=dict(query=query,version=json['version'],
                      checkpoint_sha256=get_settings().laya_checkpoint_sha256,
                      answers={factor:dict(type='choice',choice=native.get(factor,'skip'),confidence=.99)
                               for factor in CARD_ORDER})
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:body)
        monkeypatch.setattr(laya.httpx,'post',fixture)
        return {card.factor:card for card in laya.analyze_preview(query).conditions}
    yield run
    get_settings.cache_clear()


@pytest.mark.parametrize('query',POSITIVE)
def test_explicit_short_trip_request_recovers_preview_omission(analyze,query):
    card=analyze(query)['distance']
    assert (card.state,card.direction)==('applied','minimize')


@pytest.mark.parametrize('query',NEGATIVE)
def test_rejection_and_facility_proximity_do_not_become_short_trip(analyze,query):
    assert analyze(query,distance='apply')['distance'].state=='not_applied'


@pytest.mark.parametrize('query',['적게 걷는 길로 가줘','가까운 길로 가줘'])
def test_distance_request_cannot_invent_cctv_or_crossing_conditions(analyze,query):
    cards=analyze(query,cctv='apply',crossing='minimize')
    assert {factor:card.direction for factor,card in cards.items() if card.state=='applied'}=={'distance':'minimize'}


def test_explicit_compound_conditions_are_preserved(analyze):
    cards=analyze('가까운 길로 가줘. CCTV 많고 건널목 적은 곳으로',cctv='apply',crossing='minimize')
    assert {factor:card.direction for factor,card in cards.items() if card.state=='applied'}=={
        'distance':'minimize','cctv':'maximize','crossing':'minimize'}


@pytest.mark.parametrize('query',POSITIVE)
def test_final_gemma_intent_uses_same_distance_correction(monkeypatch,query):
    monkeypatch.setattr(llm,'_request_ollama',lambda _: {'message':{'content':'{}'}})
    intent=llm._parse_route_intent_uncached(query)
    assert any(p.factor=='distance_m' and p.direction=='minimize' for p in intent.preferences)


@pytest.mark.parametrize('query',['가까운 거리 우선 안 할래','병원과의 거리가 짧은 길로 가줘',
                                 '집까지 최단거리로 가고 CCTV 많은 길로 안내해줘. 최단거리는 빼고 가줘'])
def test_final_parser_drops_false_distance_preference(monkeypatch,query):
    monkeypatch.setattr(llm,'_request_ollama',lambda _: {'message':{'content':json.dumps({
        'preferences':[{'factor':'distance_m','direction':'minimize'}]})}})
    intent=llm._parse_route_intent_uncached(query)
    assert not any(p.factor=='distance_m' for p in intent.preferences)


def test_reported_phrase_is_returned_by_preview_http_endpoint(analyze):
    analyze('가까운 거리 우선')
    response=TestClient(app).post('/api/agent/intent-preview',json={'query':'가까운 거리 우선'})
    assert response.status_code==200
    cards={card['factor']:card for card in response.json()['conditions']}
    assert cards['distance']['state']=='applied'
    assert cards['distance']['direction']=='minimize'
    assert all(card['state']=='not_applied' for factor,card in cards.items() if factor!='distance')
