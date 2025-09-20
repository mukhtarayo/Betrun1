from typing import Any, Dict, List, Optional
import os, requests

BASE = "https://v3.football.api-sports.io"

def _headers():
    key = os.getenv("APISPORTS_KEY")
    if not key:
        raise RuntimeError("Missing APISPORTS_KEY")
    return {"x-apisports-key": key}

def search_team(query: str) -> Optional[Dict[str, Any]]:
    url = f"{BASE}/teams"
    r = requests.get(url, headers=_headers(), params={"search": query}, timeout=12)
    r.raise_for_status()
    data = r.json().get("response", [])
    return data[0] if data else None

def recent_fixtures(team_id: int, season: int, last: int = 6) -> List[Dict[str, Any]]:
    url = f"{BASE}/fixtures"
    r = requests.get(url, headers=_headers(), params={"team": team_id, "season": season, "last": last}, timeout=12)
    r.raise_for_status()
    return r.json().get("response", [])

def get_injuries(team_id: int, season: int) -> List[Dict[str, Any]]:
    url = f"{BASE}/injuries"
    r = requests.get(url, headers=_headers(), params={"team": team_id, "season": season}, timeout=12)
    r.raise_for_status()
    return r.json().get("response", [])

def get_h2h(home_id: int, away_id: int, last: int = 5) -> List[Dict[str, Any]]:
    url = f"{BASE}/fixtures/headtohead"
    r = requests.get(url, headers=_headers(), params={"h2h": f"{home_id}-{away_id}", "last": last}, timeout=12)
    r.raise_for_status()
    return r.json().get("response", [])
