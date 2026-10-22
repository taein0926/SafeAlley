"""Deployment regression at the browser-facing HTTP boundary; no external calls."""
from datetime import time
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.schemas.intent_preview import CARD_ORDER
from app.services import laya_preview_service as service


PREFIX = ('밤 9시에 인천비즈니스고등학교에서 인천청인학교까지 '
          '가로등, CCTV 많은 길로 안내해. ')
LIGHTING = dict(streetlight='apply', cctv='apply', time='night')
WRONG_OBSTACLES = dict(stairs='avoid', crossing='avoid')
EXAMPLE_GOLD = [
    dict(streetlight='apply', cctv='apply', crossing='avoid', time='night'),
    dict(streetlight='apply', cctv='apply', stairs='avoid', time='night'),
    dict(distance='apply', streetlight='apply', cctv='apply', safety='apply',
         stairs='avoid', crossing='avoid', bridge='apply', time='night'),
    dict(streetlight='apply', stairs='avoid', time='night'),
]


def browser_examples():
    source = (Path(__file__).resolve().parents[2] / 'frontend/src/App.tsx').read_text(encoding='utf-8')
    block = source.split('const SEARCH_EXAMPLES = [', 1)[1].split('] as const;', 1)[0]
    examples = re.findall(r'^\s*"(.+)",\s*$', block, re.M)
    assert len(examples) == len(EXAMPLE_GOLD) == 4
    return examples


@pytest.fixture
def preview(monkeypatch):
    import app.api.intent_preview as api

    monkeypatch.setenv('INTENT_PREVIEW_PROVIDER', 'laya')
    monkeypatch.setenv('LAYA_PREVIEW_ENABLED', 'true')
    get_settings.cache_clear()
    monkeypatch.setattr(api, 'analyze_preview', lambda *a, **kw: pytest.fail('Jev must not be called'))
    monkeypatch.setattr(service, 'resolve_route_time', lambda clock:
                        SimpleNamespace(is_night=clock < time(6) or clock >= time(20)))

    def run(query, native):
        def gpu_fixture(url, *, json, **kwargs):
            assert url == get_settings().laya_preview_url + '/analyze'
            assert json['query'] == query
            body = dict(query=query, version=json['version'],
                        checkpoint_sha256=get_settings().laya_checkpoint_sha256,
                        answers={factor: dict(type='choice', choice=native.get(factor, 'skip'), confidence=.99)
                                 for factor in CARD_ORDER})
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)

        monkeypatch.setattr(service.httpx, 'post', gpu_fixture)
        response = TestClient(app).post('/api/agent/intent-preview', json={'query': query})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['query'] == query
        assert body['model'] == 'laya-' + get_settings().laya_checkpoint_sha256[:12]
        assert [card['factor'] for card in body['conditions']] == list(CARD_ORDER)
        assert not [card for card in body['conditions'] if card['state'] == 'analyzing']
        for card in body['conditions']:
            if card['state'] == 'not_applied':
                assert card['judgment'] == 'skip'
                assert card['direction'] is None and card['period'] is None
        return {card['factor']: card['judgment'] for card in body['conditions'] if card['state'] == 'applied'}

    yield run
    get_settings.cache_clear()


@pytest.mark.parametrize('clause', [
    '건널목과 계단은 피하지 말고 갈래',
    '계단과 건널목은 피하지 말고 갈래',
])
@pytest.mark.parametrize('prefix', ['', PREFIX])
def test_grouped_negation_through_http(preview, clause, prefix):
    native = {**WRONG_OBSTACLES, **(LIGHTING if prefix else {})}
    assert preview(prefix + clause, native) == (LIGHTING if prefix else {})


@pytest.mark.parametrize('clause,active', [
    ('계단 피하지 않고 건널목 피해서 갈래', dict(crossing='avoid')),
    ('건널목 피하지 않고 계단 피해서 갈래', dict(stairs='avoid')),
])
@pytest.mark.parametrize('prefix', ['', PREFIX])
def test_individual_negation_through_http(preview, clause, active, prefix):
    assert preview(prefix + clause, {**WRONG_OBSTACLES, **(LIGHTING if prefix else {})}) == {
        **active, **(LIGHTING if prefix else {})}


@pytest.mark.parametrize('query,gold', list(zip(browser_examples(), EXAMPLE_GOLD)),
                         ids=['crossing', 'stairs', 'comprehensive', 'lighting-stairs'])
def test_unchanged_browser_examples_through_http(preview, query, gold):
    assert preview(query, gold) == gold
