from typing import Any, Dict, Optional, List
import re, unicodedata, os
from types import SimpleNamespace
from rapidfuzz import process, fuzz

from .live_football import search_team as lf_search_team, get_h2h as lf_get_h2h, get_injuries as lf_get_injuries, recent_fixtures as lf_recent_fixtures

_STRICT = os.getenv("STRICT_TEAM_MATCH", "1") == "1"
_ALLOW_FALLBACK = os.getenv("ALLOW_FALLBACK_NAMES", "1") == "1"

_STRIP_TOKENS = r'\b(fc|cf|sc|sk|fk|ac|afc|ud|cd|sv|if|s\.c\.|f\.c\.)\b'

_ALIAS: Dict[str,str] = {
    "man city": "Manchester City",
    "man utd": "Manchester United",
    "psg": "Paris Saint Germain",
    "inter milan": "Inter",
    "club brugge": "Club Brugge KV",
    "fc kopenhagen": "FC Copenhagen",
    "kobenhavn": "FC Copenhagen",
    "kobenhavn bk": "FC Copenhagen",
    "eintracht frank": "Eintracht Frankfurt",
    "cska moscow": "CSKA Moscow",
    "rio ave": "Rio Ave",
    "porto": "FC Porto",
}

# minimal league alias sample for future use/display
def sample_league_aliases():
    return {
        "PT1": "Primeira Liga",
        "ENP": "Premier League",
        "ENC": "Championship",
        "ES1": "LaLiga",
        "IT1": "Serie A",
        "DE1": "Bundesliga",
    }

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    s = re.sub(_STRIP_TOKENS, " ", s)
    s = re.sub(r"[^a-z0-9 ]+"," ", s)
    s = re.sub(r"\s+"," ", s).strip()
    return s

def _apply_alias(s: str) -> str:
    n = _norm(s)
    return _ALIAS.get(n, s)

def search_team(name: str, country: Optional[str] = None, league_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    # 1) try exact
    try:
        meta = lf_search_team(name)
        if meta: return meta
    except Exception:
        pass

    if not _ALLOW_FALLBACK:
        return None

    # 2) alias form
    alias = _apply_alias(name)
    if alias and alias != name:
        try:
            meta = lf_search_team(alias)
            if meta: return meta
        except Exception:
            pass

    # 3) normalized
    norm = _norm(name)
    if norm and norm != name and norm != _norm(alias):
        try:
            meta = lf_search_team(norm)
            if meta: return meta
        except Exception:
            pass

    # 4) fuzzy attempt over a small candidate set from API (search endpoint returns multiple)
    #    We re-query and pick best match if STRICT is off.
    if not _STRICT:
        try:
            # pull list
            import requests, os
            BASE = "https://v3.football.api-sports.io"
            r = requests.get(f"{BASE}/teams", headers={"x-apisports-key": os.getenv("APISPORTS_KEY")}, params={"search": norm or name}, timeout=10)
            r.raise_for_status()
            arr = r.json().get("response", [])
            candidates = [(a.get("team",{}).get("name",""), a) for a in arr]
            names = [c[0] for c in candidates if c[0]]
            if names:
                best, score, _ = process.extractOne(name, names, scorer=fuzz.WRatio)
                if score >= 85:
                    for nm, obj in candidates:
                        if nm == best: 
                            return obj
        except Exception:
            pass

    return None

def recent_fixtures(team_id: int, season: int, last: int = 6) -> List[Dict[str, Any]]:
    try:
        return lf_recent_fixtures(team_id, season, last=last) or []
    except Exception:
        return []

def get_injuries(team_id: int, season: int) -> List[Dict[str, Any]]:
    try:
        return lf_get_injuries(team_id, season) or []
    except Exception:
        return []

def get_h2h(home_id: int, away_id: int, last: int = 5) -> List[Dict[str, Any]]:
    try:
        return lf_get_h2h(home_id, away_id, last=last) or []
    except Exception:
        return []

sources = SimpleNamespace(
    search_team=search_team,
    recent_fixtures=recent_fixtures,
    get_injuries=get_injuries,
    get_h2h=get_h2h,
    sample_league_aliases=sample_league_aliases,
)
