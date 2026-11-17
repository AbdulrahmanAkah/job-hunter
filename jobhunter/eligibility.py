"""Decide whether a remote job can be applied to from Iraq.

Returns one of:
  ELIGIBLE  - open worldwide / anywhere / MENA / Middle East / EMEA / Iraq
  CHECK     - location unclear; keep it but mark "check location"
  RESTRICTED - limited to specific countries/regions that exclude Iraq -> drop
"""
from __future__ import annotations

import re

ELIGIBLE = "eligible"
CHECK = "check location"
RESTRICTED = "restricted"

# Location text containing any of these means Iraq is included.
_OPEN_PATTERNS = [
    r"world\s*wide", r"anywhere", r"\bglobal(?:ly)?\b", r"\bmena\b", r"middle\s*east",
    r"\biraq\b", r"\bkurdistan\b", r"\bemea\b", r"all\s+countries", r"any\s+country",
    r"any\s+location", r"\binternational\b", r"العراق", r"عالمي",
]

# Location text that says nothing about where (treated as unclear, not restricted).
_GENERIC = {"", "remote", "remote job", "fully remote", "100% remote", "remote-first",
            "remote first", "work from home", "wfh", "n/a", "na", "-", "flexible", "telecommute"}

# Phrases in title/description that restrict the job to a place other than Iraq.
_RESTRICTION_PHRASES = [
    # US/EU/UK are matched case-sensitively so the pronoun "us" ("contact us only…") doesn't trigger
    r"(?:\b(?-i:US|USA|EU|UK)|\bu\.s\.|\bu\.k\.|\b(?:usa|united states|europe|canada|latam|egypt|india|philippines|"
    r"germany|australia|brazil|mexico|pakistan|nigeria|kenya|south africa))[\s\-]*(?:only|based)\b",
    r"\bonly\s+(?:open\s+to\s+)?(?:candidates|applicants|residents|people)\s+(?:based\s+|located\s+|living\s+)?in\s+"
    r"(?!.{0,40}(?:iraq|mena|middle east|anywhere|worldwide))",
    r"must\s+(?:be\s+)?(?:reside|resident|located|based|living)\s+(?:in|within)\s+the\s+(?:us|u\.s\.|united states|uk|eu|european union)",
    r"must\s+(?:be\s+)?(?:reside|resident|located|based|living)\s+(?:in|within)\s+(?:the\s+)?(?:us|usa|u\.s\.|canada|europe|uk|egypt|india)\b",
    r"authori[sz]ed\s+to\s+work\s+in\s+the\s+(?:us|u\.s\.|united states|uk|eu)",
    r"\bus\s+citizens?(?:hip)?\s+(?:is\s+)?required\b",
    r"\b(?:must\s+be\s+(?:a\s+)?)?us\s+citizens?\s+only\b",
    r"\bw-?2\s+(?:only|employees?)\b",
    r"\bin\s+the\s+(?:us|u\.s\.|united states)\s+only\b",
    r"anywhere\s+in\s+(?:the\s+)?(?:us|u\.s\.|usa|united states|uk|eu|europe|canada|latam|"
    r"latin america|americas?|north america|asia|apac|africa)\b",
]

# A place named in the TITLE ("Sales Rep, Singapore", "Engineer (LATAM)") usually means the hire
# is limited to that place, even when the board lists the job as "Anywhere".
_TITLE_PLACES = (
    r"(?:\b(?-i:US|USA|UK|EU)\b|\b(?:latam|latin america|apac|americas|north america|south america|"
    r"europe|european|canada|mexico|brazil|colombia|argentina|chile|peru|germany|dach|france|spain|"
    r"italy|netherlands|benelux|nordics|poland|portugal|ireland|romania|ukraine|india|pakistan|"
    r"philippines|singapore|japan|china|korea|vietnam|indonesia|malaysia|thailand|australia|anz|"
    r"new zealand|south africa|nigeria|kenya|egypt|morocco|turkey|israel|"
    r"new york|san francisco|london|berlin|toronto|bangalore|bengaluru|manila|sydney|cairo)\b)"
)
_open_re = re.compile("|".join(_OPEN_PATTERNS), re.I)
_title_place_re = re.compile(_TITLE_PLACES, re.I)
_restrict_re = re.compile("|".join(_RESTRICTION_PHRASES), re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# Words that show a sentence is about WHERE candidates may be (not e.g. where the offices are).
_HIRING_CONTEXT = re.compile(
    r"candidates?|applicants?|residents?|eligib|open\s+to|\bhir(?:e|es|ing)\b|employ|countries|"
    r"time\s*zones?|located\s+in|you\s+(?:must|should|need\s+to)\s+(?:be|live)|we\s+accept|from\s+the\s+following",
    re.I,
)


def region_list_excluding_iraq(text: str) -> str | None:
    """Find a sentence that lists 2+ allowed places for candidates and leaves Iraq out,
    e.g. "We hire in the US, UK, Germany and Poland". Returns the places found, or None.
    (Hard restrictions are already dropped by classify(); this catches softer lists.)"""
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", (text or "")[:8000]):
        if not _HIRING_CONTEXT.search(sentence) or _open_re.search(sentence):
            continue
        places = {m.group(0).lower() for m in _title_place_re.finditer(sentence)}
        if len(places) >= 2:
            return ", ".join(sorted(places))
    return None


def classify(location, title: str = "", description: str = "") -> tuple[str, str]:
    """Classify a job. `location` may be a string or a list of country names
    (Himalayas style: empty list = worldwide).

    Returns (status, note).
    """
    # Explicit restriction in the title always wins ("(U.S. Based)", "EU only").
    m = _restrict_re.search(title or "")
    if m:
        return RESTRICTED, f"title says '{m.group(0).strip()}'"
    m = _title_place_re.search(title or "")
    if m and not _open_re.search(title):
        return RESTRICTED, f"title names a place: '{m.group(0).strip()}'"

    # List of allowed countries (Himalayas).
    if isinstance(location, (list, tuple)):
        countries = [_norm(c) for c in location if c]
        if not countries:
            loc_status, loc_note = ELIGIBLE, "worldwide (no country restriction)"
        elif any(c in ("iraq", "kurdistan") for c in countries):
            loc_status, loc_note = ELIGIBLE, "Iraq listed among allowed countries"
        else:
            shown = ", ".join(location[:5]) + ("…" if len(location) > 5 else "")
            return RESTRICTED, f"limited to: {shown}"
    else:
        loc = _norm(location)
        if _restrict_re.search(loc):
            return RESTRICTED, f"location: {location.strip()}"
        if _open_re.search(loc):
            loc_status, loc_note = ELIGIBLE, f"location: {location.strip()}"
        elif loc.strip(" .,;") in _GENERIC:
            loc_status, loc_note = CHECK, "location not stated"
        else:
            # A specific place (country, region, city, "USA Only", etc.) that isn't Iraq/MENA.
            return RESTRICTED, f"location: {location.strip()}"

    # Even "worldwide" posts sometimes restrict in the body.
    desc = (description or "")[:6000]
    m = _restrict_re.search(desc)
    if m:
        return RESTRICTED, f"description says '{m.group(0).strip()}'"

    if loc_status == CHECK and _open_re.search(desc):
        return ELIGIBLE, "description mentions worldwide/anywhere"
    return loc_status, loc_note
