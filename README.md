# Betrun

Football-only betting analysis app with API-Football live data, strict skip rules, and debugging.
No tennis code. Uses Flask + Gunicorn. Deployable on Render free plan.

## Environment Variables (Render -> Environment)
- APISPORTS_KEY: your API-Football key
- STRICT_TEAM_MATCH: `1` to require exact team resolution (default), `0` to allow fuzzy fallback
- ALLOW_FALLBACK_NAMES: `1` to use alias list on failures (default), `0` to disable
- FOOTBALL_LEAGUE_AVG_GOALS: optional, e.g. `2.6`

## Run locally
```
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_RUN_PORT=8000
export APISPORTS_KEY=YOUR_KEY_HERE
export STRICT_TEAM_MATCH=1
export ALLOW_FALLBACK_NAMES=1
gunicorn -w 2 -k gthread -b 0.0.0.0:8000 app.app:app
```
Open http://localhost:8000

## Deploy to Render
1. Push this repo to GitHub.
2. Create new **Web Service** on Render, select your repo.
3. Runtime: Python, Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn -w 2 -k gthread -b 0.0.0.0:${PORT} app.app:app`
5. Add Environment:
   - `APISPORTS_KEY` = your key
   - `STRICT_TEAM_MATCH` = `1`
   - `ALLOW_FALLBACK_NAMES` = `1`
6. Deploy.
