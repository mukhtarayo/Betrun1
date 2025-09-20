# app/engine/adapters/live_football.py
from typing import Any, Dict, List, Optional
import os, requests

BASE = os.getenv("APISPORTS_BASE", "https://v3.football.api-sports.io")
API_KEY = os.getenv("APISPORTS_KEY", "")

HEADERS = {
    "x-apisports-key": API_KEY or "",
}

def _get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE.rstrip('/')}/{path.lstrip('/')}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------- Teams ----------
def search_team(name: str) -> Optional[Dict[str, Any]]:
    if not name: return None
    data = _get("teams", {"search": name})
    arr = (data or {}).get("response", []) or []
    return arr[0] if arr else None

# ---------- Fixtures ----------
def fixtures_by_league_season(league_id: int, season: int, date: Optional[str]=None) -> List[Dict[str, Any]]:
    params = {"league": league_id, "season": season}
    if date: params["date"] = date  # YYYY-MM-DD
    data = _get("fixtures", params)
    return (data or {}).get("response", []) or []

def recent_fixtures(team_id: int, season: int, last: int = 6) -> List[Dict[str, Any]]:
    data = _get("fixtures", {"team": team_id, "season": season, "last": last})
    return (data or {}).get("response", []) or []

# ---------- Injuries/H2H ----------
def get_injuries(team_id: int, season: int) -> List[Dict[str, Any]]:
    data = _get("injuries", {"team": team_id, "season": season})
    return (data or {}).get("response", []) or []

def get_h2h(home_id: int, away_id: int, last: int = 5) -> List[Dict[str, Any]]:
    data = _get("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": last})
    return (data or {}).get("response", []) or []

# ---------- Odds ----------
def odds_by_fixture(fixture_id: int) -> List[Dict[str, Any]]:
    """
    Returns raw odds array from API-Football for a fixture.
    We will pick the first available 'Match Winner' / 1X2 market at higher level.
    """
    data = _get("odds", {"fixture": fixture_id})
    return (data or {}).get("response", []) or []
