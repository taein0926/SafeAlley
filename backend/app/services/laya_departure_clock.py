"""Pilot-only explicit clock normalization; no model or production changes."""
import re
from datetime import time

from app.services.local_llm_service import (
    _clock_text, _corrects_previous_clock, _unambiguous_departure_clock,
    ARRIVAL_AFTER_TIME, ARRIVAL_BEFORE_TIME,
    DEPARTURE_AFTER_TIME, DEPARTURE_BEFORE_TIME,
)

_CLOCK = re.compile(
    r'(?<![가-힣\d:])(?:(?P<period>오전|오후|밤|새벽|아침|낮|저녁)\s*)?'
    r'(?P<hour>\d{1,2})(?:\s*시(?:\s*(?P<minute>\d{1,2})\s*분|\s*(?P<half>반))?'
    r'|\s*:\s*(?P<colon>\d{2}))'
    r'(?![\d:]|\s*분)(?=\s|[.,!?]|$|에|까지|부터|쯤|경|로|으로|야|가\s*아니|는\s*아니)'
)


def explicit_departure_clock(query):
    """Return (status, clock): absent/apply/skip/pending.

    Arrival deadlines never become departure clocks. Ambiguous multiple clocks
    or an unqualified 1..12 o'clock are left pending, not guessed.
    """
    text = _clock_text(query)
    matches = list(_CLOCK.finditer(text))
    if not matches:
        return 'absent', None
    mentions = []
    for i, match in enumerate(matches):
        following = text[match.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        preceding = text[max(0,match.start()-12):match.start()]
        if (ARRIVAL_AFTER_TIME.search(following) or ARRIVAL_BEFORE_TIME.search(preceding)
                or re.match(r'^\s*까지',following)):
            role = 'arrival'
        elif DEPARTURE_AFTER_TIME.search(following) or DEPARTURE_BEFORE_TIME.search(preceding):
            role = 'departure'
        else:
            role = 'unspecified'
        mentions.append((match,role))
    candidates = [(m,r) for m,r in mentions if r!='arrival']
    if not candidates:
        return 'skip', None
    if any(re.search(r'또는|혹은|아니면',text[a.end():b.start()]) for a,b in zip(matches,matches[1:])):
        return 'pending', None
    # A corrected arrival deadline is still an arrival deadline.
    if (len(mentions)>1 and all(r=='arrival' for _,r in mentions[:-1])
            and mentions[-1][1]=='unspecified'
            and _corrects_previous_clock(text,matches[-2],matches[-1])):
        return 'skip', None
    departures = [m for m,r in candidates if r=='departure']
    if (len(matches)>1 and mentions[-1][1]!='arrival'
            and _corrects_previous_clock(text,matches[-2],matches[-1])):
        selected = matches[-1]
    elif len(departures)==1:
        selected = departures[0]
    elif len(candidates)==1:
        selected = candidates[0][0]
    else:
        return 'pending', None
    hour = int(selected['hour'])
    minute = int(selected['minute'] or selected['colon'] or (30 if selected['half'] else 0))
    if not 0<=minute<=59:
        return 'pending', None
    period = selected['period']
    if period:
        # Reuse the final-Gemma validator for its supported period expressions.
        clock = _unambiguous_departure_clock(selected.group())
        if clock is not None:
            return 'apply', clock
        if not 1<=hour<=12:
            return 'pending', None
        hour = hour%12 + (12 if period in {'오후','낮','저녁','밤'} else 0)
        if period=='밤' and int(selected['hour'])==12:
            hour=0
    elif not 0<=hour<=23 or (selected['colon'] is None and 1<=hour<=12):
        return 'pending', None
    return 'apply',time(hour,minute)
