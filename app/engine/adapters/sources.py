# app/engine/adapters/sources.py
from typing import Any, Dict, List, Optional, Tuple
from types import SimpleNamespace
import re, unicodedata

from . import live_football as api

# ---------- name normalization ----------
_STRIP_TOKENS = r'\b(fc|cf|sc|sk|fk|ac|afc|ud|cd|sv|if|s\.c\.|f\.c\.)\b'
_ALIAS = {
    "man city": "Manchester City",
    "man utd": "Manchester United",
    "psg": "Paris Saint Germain",
    "inter milan": "Inter",
    "club brugge": "Club Brugge KV",
    "fc kopenhagen": "FC Copenhagen",
    "kobenhavn": "FC Copenhagen",
    "københavn": "FC Copenhagen",
    "eintracht frank": "Eintracht Frankfurt",
    "cska moscow": "CSKA Moscow",
}

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(_STRIP_TOKENS, " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _apply_alias(s: str) -> str:
    n = _norm(s)
    return _ALIAS.get(n, s)

# ---------- Robust team search ----------
def search_team(name: str, country: Optional[str]=None, league_id: Optional[int]=None) -> Optional[Dict[str, Any]]:
    if not name: return None
    try:
        m = api.search_team(name)
        if m: return m
    except Exception: pass

    alias = _apply_alias(name)
    if alias and alias != name:
        try:
            m = api.search_team(alias)
            if m: return m
        except Exception: pass

    norm = _norm(name)
    if norm and norm != name and norm != _norm(alias):
        try:
            m = api.search_team(norm)
            if m: return m
        except Exception: pass

    return None

def recent_fixtures(team_id: int, season: int, last: int=6) -> List[Dict[str, Any]]:
    try: return api.recent_fixtures(team_id, season, last=last) or []
    except Exception: return []

def get_injuries(team_id: int, season: int) -> List[Dict[str, Any]]:
    try: return api.get_injuries(team_id, season) or []
    except Exception: return []

def get_h2h(home_id: int, away_id: int, last: int=5) -> List[Dict[str, Any]]:
    try: return api.get_h2h(home_id, away_id, last=last) or []
    except Exception: return []

# ---------- Fixtures + Odds helpers ----------
def fixtures_by_league_season(league_id: int, season: int, date: Optional[str]=None) -> List[Dict[str, Any]]:
    try: return api.fixtures_by_league_season(league_id, season, date=date) or []
    except Exception: return []

def _extract_1x2_from_odds(raw: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """
    API-Football odds response shape:
      response: [
        {
          "bookmakers": [
            {
              "name": "...",
              "bets": [
                 { "name": "Match Winner", "values": [ {"value":"Home", "odd":"2.10"}, ... ] },
                 ...
              ]
            }, ...
          ]
        }
      ]

    We take the FIRST bookmaker that contains a 'Match Winner' (or '1X2') bet and map to {"1":..., "X":..., "2":...}
    """
    if not raw: return None
    r0 = raw[0]  # first line for the fixture
    for bm in r0.get("bookmakers", []) or []:
        for bet in bm.get("bets", []) or []:
            name = (bet.get("name") or "").lower()
            if "match winner" in name or "1x2" in name:
                home = draw = away = None
                for v in bet.get("values", []) or []:
                    label = (v.get("value") or "").strip().lower()
                    try:
                        price = float(v.get("odd"))
                    except Exception:
                        price = None
                    if price is None: continue
                    if label in ("home","1","1 (home)"):
                        home = price
                    elif label in ("draw","x"):
                        draw = price
                    elif label in ("away","2","2 (away)"):
                        away = price
                if home and draw and away:
                    return {"1": home, "X": draw, "2": away}
    return None

def odds_for_fixture(fixture_id: int) -> Optional[Dict[str, float]]:
    try:
        raw = api.odds_by_fixture(fixture_id)
        return _extract_1x2_from_odds(raw)
    except Exception:
        return None

def fixtures_with_odds(league_id: int, season: int, date: Optional[str]=None) -> List[Dict[str, Any]]:
    fxs = fixtures_by_league_season(league_id, season, date=date)
    out = []
    for fx in fxs:
        fixture = fx.get("fixture", {})
        teams = fx.get("teams", {})
        fid = fixture.get("id")
        odds = odds_for_fixture(fid) if fid else None
        out.append({
            "fixture_id": fid,
            "utc": fixture.get("date"),
            "home": teams.get("home",{}).get("name"),
            "away": teams.get("away",{}).get("name"),
            "odds": odds  # may be None if odds not posted yet
        })
    return out

# export
sources = SimpleNamespace(
    search_team=search_team,
    recent_fixtures=recent_fixtures,
    get_injuries=get_injuries,
    get_h2h=get_h2h,
    fixtures_with_odds=fixtures_with_odds,
)
