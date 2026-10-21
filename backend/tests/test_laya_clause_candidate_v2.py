import pytest
from app.schemas.intent_preview import CARD_ORDER
from app.services.laya_preview_service import map_hybrid_cards
from app.services.laya_clause_candidate import refine_clause_cards
from app.services.laya_clause_candidate_v2 import refine_clause_cards_v2

def result(query,**choices):
 body={'answers':{f:{'type':'choice','choice':choices.get(f,'skip'),'confidence':.99} for f in CARD_ORDER}}
 cards=refine_clause_cards(body,query,map_hybrid_cards(body,query))
 return {c.factor:c for c in refine_clause_cards_v2(body,query,cards)}

@pytest.mark.parametrize('term,factor',[('안전시설','safety'),('계단','stairs'),('가로등','streetlight'),('횡단보도','crossing'),('육교','bridge')])
def test_open_list_only_pending(term,factor):
 cards=result(f'공원까지 CCTV가 많고 {term}과',cctv='apply',**{factor:'apply' if factor not in {'stairs','crossing'} else 'avoid'})
 assert cards[factor].judgment=='pending'
 assert cards['cctv'].judgment=='apply'

@pytest.mark.parametrize('q',[
 '가로등과 CCTV가 많은 게 무슨 뜻인지 설명해주세요',
 '밝은 길의 의미를 설명해줘',
 '계단 회피의 정의를 알려줘',
])
def test_explanation_not_navigation(q):
 cards=result(q,streetlight='apply',cctv='apply',stairs='avoid')
 assert all(c.state=='not_applied' for c in cards.values())

def test_explanation_does_not_cancel_real_navigation():
 cards=result('학교까지 CCTV가 많은 길로 안내해줘. 추천 이유도 설명해줘',cctv='apply')
 assert cards['cctv'].state=='applied'

@pytest.mark.parametrize('factor,noun',[('streetlight','가로등'),('cctv','CCTV'),('safety','안전시설'),('distance','최단거리')])
def test_last_direct_cancellation(factor,noun):
 cards=result(f'집까지 {noun} 우선으로 가고 {noun}은 빼고 가줘',**{factor:'apply'})
 assert cards[factor].state=='not_applied'

def test_cancellation_does_not_cancel_other_factor():
 cards=result('학교까지 가로등과 CCTV가 많고 가로등은 빼고 가줘',streetlight='apply',cctv='apply')
 assert cards['streetlight'].state=='not_applied' and cards['cctv'].state=='applied'

def test_stairs_exclusion_is_not_cancelled():
 cards=result('계단은 빼고 CCTV 많은 길로 안내해줘',stairs='avoid',cctv='apply')
 assert cards['stairs'].state=='applied'

def test_previous_completed_factor_not_erased_by_open_repetition():
 cards=result('가로등이 많은 길로 안내해줘. 가로등과',streetlight='apply')
 assert cards['streetlight'].state=='applied'
