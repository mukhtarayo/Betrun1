# app/app.py

import os
import requests
from flask import Flask, request, jsonify, render_template

# your existing engine (unchanged)
from app.engine.football import analyze_football_match, SUPPORTED_MARKETS
from app.engine.audit import export_picks, import_picks, store_pick, MEMORY_PICKS

# --- Config / ENV ---
APISPORTS_KEY  = os.getenv("APISPORTS_KEY") or os.getenv("APISPORTS")
APISPORTS_BASE = os.getenv("APISPORTS_BASE", "https://v3.football.api-sports.io")
STRICT_TEAM_MATCH = os.getenv("STRICT_TEAM_MATCH", "0").lower() in ("1", "true", "yes")
BRAND = os.getenv("BRAND_NAME", "Betrun")

try:
    from flask_cors import CORS
    _HAS_CORS = True
except Exception:
    _HAS_CORS = False

app = Flask(__name__, static_folder="static", template_folder="templates")
if _HAS_CORS:
    CORS(app)

# --------------------------
# Helpers for API-FOOTBALL
# --------------------------
def _api_headers():
    if not APISPORTS_KEY:
        raise RuntimeError("Missing APISPORTS_KEY environment variable")
    return {
        "x-apisports-key": APISPORTS_KEY,
        "Accept": "application/json",
    }

def _api_get(path: str, params: dict, timeout: int = 20):
    url = f"{APISPORTS_BASE.rstrip('/')}/{path.lstrip('/')}"
    r = requests.get(url, headers=_api_headers(), params=params, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    return j.get("response", [])

# Preferred bookmaker codes (exact label text from API-FOOTBALL)
PREFERRED_BOOKMAKERS = [
    "Bet365",
    "Pinnacle",
    "William Hill",
    "Marathonbet",
    "Unibet",
    "1xBet",
    "Betfair",
]

def _extract_1x2_from_odds_response(odds_blocks):
    """
    Input: odds response for a fixture (list of bookmakers with bets/values)
    Return: dict with {"1":float,"X":float,"2":float,"bookmaker":"name"} or {}
    """
    # Flatten by bookmaker, prefer in PREFERRED_BOOKMAKERS order
    by_bookmaker = {}
    for bk in odds_blocks:
        bname = (bk.get("bookmaker", {}) or bk.get("bookmakers", [{}])[0]).get("name") if "bookmaker" in bk else bk.get("bookmakers", [{}])[0].get("name")
        bname = bk.get("bookmaker", {}).get("name") if bk.get("bookmaker") else bk.get("bookmakers", [{}])[0].get("name")
        bname = (bk.get("bookmaker") or {}).get("name") or (bk.get("bookmakers", [{}])[0] or {}).get("name")
        # API V3 shape:
        # bookmaker: {id, name}, bets: [{id, name, values:[{value, odd}, ...]}]
        bookmaker = (bk.get("bookmaker") or {})
        bets = bk.get("bets") or []
        # find the "Match Winner" market (1X2)
        for bet in bets:
            bet_name = bet.get("name") or bet.get("label") or ""
            if bet_name.lower() in ("match winner", "1x2", "winner", "fulltime result"):
                one = draw = two = None
                for v in bet.get("values", []):
                    lbl = (v.get("value") or v.get("label") or "").strip().upper()
                    odd = v.get("odd")
                    if not odd:
                        continue
                    try:
                        o = float(odd)
                    except Exception:
                        continue
                    if lbl in ("1", "HOME"):
                        one = o
                    elif lbl in ("X", "DRAW"):
                        draw = o
                    elif lbl in ("2", "AWAY"):
                        two = o
                if one and draw and two:
                    by_bookmaker[bookmaker.get("name")] = {"1": one, "X": draw, "2": two, "bookmaker": bookmaker.get("name")}

    # choose preferred bookmaker if available; else any
    for pref in PREFERRED_BOOKMAKERS:
        if pref in by_bookmaker:
            return by_bookmaker[pref]
    # fallback: first any
    if by_bookmaker:
        # pick the one with most balanced (lowest juice) as a tiny heuristic
        best_name = min(by_bookmaker, key=lambda k: sum(1.0/float(v) for v in by_bookmaker[k].values() if isinstance(v, float)))
        return by_bookmaker[best_name]
    return {}

# --------------------------
# Pages
# --------------------------
@app.get("/")
def index():
    # Make sure you have templates/index.html in your repo
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
        "BRAND": BRAND,
    }
    return jsonify(present)

# --------------------------
# Matches + Odds (NEW)
# --------------------------
@app.get("/api/matches")
def api_matches():
    """
    Returns fixtures WITH 1X2 odds (if available) for a league/season/date.
      GET /api/matches?league_id=39&season=2025&date=YYYY-MM-DD
    You can also pass ?fixture_id= to fetch a single one.
    """
    fixture_id = request.args.get("fixture_id", type=int)
    league_id = request.args.get("league_id", type=int)
    season = request.args.get("season", type=int)
    date = request.args.get("date")  # optional YYYY-MM-DD

    if not (fixture_id or (league_id and (season or date))):
        return jsonify({"error": "Provide fixture_id OR league_id with season/date"}), 400

    # 1) Fetch fixtures
    fx_params = {}
    if fixture_id:
        fx_params["id"] = fixture_id
    if league_id:
        fx_params["league"] = league_id
    if season:
        fx_params["season"] = season
    if date:
        fx_params["date"] = date

    try:
        fixtures_raw = _api_get("/fixtures", fx_params)
    except Exception as e:
        return jsonify({"error": f"fixtures fetch failed: {e}"}), 502

    fixtures = []
    ids_for_odds = []
    for fx in fixtures_raw:
        f = fx.get("fixture", {})
        l = fx.get("league", {})
        h = fx.get("teams", {}).get("home", {})
        a = fx.get("teams", {}).get("away", {})
        fid = f.get("id")
        items = {
            "fixture_id": fid,
            "utc": f.get("date"),
            "status": (f.get("status") or {}).get("short"),
            "league_id": l.get("id"),
            "league": l.get("name"),
            "country": l.get("country"),
            "season": l.get("season"),
            "round": l.get("round"),
            "home_id": h.get("id"),
            "home": h.get("name"),
            "away_id": a.get("id"),
            "away": a.get("name"),
            "odds": None,  # to be filled
        }
        fixtures.append(items)
        if fid:
            ids_for_odds.append(fid)

    # 2) Fetch odds for those fixtures (if any)
    odds_map = {}
    if ids_for_odds:
        # API allows multiple fixture ids via repeated param: odds?fixture=ID
        # We'll just loop to be safe with rate limits
        for fid in ids_for_odds:
            try:
                odds_resp = _api_get("/odds", {"fixture": fid})
            except Exception:
                odds_resp = []
            # odds_resp is list of {bookmakers:[{bookmaker:{}, bets:[...]}, ...]}
            # but some plans return {bookmaker:{}, bets:[]} single layer
            # normalize:
            block_found = []
            for entry in odds_resp:
                # v3 format: entry = { "bookmakers":[ {bookmaker:{}, bets:[...]}, ... ] }
                bks = entry.get("bookmakers") or []
                for b in bks:
                    block_found.append(b)
            if not block_found and odds_resp:
                # some responses may already be in "bookmaker/bets" shape
                block_found = odds_resp

            picked = _extract_1x2_from_odds_response(block_found)
            if picked:
                odds_map[fid] = picked

    # 3) Attach odds into fixtures
    for item in fixtures:
        fid = item.get("fixture_id")
        if fid in odds_map:
            item["odds"] = odds_map[fid]

    return jsonify({"count": len(fixtures), "items": fixtures})

# --------------------------
# Debug Routes (useful)
# --------------------------
@app.get("/debug/ping")
def debug_ping():
    return jsonify({"ok": True})

@app.get("/debug/team")
def debug_team():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "missing ?name=<team>"}), 400
    try:
        resp = _api_get("/teams", {"search": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    if not resp:
        return jsonify({"found": False, "query": name}), 404
    out = []
    for r in resp[:15]:
        t = r.get("team", {})
        v = r.get("venue", {})
        out.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "code": t.get("code"),
            "country": t.get("country"),
            "venue": v.get("name"),
        })
    return jsonify({"found": True, "query": name, "candidates": out})

@app.get("/debug/fixtures")
def debug_fixtures():
    team_id = request.args.get("team_id", type=int)
    league = request.args.get("league", type=int)
    season = request.args.get("season", default=2025, type=int)
    date = request.args.get("date")
    last = request.args.get("last", type=int)
    params = {}
    if team_id: params["team"] = team_id
    if league:  params["league"] = league
    if season:  params["season"] = season
    if date:    params["date"] = date
    if last:    params["last"] = last
    try:
        resp = _api_get("/fixtures", params)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    items = []
    for fx in resp:
        l = fx.get("league", {})
        h = fx.get("teams", {}).get("home", {})
        a = fx.get("teams", {}).get("away", {})
        items.append({
            "fixture_id": fx.get("fixture", {}).get("id"),
            "utc": fx.get("fixture", {}).get("date"),
            "status": fx.get("fixture", {}).get("status", {}).get("short"),
            "league_id": l.get("id"),
            "league": l.get("name"),
            "season": l.get("season"),
            "home_id": h.get("id"), "home": h.get("name"),
            "away_id": a.get("id"), "away": a.get("name"),
        })
    return jsonify({"count": len(items), "items": items})

@app.get("/debug/injuries")
def debug_injuries():
    team_id = request.args.get("team_id", type=int)
    season = request.args.get("season", default=2025, type=int)
    if not team_id:
        return jsonify({"error": "missing ?team_id=<id>"}), 400
    try:
        resp = _api_get("/injuries", {"team": team_id, "season": season})
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"team_id": team_id, "season": season, "count": len(resp), "items": resp})

@app.get("/debug/h2h")
def debug_h2h():
    h_id = request.args.get("home_id", type=int)
    a_id = request.args.get("away_id", type=int)
    if not (h_id and a_id):
        return jsonify({"error": "missing ?home_id=<id>&away_id=<id>"}), 400
    try:
        resp = _api_get("/fixtures/headtohead", {"h2h": f"{h_id}-{a_id}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"home_id": h_id, "away_id": a_id, "count": len(resp), "items": resp})

# --------------------------
# Analyze (uses your engine)
# --------------------------
@app.post("/analyze/football")
def analyze_football():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        result = analyze_football_match(payload)
    except Exception as e:
        return jsonify({"status": "ERROR", "reason": str(e)}), 500
    store_pick(result)
    return jsonify(result)

# --------------------------
# Export / Import
# --------------------------
@app.get("/export")
def export_json():
    return jsonify(export_picks())

@app.post("/import")
def import_json():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])
    import_picks(items)
    return jsonify({"status": "ok", "count": len(MEMORY_PICKS)})

# --------------------------
# Main
# --------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
