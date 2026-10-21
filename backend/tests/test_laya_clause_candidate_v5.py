import pytest
from app.schemas.intent_preview import CARD_ORDER, ConditionCard
from app.services.laya_clause_candidate_v5 import refine_clause_cards_v5

def result(q, raw='skip'):
    cards=[ConditionCard(factor=f,state='applied' if f=='streetlight' and raw=='apply' else 'not_applied',judgment=raw if f=='streetlight' else 'skip',direction='maximize' if f=='streetlight' and raw=='apply' else None) for f in CARD_ORDER]
    return {c.factor:c for c in refine_clause_cards_v5({},q,cards)}

@pytest.mark.parametrize('q',[
 '학교까지 가로등이 적은 구간은 피해서 안내해줘',
 '23시 35분에 학교까지 가로등이 적은 구간은 피해서 안내해줘',
 '집까지 조명이 없는 길은 피해서 안내해주세요',
])
def test_complete_inverse(q):
    assert result(q)['streetlight'].judgment=='apply'

@pytest.mark.parametrize('q',[
 '공원까지 가로등이 적은 곳은 피하지 않아도 돼',
 '조명이 없는 길은 피하고 싶지 않아',
 '가로등이 적은 곳은 피해서 안 가고 싶어',
 '가로등이 적은 곳은 피해서 가지 마',
])
def test_negative_even_if_model_positive(q):
    assert result(q,'apply')['streetlight'].judgment=='skip'

@pytest.mark.parametrize('tail',['피','피하','피해','피하지','피하고','피하고 싶','피하고 싶지'])
def test_partial_never_activates(tail):
    assert result('도서관까지 가로등이 적은 곳은 '+tail,'apply')['streetlight'].judgment=='pending'

def test_later_condition_not_overwritten():
    assert result('가로등이 적은 곳은 피해서 가줘. 가로등은 빼고 안내해줘')['streetlight'].judgment=='skip'

def test_explanation_not_activated():
    assert result('가로등이 적은 곳은 피해서라는 말의 의미를 설명해줘')['streetlight'].judgment=='skip'

def test_no_other_card_changes():
    assert all(c.judgment=='skip' for f,c in result('가로등이 적은 길은 피해서 안내해줘').items() if f!='streetlight')
