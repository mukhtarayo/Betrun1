import os
import requests
from flask import Flask, request, jsonify, render_template
from app.engine.football import analyze_football_match, SUPPORTED_MARKETS
from app.engine.audit import export_picks, import_picks, store_pick, MEMORY_PICKS

# --- ENV ---
APISPORTS_KEY  = os.getenv("APISPORTS_KEY") or os.getenv("APISPORTS")
APISPORTS_BASE = os.getenv("APISPORTS_BASE", "https://v3.football.api-sports.io")
STRICT_TEAM_MATCH = os.getenv("STRICT_TEAM_MATCH", "0").lower() in ("1","true","yes")
BOOKMAKER_ID   = int(os.getenv("BOOKMAKER_ID", "8"))     # Bet365 id in API-FOOTBALL
BOOKMAKER_NAME = os.getenv("BOOKMAKER_NAME", "Bet365")
BRAND          = os.getenv("BRAND_NAME", "Betrun")

app = Flask(__name__, static_folder="static", template_folder="templates")

def _api_headers():
    if not APISPORTS_KEY:
        raise RuntimeError("Missing APISPORTS_KEY env var")
    return {"x-apisports-key": APISPORTS_KEY, "Accept": "application/json"}

@app.get("/")
def index():
    return render_template("index.html", supported_markets=SUPPORTED_MARKETS, brand=BRAND, bookmaker=BOOKMAKER_NAME)

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/env_status")
def env_status():
    present = {
        "APISPORTS_KEY": bool(APISPORTS_KEY),
        "APISPORTS_BASE": APISPORTS_BASE,
        "STRICT_TEAM_MATCH": STRICT_TEAM_MATCH,
        "BOOKMAKER_ID": BOOKMAKER_ID,
        "BOOKMAKER_NAME": BOOKMAKER_NAME,
        "BRAND": BRAND,
    }
    return jsonify(present)

# -------- fixtures + odds (Bet365) --------
@app.get("/api/matches")
def api_matches():
    """
    GET /api/matches?league_id=39&season=2025&date=YYYY-MM-DD
    Returns fixtures WITH Bet365 1X2 odds when available.
    """
    league_id = request.args.get("league_id", type=int)
    season    = request.args.get("season", type=int)
    date      = request.args.get("date")  # optional

    if not (league_id and season) and not date:
        return jsonify({"error": "Provide league_id & season OR a specific date (YYYY-MM-DD)"}), 400

    # 1) fixtures
    params = {}
    if league_id: params["league"] = league_id
    if season:    params["season"] = season
    if date:      params["date"]   = date

    try:
        r = requests.get(f"{APISPORTS_BASE}/fixtures", headers=_api_headers(), params=params, timeout=25)
        r.raise_for_status()
        fixtures_raw = r.json().get("response", [])
    except Exception as e:
        return jsonify({"error": f"fixtures: {e}"}), 502

    items = []
    fixture_ids = []
    for fx in fixtures_raw:
        league = fx.get("league", {})
        h = fx.get("teams", {}).get("home", {}) or {}
        a = fx.get("teams", {}).get("away", {}) or {}
        fid = fx.get("fixture", {}).get("id")
        fixture_ids.append(fid)
        items.append({
            "fixture_id": fid,
            "utc": fx.get("fixture", {}).get("date"),
            "status": fx.get("fixture", {}).get("status", {}).get("short"),
            "league_id": league.get("id"),
            "league": league.get("name"),
            "season": league.get("season"),
            "home_id": h.get("id"),
            "home": h.get("name"),
            "away_id": a.get("id"),
            "away": a.get("name"),
            "odds": None,
            "bookmaker": None
        })

    # Early return if no fixtures
    if not fixture_ids:
        return jsonify({"count": 0, "items": []})

    # 2) fetch odds per fixture (1X2 market) for Bet365
    # API-FOOTBALL returns odds per fixture; call in batches to stay safe (here: one-by-one simple loop)
    for it in items:
        fid = it["fixture_id"]
        try:
            r = requests.get(
                f"{APISPORTS_BASE}/odds",
                headers=_api_headers(),
                params={"fixture": fid, "bookmaker": BOOKMAKER_ID},
                timeout=25
            )
            r.raise_for_status()
            resp = r.json().get("response", [])
        except Exception:
            resp = []

        # parse 1X2 if present
        odds_map = None
        if resp:
            # resp structure: list of {bookmakers:[{name, bets:[{name, values:[{value,odd}]}]}]} per response item
            for entry in resp:
                for bm in entry.get("bookmakers", []):
                    if str(bm.get("id")) == str(BOOKMAKER_ID) or bm.get("name") == BOOKMAKER_NAME:
                        for bet in bm.get("bets", []):
                            if bet.get("name", "").lower() in ("match winner", "1x2", "1x2 ft", "ft 1x2"):
                                # values: [{"value":"Home","odd":"1.95"}, {"value":"Draw","odd":"3.40"}, {"value":"Away","odd":"3.45"}]
                                mm = {}
                                for v in bet.get("values", []):
                                    val = (v.get("value") or "").lower()
                                    try:
                                        price = float(v.get("odd"))
                                    except Exception:
                                        continue
                                    if val.startswith("home"): mm["1"] = price
                                    elif val.startswith("draw"): mm["X"] = price
                                    elif val.startswith("away"): mm["2"] = price
                                if mm:
                                    odds_map = mm
                                    break
                    if odds_map: break
                if odds_map: break

        if odds_map:
            it["odds"] = odds_map
            it["bookmaker"] = BOOKMAKER_NAME

    return jsonify({"count": len(items), "items": items})

# -------- analyzers --------
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
