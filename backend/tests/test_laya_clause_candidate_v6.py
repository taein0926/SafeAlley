import pytest
from app.schemas.intent_preview import CARD_ORDER, ConditionCard
from app.services.laya_clause_candidate_v6 import refine_clause_cards_v6

def result(q):
    cards=[ConditionCard(factor=f,state='applied',judgment='night' if f=='time' else 'avoid' if f in ('stairs','crossing','bridge') else 'apply',period='night' if f=='time' else None,direction=None if f=='time' else 'avoid' if f in ('stairs','crossing','bridge') else 'maximize') for f in CARD_ORDER]
    return {c.factor:c for c in refine_clause_cards_v6({},q,cards)}

@pytest.mark.parametrize('tail',['됩니다','됩니다.','됩니다만 CCTV 많은 길로 가줘','괜찮아요','상관없어요','무방해요'])
def test_completed_permission(tail):
    assert result('학교까지 가로등이 적은 길은 피하지 않아도 '+tail)['streetlight'].judgment=='skip'

@pytest.mark.parametrize('q',[
 '조명이 부족한 구간은 피해서라는 표현의 의미를 설명해줘',
 '가로등이 없는 길은 피해서라는 말은 무슨 뜻인지 알려줘',
 '계단 회피의 의미를 설명해줘',
])
def test_explanation_does_not_resurrect_cards(q):
    assert all(c.judgment=='skip' for c in result(q).values())

@pytest.mark.parametrize('q',[
 '가로등이 적은 길은 피해서 안내해줘',
 '가로등이 적은 곳은 피하지 않아도 됩니다. 그래도 가로등 많은 길로 안내해줘',
 '가로등이 적은 곳은 피하지 않아도 안 됩니다. 피해 주세요',
 '조명이 없는 길은 피하고 싶어요',
 '가로등 많은 길로 안내해줘. 왜 골랐는지 설명해줘',
])
def test_navigation_not_cancelled(q):
    assert result(q)['streetlight'].judgment=='apply'

def test_other_conditions_preserved_on_permission():
    c=result('가로등이 적은 곳은 피하지 않아도 됩니다. CCTV 많은 길로 안내해줘')
    assert c['streetlight'].judgment=='skip' and c['cctv'].judgment=='apply'
