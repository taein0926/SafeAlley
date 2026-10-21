"""Wrong-positive native fixtures exercise the complete Laya-only pipeline.

No training, external inference, Jev calls, database, or example edits.
"""
from datetime import time
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.schemas.intent_preview import CARD_ORDER
from app.services import laya_preview_service as service


@pytest.fixture
def analyze(monkeypatch):
    monkeypatch.setenv('LAYA_PREVIEW_ENABLED', 'true')
    get_settings.cache_clear()
    monkeypatch.setattr(service, 'resolve_route_time', lambda clock:
        SimpleNamespace(is_night=clock < time(6) or clock >= time(20)))

    def run(query, **native):
        class Reply:
            def raise_for_status(self):
                pass

            def json(self):
                return dict(query=query, version=123,
                    checkpoint_sha256=get_settings().laya_checkpoint_sha256,
                    answers={f: dict(type='choice', choice=native.get(f, 'skip'), confidence=.99)
                             for f in CARD_ORDER})
        monkeypatch.setattr(service, 'monotonic_ns', lambda: 123)
        monkeypatch.setattr(service.httpx, 'post', lambda *a, **kw: Reply())
        return {c.factor: c for c in service.analyze_preview(query).conditions}

    yield run
    get_settings.cache_clear()


@pytest.mark.parametrize('query,excluded,active', [
    ('계단 피하지 않고 건널목 피해서 갈래', 'stairs', 'crossing'),
    ('계단은 피하지 말고 건널목은 피해서 가줘', 'stairs', 'crossing'),
    ('건널목 피하지 않고 계단 피해서 갈래', 'crossing', 'stairs'),
    ('육교는 피하지 않아도 돼. 계단을 피해서 가줘', 'bridge', 'stairs'),
    ('계단을 피해서 가줘. 건널목은 피하지 않아도 돼', 'crossing', 'stairs'),
])
def test_explicit_rejection_overrides_wrong_native_positive(analyze, query, excluded, active):
    cards = analyze(query, **{excluded: 'avoid', active: 'avoid'})
    rejected = cards[excluded]
    assert (rejected.state, rejected.judgment) == ('not_applied', 'skip')
    assert rejected.direction is None and rejected.confidence is None
    assert cards[active].state == 'applied' and cards[active].direction == 'avoid'


def test_reported_complete_input_preserves_other_conditions(analyze):
    query = ('밤 9시에 인천비즈니스고등학교에서 인천청인학교까지 가로등, CCTV 많은 길로 안내해. '
             '계단 피하지 않고 건널목 피해서 갈래.')
    cards = analyze(query, streetlight='apply', cctv='apply', stairs='avoid', crossing='avoid', time='night')
    assert {f for f, c in cards.items() if c.state == 'applied'} == {'streetlight', 'cctv', 'crossing', 'time'}
    assert cards['stairs'].judgment == 'skip'
    assert cards['time'].period == 'night'


@pytest.mark.parametrize('factor,positive_query,rejection,choice', [
    ('distance', '최단 거리로 가줘', '최단 거리는 고려하지 말고 가로등 많은 길로 가줘', 'apply'),
    ('cctv', 'CCTV 많은 길로 가줘', 'CCTV는 고려하지 말고 가로등 많은 길로 가줘', 'apply'),
    ('streetlight', '가로등 많은 길로 가줘', '가로등은 고려하지 말고 CCTV 많은 길로 가줘', 'apply'),
    ('safety', '안전시설 가까운 길로 가줘', '안전시설은 고려하지 말고 CCTV 많은 길로 가줘', 'apply'),
    ('stairs', '계단 피해서 가줘', '계단은 피하지 않고 CCTV 많은 길로 가줘', 'avoid'),
    ('crossing', '건널목 피해서 가줘', '건널목은 피하지 않고 CCTV 많은 길로 가줘', 'avoid'),
    ('bridge', '육교 피해서 가줘', '육교는 피하지 않고 CCTV 많은 길로 가줘', 'avoid'),
])
def test_positive_negative_pairs(analyze, factor, positive_query, rejection, choice):
    assert analyze(positive_query, **{factor: choice})[factor].state == 'applied'
    assert analyze(rejection, **{factor: choice})[factor].state == 'not_applied'


def test_later_positive_same_factor_is_not_cancelled(analyze):
    query = '계단은 피하지 않아도 돼. 아니 계단을 피해서 가줘'
    cards = analyze(query, stairs='avoid')
    assert cards['stairs'].state == 'applied' and cards['stairs'].direction == 'avoid'


def test_low_lighting_avoidance_remains_a_positive_preference(analyze):
    cards = analyze('가로등이 적은 길은 피해서 가줘', streetlight='apply')
    assert cards['streetlight'].state == 'applied'


def test_unfinished_input_remains_pending(analyze):
    assert analyze('계단을', stairs='avoid')['stairs'].state == 'analyzing'
