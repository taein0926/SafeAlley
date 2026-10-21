from datetime import time
from types import SimpleNamespace
import pytest
from app.services.laya_departure_clock import explicit_departure_clock
from app.services import laya_preview_service as service
from app.schemas.intent_preview import CARD_ORDER

@pytest.mark.parametrize('query,status,clock',[
 ('21시에 도화역에서 출발해','apply',time(21)),
 ('23시에 CCTV 많은 길로 가고 싶어','apply',time(23)),
 ('21:30에 도화역에서 도서관까지 가줘','apply',time(21,30)),
 ('00:15에 출발할래','apply',time(0,15)),
 ('밤 아홉 시에 출발','apply',time(21)),
 ('오후 2시 반에 출발','apply',time(14,30)),
 ('오전 12시에 출발','apply',time(0)),
 ('낮 2시에 안내해줘','apply',time(14)),
 ('21시가 아니라 23시에 출발','apply',time(23)),
 ('21시에 출발해서 23시까지 도착하고 싶어','apply',time(21)),
 ('21시까지 도착하고 싶어','skip',None),
 ('도착 시간은 23시야','skip',None),
 ('21시까지 도착이 아니라 23시로 바꿔줘','skip',None),
 ('21시 또는 23시에 출발','pending',None),
 ('9시에 출발','pending',None),
 ('25시에 출발','pending',None),
 ('21시 65분에 출발','pending',None),
 ('21시','apply',time(21)),
 ('21','absent',None),
 ('21시식당에서 도서관까지','absent',None),
 ('도로 123번지에서 출발','absent',None),
 ('계단을 피하고 CCTV 많은 길로 가줘','absent',None),
])
def test_explicit_clock_scope(query,status,clock):
 assert explicit_departure_clock(query)==(status,clock)

def native(**choices):
 return {'answers':{f:{'type':'choice','choice':choices.get(f,'skip'),'confidence':.99} for f in CARD_ORDER}}

@pytest.mark.parametrize('query,expected',[
 ('21시에 가로등 많은 길로 안내해줘','night'),
 ('23시에 CCTV 많은 길로 가줘','night'),
 ('오후 2시에 CCTV 많은 길로 가줘','day'),
 ('05:59에 출발해','night'),('06:00에 출발해','day'),
 ('19:59에 출발해','day'),('20:00에 출발해','night'),
 ('21시가 아니라 14:00에 출발해','day'),
])
def test_repair_only_time_and_no_fake_confidence(monkeypatch,query,expected):
 monkeypatch.setattr(service,'resolve_route_time',lambda clock:SimpleNamespace(is_night=clock<time(6) or clock>=time(20)))
 data=native(cctv='apply');before=repr(data)
 baseline={c.factor:c for c in service.map_cards(data,query)}
 cards={c.factor:c for c in service.map_hybrid_cards(data,query)}
 assert cards['time'].period==expected and cards['time'].state=='applied'
 assert cards['time'].confidence is None
 assert cards['cctv'].judgment==baseline['cctv'].judgment
 assert repr(data)==before

def test_arrival_does_not_become_departure(monkeypatch):
 monkeypatch.setattr(service,'resolve_route_time',lambda clock:pytest.fail('No departure to resolve'))
 cards={c.factor:c for c in service.map_hybrid_cards(native(time='night'),'21시까지 도착하고 싶어')}
 assert cards['time'].judgment=='skip' and cards['time'].period is None

def test_uses_same_solar_policy_as_actual_routing(monkeypatch):
 called=[]
 def official(clock):
  called.append(clock);return SimpleNamespace(is_night=True)
 monkeypatch.setattr(service,'resolve_route_time',official)
 cards={c.factor:c for c in service.map_hybrid_cards(native(),'18:30에 출발할래')}
 assert called==[time(18,30)] and cards['time'].period=='night'

def test_ambiguous_clock_remains_pending(monkeypatch):
 monkeypatch.setattr(service,'resolve_route_time',lambda clock:pytest.fail('Ambiguous departure'))
 cards={c.factor:c for c in service.map_hybrid_cards(native(time='night'),'21시 또는 23시에 출발해')}
 assert cards['time'].judgment=='pending' and cards['time'].period is None
