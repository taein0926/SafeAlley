import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings
from app.services import laya_preview_service as service
from app.services.jev_preview_service import PreviewUnavailable
from app.schemas.intent_preview import CARD_ORDER

@pytest.fixture(autouse=True)
def isolated_time_policy(monkeypatch):
 from types import SimpleNamespace
 from datetime import time
 monkeypatch.setattr(service,'resolve_route_time',lambda clock:SimpleNamespace(is_night=clock<time(6) or clock>=time(20)))

def body(**choices):
 return dict(answers={f:dict(type='choice',choice=choices.get(f,'skip'),confidence=.99) for f in CARD_ORDER})

def test_hybrid_recovers_completed_lighting_not_trailing_crossing(monkeypatch):
 monkeypatch.setattr(service.httpx,'post',lambda *a,**kw:pytest.fail('No paid/network call in pure mapping'))
 cards={c.factor:c for c in service.map_hybrid_cards(body(streetlight='pending',crossing='pending'),'가로등이 많고 횡단보도는')}
 assert cards['streetlight'].judgment=='apply' and cards['streetlight'].state=='applied'
 assert cards['crossing'].judgment=='pending' and cards['crossing'].state=='analyzing'

def test_hybrid_keeps_pilot_recovery_and_does_not_invent_time():
 cards={c.factor:c for c in service.map_hybrid_cards(body(),'빠르게 가고 싶어')}
 assert cards['distance'].judgment=='apply'
 assert cards['time'].state=='not_applied'

def test_hybrid_incomplete_does_not_apply_bare_obstacle():
 cards={c.factor:c for c in service.map_hybrid_cards(body(stairs='avoid'),'계단을')}
 assert cards['stairs'].state=='analyzing' and cards['stairs'].judgment=='pending'

@pytest.mark.parametrize('query,factor',[
 ('건널목 대신 육교로 갈래.','crossing'),
 ('횡단보도 대신 지하도로 가줘','crossing'),
 ('계단 대신 평지로 가고 싶어','stairs'),
 ('육교 대신 건널목으로 갈래','bridge'),
 ('건널목 대신 육교를 이용할래','crossing'),
])
def test_route_substitution_excludes_only_named_obstacle(query,factor):
 data=body(bridge='apply') if factor!='bridge' else body()
 cards={c.factor:c for c in service.map_hybrid_cards(data,query)}
 assert cards[factor].judgment=='avoid' and cards[factor].state=='applied'
 assert cards['safety'].state=='not_applied'

@pytest.mark.parametrize('query',[
 '육교로 갈래', '건널목 대신', '건널목 대신 육교',
 '건널목 대신 육교로 가고 싶지 않아', '건널목 대신 육교로 가지 마',
 '건널목 대신 육교가 무슨 뜻이야', '건널목 대신 건널목으로 갈래',
 '건널목아파트에서 육교로 갈래',
 '건널목 대신 육교로 갈래. 건널목은 피하지 않아도 돼',
])
def test_no_substitution_avoidance_without_completed_request(query):
 assert service.explicit_pilot_choice(query,'crossing') is None

def test_original_comprehensive_request_all_eight():
 query='밤 9시에 인천비즈니스고등학교에서 인천청인학교까지 최단 거리로 안내해. 가로등, CCTV 많고 경찰서 주변인 길로 안내해. 계단 피하고 건널목 대신 육교로 갈래.'
 data=body(distance='apply',safety='apply',streetlight='apply',cctv='apply',stairs='avoid',bridge='apply',time='night')
 cards={c.factor:c for c in service.map_hybrid_cards(data,query)}
 assert all(c.state=='applied' for c in cards.values())
 assert cards['crossing'].direction=='avoid' and cards['bridge'].direction=='maximize'

def test_native_mapping_and_pending():
 cards={c.factor:c for c in service.map_cards(body(cctv='apply',stairs='avoid',crossing='pending',time='night'))}
 assert cards['cctv'].state=='applied' and cards['stairs'].direction=='avoid'
 assert cards['crossing'].state=='analyzing' and cards['time'].period=='night'
 assert cards['safety'].state=='not_applied'

@pytest.mark.parametrize('query,factor,expected',[
 ('빠르게 가고 싶어','distance','apply'),
 ('건널목을 피해서 가고 싶어','crossing','avoid'),
 ('육교와 계단을 피하고 CCTV가 많은 길로 안내해줘','bridge','avoid'),
 ('계단을 피하고','stairs','avoid'),
 ('횡단보도와 육교를 피해서 가줘','bridge','avoid'),
 ('층계를 피해서 가줘','stairs','avoid'),
])
def test_clear_request_recovery(query,factor,expected):
 data=body(cctv='apply');data['answers'][factor]['choice']='pending'
 cards={c.factor:c for c in service.map_cards(data,query)}
 assert cards[factor].state=='applied' and cards[factor].judgment==expected
 assert cards[factor].confidence is None
 assert data['answers'][factor]['choice']=='pending'
 assert cards['cctv'].judgment=='apply'

@pytest.mark.parametrize('query',[
 '육교와 계단을', '계단을 피', '계단을 피하지 않아도 돼',
 '계단은 많고 CCTV가 많은 길', '육교아파트에서 도서관까지 가줘',
 '계단에서 도서관까지 CCTV를 우선해줘',
 '계단이 있고 육교를 피해서 가줘',
 '계단과 육교는 피하지 말고 가줘',
])
def test_no_recovery_without_clear_local_stairs_request(query):
 cards={c.factor:c for c in service.map_cards(body(),query)}
 assert cards['stairs'].state=='not_applied'

def test_completed_clause_does_not_consume_next_bare_condition():
 cards={c.factor:c for c in service.map_cards(body(crossing='pending'),'계단을 피하고 횡단보도를')}
 assert cards['stairs'].judgment=='avoid'
 assert cards['crossing'].judgment=='pending'

@pytest.mark.parametrize('query',[
 '밤 10시에 도화역에서 수봉도서관까지 가로등이 많은 길로 안내해줘',
 'CCTV가 많은 길로 안내해줘',
 '경찰서에서 수봉도서관까지 가로등이 많은 길로 가줘',
 '안전시설은 고려하지 말고 가로등 많은 길로 가줘',
])
def test_unrequested_safety_is_not_applied(query):
 data=body(safety='apply',streetlight='apply',time='night')
 cards={c.factor:c for c in service.map_cards(data,query)}
 assert cards['safety'].state=='not_applied' and cards['safety'].judgment=='skip'
 assert cards['safety'].direction is None and cards['safety'].confidence is None
 assert cards['streetlight'].state=='applied' and cards['time'].period=='night'
 assert data['answers']['safety']['choice']=='apply','Do not mutate native response'

@pytest.mark.parametrize('query',[
 '안전시설이 가까운 길로 가줘',
 '경찰서 가까운 길로 안내해줘',
 '안전시설과 가깝고 가로등이 많은 길로 가줘',
 'CCTV가 많고 도움시설이 가까운 길로 가줘',
])
def test_explicit_safety_request_kept(query):
 cards={c.factor:c for c in service.map_cards(body(safety='apply'),query)}
 assert cards['safety'].state=='applied' and cards['safety'].direction=='maximize'
 assert cards['safety'].confidence==.99

def test_bare_safety_is_pending_and_no_forced_positive():
 cards={c.factor:c for c in service.map_cards(body(safety='apply'),'도화역에서 수봉도서관까지 안전시설은')}
 assert cards['safety'].state=='analyzing' and cards['safety'].judgment=='pending'
 cards={c.factor:c for c in service.map_cards(body(safety='skip'),'안전시설 가까운 길로 가줘')}
 assert cards['safety'].state=='not_applied','Do not invent positive native judgment'

@pytest.mark.parametrize('value',[True,float('nan'),2,-1])
def test_reject_bad_confidence(value):
 data=body();data['answers']['cctv']['confidence']=value
 with pytest.raises(PreviewUnavailable):service.map_cards(data)

def test_laya_dispatch_never_jev(monkeypatch):
 monkeypatch.setenv('INTENT_PREVIEW_PROVIDER','laya');get_settings.cache_clear()
 import app.api.intent_preview as api
 monkeypatch.setattr(api,'analyze_preview',lambda *a,**kw:pytest.fail('Jev called'))
 monkeypatch.setattr(service,'analyze_preview',lambda q:dict(query=q,model='laya-test',conditions=service.map_cards(body(cctv='apply'))))
 r=TestClient(app).post('/api/agent/intent-preview',json=dict(query='CCTV 많은 길'))
 assert r.status_code==200 and r.json()['model']=='laya-test'
 get_settings.cache_clear()

def test_default_provider_remains_jev(monkeypatch):
 monkeypatch.delenv('INTENT_PREVIEW_PROVIDER',raising=False);get_settings.cache_clear()
 assert get_settings().intent_preview_provider=='jev'
 get_settings.cache_clear()

def test_connection_failure_does_not_fallback(monkeypatch):
    import httpx
    monkeypatch.setenv('LAYA_PREVIEW_ENABLED','true');get_settings.cache_clear()
    urls=[]
    def fail(url,**kwargs):
        urls.append(url);raise httpx.ConnectError('offline')
    monkeypatch.setattr(service.httpx,'post',fail)
    with pytest.raises(PreviewUnavailable,match='Jev로 대체 호출하지 않습니다'):
        service.analyze_preview('CCTV 많은 길')
    assert urls==[get_settings().laya_preview_url+'/analyze']
    get_settings.cache_clear()

@pytest.mark.parametrize('field,value',[('checkpoint_sha256','wrong'),('version',999),('query','다른 문장')])
def test_reject_wrong_model_or_stale_response(monkeypatch,field,value):
    monkeypatch.setenv('LAYA_PREVIEW_ENABLED','true');get_settings.cache_clear()
    monkeypatch.setattr(service,'monotonic_ns',lambda:123)
    data=body(cctv='apply')|dict(query='CCTV 많은 길',version=123,checkpoint_sha256=get_settings().laya_checkpoint_sha256)
    data[field]=value
    class Reply:
        def raise_for_status(self):pass
        def json(self):return data
    monkeypatch.setattr(service.httpx,'post',lambda *a,**kw:Reply())
    with pytest.raises(PreviewUnavailable):service.analyze_preview('CCTV 많은 길')
    get_settings.cache_clear()
