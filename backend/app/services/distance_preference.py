"""Explicit trip-distance requests shared by preview and final intent parsing.

Facility proximity is not the same as minimizing the user's travel distance.
These source checks do not train or replace either language model.
"""
import re

from app.services.laya_clause_candidate_v2 import _EXPLANATION, _MOVEMENT
from app.services.incomplete_conditions import preview_factor_evidence

_SHORT = re.compile(
    r'최단\s*(?:거리|경로|길)|최단으로|지름길'
    r'|가까운\s*(?:이동\s*)?거리|(?:(?:가장|최대한|가능한|더)\s*)?가까운\s*(?:길|경로)'
    r'|(?:짧은|짧게)\s*(?:길|경로|이동|걷)'
    r'|(?:이동\s*거리|걷는\s*거리|도보\s*거리|거리)(?:는|가|를|도)?\s*'
    r'(?:(?:더|좀|조금|최대한|가능한|되도록)\s*)?(?:짧|줄|가깝|가까|최소)'
    r'|(?:길|경로)(?:이|가|는)?\s*짧'
    r'|최소(?:한)?(?:의)?\s*(?:이동\s*)?거리'
    r'|(?:덜|적게)\s*걷(?:고|는|게|기)'
    r'|(?:빨리|빠르게|신속하게)\s*(?:가|갈|도착|안내|이동|걷)'
    r'|빠른\s*(?:길|경로)'
)
_FACILITY_RELATION = re.compile(
    r'(?:경찰서|파출소|지구대|병원|소방서|안전시설|도움시설|가로등|CCTV)'
    r'(?:와의|과의|까지의|와|과|에|이|가)?\s*$', re.I)
_REJECT_SHORT = re.compile(
    r'말고|보다는|보다|보단|대신|싫|필요(?:는|가)?\s*없'
    r'|고려하지\s*(?:않|말|마)|우선하지\s*(?:않|말|마)|우선\s*안'
    r'|아니어도\s*(?:돼|괜찮)|짧지\s*않아도|상관\s*없|가고\s*싶지\s*않|원하지\s*않'
)


def short_distance_choice(query: str) -> str | None:
    """Return apply/skip for an explicit trip preference, otherwise abstain."""
    if _EXPLANATION.search(query) and not _MOVEMENT.search(query):
        return None
    # Respect the existing last-mention rejection before recovering omissions.
    if preview_factor_evidence(query, 'distance')[0] == 'negative':
        return 'skip'
    matches = list(_SHORT.finditer(query))
    if not matches:
        nouns = list(re.finditer(r'(?<![가-힣])(?:이동\s*)?거리(?:는|가|를|도)?', query))
        if nouns and _REJECT_SHORT.search(query[nouns[-1].end():][:35]):
            return 'skip'
        return None
    trip_matches = [match for match in matches if not _FACILITY_RELATION.search(
        query[max(0, match.start() - 24):match.start()])]
    if not trip_matches:
        return 'skip'
    match = trip_matches[-1]
    tail = re.split(r'[.!?,，]|가로등|CCTV|계단|건널목|횡단보도|육교|안전시설|도움시설',
                    query[match.end():], maxsplit=1, flags=re.I)[0]
    if _REJECT_SHORT.search(tail[:35]):
        return 'skip'
    return 'apply'
