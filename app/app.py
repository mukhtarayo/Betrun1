# app/app.py
import os
import time
import requests
from flask import Flask, request, jsonify, render_template

# Your existing engines (unchanged)
from app.engine.football import analyze_football_match, SUPPORTED_MARKETS
from app.engine.audit import export_picks, import_picks, store_pick, MEMORY_PICKS

# ---------- ENV ----------
APISPORTS_KEY  = os.getenv("APISPORTS_KEY") or os.getenv("apisports_key") or os.getenv("APISPORTS")
APISPORTS_BASE = os.getenv("APISPORTS_BASE", "https://v3.football.api-sports.io")
BRAND          = os.getenv("BRAND_NAME", "Betrun")
STRICT_TEAM_MATCH = os.getenv("STRICT_TEAM_MATCH", "0").lower() in ("1","true","yes")

# Odds merge settings
ODDS_BET_ID = 1  # 1X2 market
# Preferred bookmakers (first one found is used). You can reorder this list.
PREFERRED_BOOKMAKERS = [
    8,   # Pinnacle
    6,   # bet365
    11,  # William Hill
    3,   # Marathon
    21,  # Betfair
    14,  # Bwin
    1,   # 1xBet
]

# Tiny in-memory cache to avoid hammering /odds during one page load
_ODDS_CACHE = {}  # key: fixture_id -> {"1":float,"X":float,"2":float}

try:
    from flask_cors import CORS
    _HAS_CORS = True
except Exception:
    _HAS_CORS = False

app = Flask(__name__, static_folder="static", template_folder="templates")
if _HAS_CORS:
    CORS(app)


# ---------- helpers ----------
def _api_headers():
    if not APISPORTS_KEY:
        raise RuntimeError("Missing APISPORTS_KEY environment variable.")
    return {
        "x-apisports-key": APISPORTS_KEY,
        "Accept": "application/json",
    }


def _extract_1x2_from_odds_payload(payload):
    """
    Given API-Football /odds response list (response: [...]),
    return a dict {"1": float|None, "X": float|None, "2": float|None}
    for the first preferred bookmaker containing bet_id == 1 (1X2).
    """
    # The structure is response -> list of bookmakers, each has bets
    # Choose first bookmaker from preferred list that has bet_id=1
    best = None
    best_bm_id = None

    for bm_id in PREFERRED_BOOKMAKERS:
        for entry in payload:
            bookmaker = entry.get("bookmaker", {})
            if bookmaker.get("id") != bm_id:
                continue
            # find bet 1
            for bet in entry.get("bets", []):
                if bet.get("id") == ODDS_BET_ID:
                    best = bet
                    best_bm_id = bm_id
                    break
            if best:
                break
        if best:
            break

    # If not found in preferred list, just grab the first bet id 1 we see
    if not best:
        for entry in payload:
            for bet in entry.get("bets", []):
                if bet.get("id") == ODDS_BET_ID:
                    best = bet
                    break
            if best:
                break

    out = {"1": None, "X": None, "2": None, "_bookmaker_id": best_bm_id}
    if not best:
        return out

    # values: [{"value":"Home","odd":"1.95"}, {"value":"Draw","odd":"3.40"}, {"value":"Away","odd":"3.45"}]
    for v in best.get("values", []):
        tag = (v.get("value") or "").strip().lower()
        try:
            odd_f = float(v.get("odd"))
        except Exception:
            odd_f = None
        if tag in ("home", "1"):
            out["1"] = odd_f
        elif tag in ("draw", "x"):
            out["X"] = odd_f
        elif tag in ("away", "2"):
            out["2"] = odd_f
    return out


def _fetch_1x2_odds_for_fixture(fixture_id):
    """
    Calls /odds?fixture=<id>&bet=1 and returns {"1":..,"X":..,"2":..} or all None.
    Uses a tiny cache to lower API calls during one page load.
    """
    if fixture_id in _ODDS_CACHE:
        return _ODDS_CACHE[fixture_id]

    try:
        r = requests.get(
            f"{APISPORTS_BASE}/odds",
            headers=_api_headers(),
            params={"fixture": fixture_id, "bet": ODDS_BET_ID},
            timeout=20,
        )
        r.raise_for_status()
        resp = r.json().get("response", [])
    except Exception:
        resp = []

    odds = _extract_1x2_from_odds_payload(resp)
    _ODDS_CACHE[fixture_id] = odds
    return odds


def _fixtures_base_query(league=None, season=None, date=None, team=None, last=None, next_n=None):
    """Build params for /fixtures."""
    params = {}
    if league: params["league"] = league
    if season: params["season"] = season
    if date:   params["date"]   = date
    if team:   params["team"]   = team
    if last:   params["last"]   = last
    if next_n: params["next"]   = next_n
    return params


# ---------- pages ----------
@app.get("/")
def index():
    return render_template("index.html", supported_markets=SUPPORTED_MARKETS, brand=BRAND)


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/env_status")
def env_status():
    present = {
        "APISPORTS_KEY": bool(APISPORTS_KEY),
        "APISPORTS_BASE": APISPORTS_BASE,
        "STRICT_TEAM_MATCH": STRICT_TEAM_MATCH,
    }
    return jsonify(present)


# ---------- analyzers ----------
@app.post("/analyze/football")
def analyze_football():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        result = analyze_football_match(payload)
    except Exception as e:
        return jsonify({"status": "ERROR", "reason": str(e)}), 500
    store_pick(result)
    return jsonify(result)


@app.get("/export")
def export_json():
    return jsonify(export_picks())


@app.post("/import")
def import_json():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])
    import_picks(items)
    return jsonify({"status": "ok", "count": len(MEMORY_PICKS)})


# ---------- DEBUG helpers ----------
@app.get("/debug/ping")
def debug_ping():
    return jsonify({"ok": True})


@app.get("/debug/team")
def debug_team():
    """
    Find a team by fuzzy name using API-FOOTBALL /teams?search=
    Usage: /debug/team?name=man%20city
    """
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "missing ?name=<team>"}), 400
    try:
        r = requests.get(f"{APISPORTS_BASE}/teams", headers=_api_headers(),
                         params={"search": name}, timeout=15)
        r.raise_for_status()
        data = r.json().get("response", []) or []
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    if not data:
        return jsonify({"found": False, "query": name}), 404

    out = []
    for item in data[:10]:
        t = item.get("team", {})
        v = item.get("venue", {})
        out.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "code": t.get("code"),
            "country": t.get("country"),
            "founded": t.get("founded"),
            "venue": v.get("name"),
        })
    return jsonify({"found": True, "query": name, "candidates": out})


@app.get("/debug/fixtures")
def debug_fixtures():
    """
    Quick fixtures lookup.
      ?team_id= (optional)
      ?league=  (optional)
      ?season=2025 (default if missing and no date)
      ?date=YYYY-MM-DD (optional)
      ?last=N (optional)
      ?next=N (optional)
    """
    team_id = request.args.get("team_id", type=int)
    league  = request.args.get("league", type=int)
    season  = request.args.get("season", type=int)
    date    = request.args.get("date")
    last    = request.args.get("last", type=int)
    next_n  = request.args.get("next", type=int)

    if not (season or date):
        season = 2025

    params = _fixtures_base_query(league, season, date, team_id, last, next_n)

    try:
        r = requests.get(f"{APISPORTS_BASE}/fixtures",
                         headers=_api_headers(), params=params, timeout=20)
        r.raise_for_status()
        raw = r.json().get("response", []) or []
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    fixtures = []
    for fx in raw:
        l = fx.get("league", {})
        h = fx.get("teams", {}).get("home", {})
        a = fx.get("teams", {}).get("away", {})
        fixtures.append({
            "fixture_id": fx.get("fixture", {}).get("id"),
            "utc": fx.get("fixture", {}).get("date"),
            "status": fx.get("fixture", {}).get("status", {}).get("short"),
            "league_id": l.get("id"),
            "league": l.get("name"),
            "country": l.get("country"),
            "season": l.get("season"),
            "home_id": h.get("id"),
            "home": h.get("name"),
            "away_id": a.get("id"),
            "away": a.get("name"),
            "round": l.get("round"),
        })
    return jsonify({"count": len(fixtures), "items": fixtures})


@app.get("/debug/injuries")
def debug_injuries():
    team_id = request.args.get("team_id", type=int)
    season  = request.args.get("season", default=2025, type=int)
    if not team_id:
        return jsonify({"error": "missing ?team_id=<id>"}), 400
    try:
        r = requests.get(f"{APISPORTS_BASE}/injuries", headers=_api_headers(),
                         params={"team": team_id, "season": season}, timeout=20)
        r.raise_for_status()
        data = r.json().get("response", []) or []
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"team_id": team_id, "season": season, "count": len(data), "items": data})


@app.get("/debug/h2h")
def debug_h2h():
    """
    /fixtures/headtohead?h2h=<home_id>-<away_id>
    """
    h_id = request.args.get("home_id", type=int)
    a_id = request.args.get("away_id", type=int)
    if not (h_id and a_id):
        return jsonify({"error": "missing ?home_id=<id>&away_id=<id>"}), 400
    try:
        r = requests.get(f"{APISPORTS_BASE}/fixtures/headtohead",
                         headers=_api_headers(), params={"h2h": f"{h_id}-{a_id}"}, timeout=20)
        r.raise_for_status()
        data = r.json().get("response", []) or []
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"home_id": h_id, "away_id": a_id, "count": len(data), "items": data})


# ---------- PUBLIC: fixtures WITH ODDS ----------
@app.get("/fixtures")
def fixtures_public():
    """
    Frontend 'Get Matches' button calls this.
    Returns fixtures with merged 1X2 odds.
    Query:
      ?league=<id>  OR  ?team=<id>  (at least one required)
      ?season=<year> (required if date missing)
      ?date=YYYY-MM-DD (optional)
      ?next=N or ?last=N (optional)
    """
    league = request.args.get("league", type=int)
    season = request.args.get("season", type=int)
    date   = request.args.get("date")
    team   = request.args.get("team", type=int)
    last_n = request.args.get("last", type=int)
    next_n = request.args.get("next", type=int)

    if not (league or team):
        return jsonify({"error": "Provide ?league=<id> or ?team=<id>"}), 400
    if not (season or date):
        season = 2025  # default season if no date

    params = _fixtures_base_query(league, season, date, team, last_n, next_n)

    try:
        r = requests.get(f"{APISPORTS_BASE}/fixtures",
                         headers=_api_headers(), params=params, timeout=25)
        r.raise_for_status()
        raw = r.json().get("response", []) or []
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    # Clear odds cache per request
    _ODDS_CACHE.clear()

    items = []
    for fx in raw:
        fixture_id = fx.get("fixture", {}).get("id")
        l = fx.get("league", {})
        h = fx.get("teams", {}).get("home", {})
        a = fx.get("teams", {}).get("away", {})

        odds = _fetch_1x2_odds_for_fixture(fixture_id)
        # Be nice to the API if there are many fixtures (simple tiny delay)
        time.sleep(0.05)

        items.append({
            "fixture_id": fixture_id,
            "utc": fx.get("fixture", {}).get("date"),
            "status": fx.get("fixture", {}).get("status", {}).get("short"),
            "league_id": l.get("id"),
            "league": l.get("name"),
            "country": l.get("country"),
            "season": l.get("season"),
            "home_id": h.get("id"), "home": h.get("name"),
            "away_id": a.get("id"), "away": a.get("name"),
            "odds": {
                "1": odds.get("1"),
                "X": odds.get("X"),
                "2": odds.get("2"),
            },
            "bookmaker_id": odds.get("_bookmaker_id"),
        })

    return jsonify({"count": len(items), "items": items})


# Legacy alias some of your front-end may be calling
@app.get("/api/matches")
def api_matches():
    return fixtures_public()


# ---------- main ----------
if __name__ == "__main__":
    # Local dev
    app.run(host="0.0.0.0", port=8000, debug=True)
