# app/app.py
import os
import requests
from flask import Flask, request, jsonify, render_template

# ✅ keep using your existing engine (no changes needed here)
from app.engine.football import analyze_football_match, SUPPORTED_MARKETS
from app.engine.audit import export_picks, import_picks, store_pick, MEMORY_PICKS

APISPORTS_KEY = os.getenv("APISPORTS_KEY") or os.getenv("APISPORTS_KEY".lower()) or os.getenv("APISPORTS")
APISPORTS_BASE = "https://v3.football.api-sports.io"

STRICT_TEAM_MATCH = os.getenv("STRICT_TEAM_MATCH", "0") in ("1", "true", "True", "yes", "YES")

app = Flask(__name__, static_folder="static", template_folder="templates")

# --------------------------
# Page
# --------------------------
@app.get("/")
def index():
    return render_template("index.html", supported_markets=SUPPORTED_MARKETS, brand="Betrun")

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/env_status")
def env_status():
    present = {
        "APISPORTS_KEY": bool(APISPORTS_KEY),
        "STRICT_TEAM_MATCH": STRICT_TEAM_MATCH,
    }
    return jsonify(present)

# --------------------------
# ANALYZE (uses your engine)
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
# DEBUG HELPERS (no engine)
# --------------------------

def _api_headers():
    if not APISPORTS_KEY:
        raise RuntimeError("Missing APISPORTS_KEY env var")
    return {
        "x-apisports-key": APISPORTS_KEY,
        "Accept": "application/json",
    }

@app.get("/debug/ping")
def debug_ping():
    return jsonify({"ok": True})

@app.get("/debug/team")
def debug_team():
    """
    Find a team by fuzzy name using API-FOOTBALL /teams?search=.
    Query: ?name=<team>
    """
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "missing ?name=<team>"}), 400

    try:
        r = requests.get(
            f"{APISPORTS_BASE}/teams",
            headers=_api_headers(),
            params={"search": name},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json().get("response", [])
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    if not data:
        return jsonify({"found": False, "query": name}), 404

    # return the top suggestions so you can pick ids
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
    Quick recent fixtures lookup via /fixtures
    Query:
      ?team_id=   (int, optional)
      ?league=    (int, optional)
      ?season=    (int, default=2025)
      ?date=      (YYYY-MM-DD, optional)
      ?last=      (int, for last N fixtures if team_id provided)
    """
    team_id = request.args.get("team_id", type=int)
    league = request.args.get("league", type=int)
    season = request.args.get("season", default=2025, type=int)
    date = request.args.get("date")
    last = request.args.get("last", type=int)

    params = {}
    if league: params["league"] = league
    if season: params["season"] = season
    if date:   params["date"]   = date
    if team_id: params["team"]  = team_id
    if last:   params["last"]   = last

    try:
        r = requests.get(f"{APISPORTS_BASE}/fixtures", headers=_api_headers(), params=params, timeout=20)
        r.raise_for_status()
        raw = r.json().get("response", [])
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
    season = request.args.get("season", default=2025, type=int)
    if not team_id:
        return jsonify({"error": "missing ?team_id=<id>"}), 400
    try:
        r = requests.get(f"{APISPORTS_BASE}/injuries", headers=_api_headers(), params={"team": team_id, "season": season}, timeout=20)
        r.raise_for_status()
        data = r.json().get("response", [])
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
        r = requests.get(f"{APISPORTS_BASE}/fixtures/headtohead", headers=_api_headers(),
                         params={"h2h": f"{h_id}-{a_id}"}, timeout=20)
        r.raise_for_status()
        data = r.json().get("response", [])
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"home_id": h_id, "away_id": a_id, "count": len(data), "items": data})

# --------------------------
# PUBLIC FIXTURES (for index)
# --------------------------
@app.get("/fixtures")
def fixtures_public():
    """
    Frontend 'Get Matches' button calls this.
    Query: league, season, date (optional), team (optional)
    """
    league = request.args.get("league", type=int)
    season = request.args.get("season", type=int)
    date = request.args.get("date")
    team = request.args.get("team", type=int)

    if not (league or team):
        return jsonify({"error": "Provide ?league=<id> or ?team=<id>"}), 400
    if not season and not date:
        # API-FOOTBALL needs at least season or date
        season = 2025

    params = {}
    if league: params["league"] = league
    if season: params["season"] = season
    if date:   params["date"]   = date
    if team:   params["team"]   = team

    try:
        r = requests.get(f"{APISPORTS_BASE}/fixtures", headers=_api_headers(), params=params, timeout=20)
        r.raise_for_status()
        raw = r.json().get("response", [])
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
            "season": l.get("season"),
            "home_id": h.get("id"), "home": h.get("name"),
            "away_id": a.get("id"), "away": a.get("name"),
        })

    return jsonify({"count": len(fixtures), "items": fixtures})

if __name__ == "__main__":
    # local dev
    app.run(host="0.0.0.0", port=8000, debug=True)
