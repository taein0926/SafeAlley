import pytest
from app.schemas.intent_preview import CARD_ORDER
from app.services.laya_preview_service import map_hybrid_cards
from app.services.laya_clause_candidate import refine_clause_cards
from app.services.laya_clause_candidate_v2 import refine_clause_cards_v2
from app.services.laya_clause_candidate_v3 import refine_clause_cards_v3

def result(q,**choices):
 b={'answers':{f:{'type':'choice','choice':choices.get(f,'skip'),'confidence':.99} for f in CARD_ORDER}}
 c=refine_clause_cards(b,q,map_hybrid_cards(b,q));c=refine_clause_cards_v2(b,q,c)
 return {x.factor:x for x in refine_clause_cards_v3(b,q,c)}

@pytest.mark.parametrize('noun,factor,choice',[
 ('계단 없이','stairs','avoid'),('건널목을 적게 지나는','crossing','minimize'),('가로등이 많은','streetlight','apply'),('CCTV가 많은','cctv','apply'),
])
def test_request_before_explanation_preserved(noun,factor,choice):
 q=f'학교까지 {noun} 길로 안내해줘. {noun} 이유를 설명해줘'
 assert result(q)[factor].judgment==choice

def test_original_stairs_reason():
 c=result('학교까지 계단 없이 안내해줘. 계단을 피한 이유를 설명해줘')
 assert c['stairs'].judgment=='avoid'

@pytest.mark.parametrize('ending',['고려하지 마','적어도 괜찮아','없어도 괜찮으니 안내해줘'])
def test_shared_negative_predicate(ending):
 c=result('학교까지 가로등과 CCTV가 '+ending,streetlight='apply',cctv='apply')
 assert c['streetlight'].judgment==c['cctv'].judgment=='skip'

def test_preserve_other_requested_factor():
 c=result('가로등과 CCTV를 고려하지 마. 계단 없는 길로 안내해줘',streetlight='apply',cctv='apply',stairs='avoid')
 assert c['stairs'].judgment=='avoid' and c['streetlight'].judgment==c['cctv'].judgment=='skip'

def test_later_reintroduced_factor_wins():
 c=result('학교까지 가로등과 CCTV를 고려하지 마. CCTV가 많은 길로 안내해줘',streetlight='apply',cctv='apply')
 assert c['streetlight'].judgment=='skip' and c['cctv'].judgment=='apply'

def test_plain_explanation_does_not_create_route_conditions():
 c=result('계단을 피한 이유를 설명해줘')
 assert all(x.state!='applied' for x in c.values())

def test_obstacle_exclusion_remains_avoidance():
 c=result('계단과 육교는 빼고 CCTV 많은 길로 안내해줘',stairs='avoid',bridge='avoid',cctv='apply')
 assert c['stairs'].judgment=='avoid' and c['bridge'].judgment=='avoid'

def test_ordinary_shared_positive_not_cancelled():
 c=result('학교까지 가로등과 CCTV가 많은 길로 안내해줘',streetlight='apply',cctv='apply')
 assert c['streetlight'].judgment==c['cctv'].judgment=='apply'

def test_later_movement_request_not_discarded_as_meta():
 c=result('CCTV 많은 길로 안내해줘. 계단 없는 길로 안내해주고 이유도 설명해줘',cctv='apply',stairs='avoid')
 assert c['stairs'].judgment=='avoid' and c['cctv'].judgment=='apply'
