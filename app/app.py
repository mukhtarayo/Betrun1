from flask import Flask, request, jsonify, render_template
from app.engine.football import analyze_football_match, SUPPORTED_MARKETS
from app.engine.audit import export_picks, import_picks, store_pick, MEMORY_PICKS
from app.engine.adapters import sources as src
import os

try:
    from flask_cors import CORS
    _HAS_CORS = True
except Exception:
    _HAS_CORS = False

app = Flask(__name__, static_folder="static", template_folder="templates")
if _HAS_CORS:
    CORS(app)

@app.get("/")
def index():
    return render_template("index.html", supported_markets=SUPPORTED_MARKETS, brand="Betrun")

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/env_status")
def env_status():
    present = {k: bool(os.getenv(k)) for k in ["APISPORTS_KEY","STRICT_TEAM_MATCH","ALLOW_FALLBACK_NAMES"]}
    return jsonify(present)

# ---- Debug routes ----

@app.get("/debug/team")
def debug_team():
    name = request.args.get("name","").strip()
    if not name:
        return jsonify({"error":"missing ?name"}), 400
    meta = src.search_team(name)
    if not meta:
        return jsonify({"found":False,"input":name,"note":"not found"}), 404
    t = meta.get("team",{})
    return jsonify({
        "found": True,
        "input": name,
        "resolved_name": t.get("name"),
        "team_id": t.get("id"),
        "country": t.get("country"),
        "logo": t.get("logo"),
        "raw": meta
    })

@app.get("/debug/fixtures")
def debug_fixtures():
    team_id = request.args.get("team_id",type=int)
    season = request.args.get("season",default=2025,type=int)
    if not team_id:
        return jsonify({"error":"missing ?team_id"}), 400
    fxs = src.recent_fixtures(team_id, season, last=6)
    return jsonify({"count": len(fxs), "fixtures": fxs})

@app.get("/debug/injuries")
def debug_injuries():
    team_id = request.args.get("team_id",type=int)
    season = request.args.get("season",default=2025,type=int)
    if not team_id:
        return jsonify({"error":"missing ?team_id"}), 400
    data = src.get_injuries(team_id, season)
    return jsonify({"count": len(data), "injuries": data})

@app.get("/debug/leagues/sample")
def debug_leagues_sample():
    return jsonify(src.sample_league_aliases())

# ---- Analyzers ----

@app.post("/analyze/football")
def analyze_football():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        result = analyze_football_match(payload)
    except Exception as e:
        return jsonify({"status":"ERROR","reason":str(e)}), 500
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
    return jsonify({"status":"ok","count": len(MEMORY_PICKS)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
