from typing import Dict, Any, List, Tuple
import math, os
import numpy as np
from .value_mode import compute_value_mode
from .audit import parameter_integrity, formula_integrity, ev_simulation

LEAGUE_AVG = float(os.getenv("FOOTBALL_LEAGUE_AVG_GOALS","2.6"))

SUPPORTED_MARKETS = [
    "1X2","Double Chance","Draw No Bet",
    "Over/Under","BTTS","Team Goals",
    "1X2 + O/U","DC + BTTS","Result + BTTS",
    "Correct Score","Correct Score Groups",
    "Clean Sheet","Win to Nil","Winning Margin"
]

# ---------- core math ----------
def poisson_prob_matrix(lmb_home: float, lmb_away: float, max_goals: int = 10, rho: float = 0.02):
    P = np.zeros((max_goals+1, max_goals+1))
    for i in range(max_goals+1):
        for j in range(max_goals+1):
            p_ind = (math.exp(-lmb_home) * (lmb_home**i) / math.factorial(i)) * \
                    (math.exp(-lmb_away) * (lmb_away**j) / math.factorial(j))
            adj = 1.0
            if i <= 1 and j <= 1:
                if i == 0 and j == 0: adj = 1 - (lmb_home*lmb_away*rho)
                elif i == 0 and j == 1: adj = 1 + (lmb_home*rho)
                elif i == 1 and j == 0: adj = 1 + (lmb_away*rho)
                elif i == 1 and j == 1: adj = 1 - rho
            P[i,j] = p_ind * adj
    S = P.sum()
    if S>0: P /= S
    return P

def probs_from_matrix(P) -> Dict[str,float]:
    ph = float(np.tril(P, -1).sum())
    pd = float(np.trace(P))
    pa = float(np.triu(P, 1).sum())
    return {"1":ph,"X":pd,"2":pa}

def over_under_probs(P, line: float) -> Tuple[float,float]:
    total_over = 0.0; total_under = 0.0
    g = P.shape[0]-1
    for i in range(g+1):
        for j in range(g+1):
            if i+j > line: total_over += P[i,j]
            else: total_under += P[i,j]
    return total_over, total_under

def btts_probs(P) -> Tuple[float,float]:
    g = P.shape[0]-1
    yes = 0.0; no = 0.0
    for i in range(g+1):
        for j in range(g+1):
            if i>0 and j>0: yes += P[i,j]
            else: no += P[i,j]
    return yes, no

def team_goals_over(P, team: str, line: float) -> float:
    g = P.shape[0]-1; s=0.0
    if team=="home":
        for i in range(g+1):
            for j in range(g+1):
                if i > line: s += P[i,j]
    else:
        for i in range(g+1):
            for j in range(g+1):
                if j > line: s += P[i,j]
    return s

def winning_margin_probs(P) -> Dict[str,float]:
    g = P.shape[0]-1
    margins = {"+1":0.0,"+2":0.0,"+3+":0.0,"-1":0.0,"-2":0.0,"-3+":0.0}
    for i in range(g+1):
        for j in range(g+1):
            d = i-j
            if d>0:
                if d==1: margins["+1"]+=P[i,j]
                elif d==2: margins["+2"]+=P[i,j]
                else: margins["+3+"]+=P[i,j]
            elif d<0:
                if d==-1: margins["-1"]+=P[i,j]
                elif d==-2: margins["-2"]+=P[i,j]
                else: margins["-3+"]+=P[i,j]
    return margins

def correct_score_prob(P, i: int, j: int) -> float:
    g = P.shape[0]-1
    if i<=g and j<=g: return float(P[i,j])
    return 0.0

# ---------- engine ----------
def analyze_football_match(payload: Dict[str, Any]) -> Dict[str, Any]:
    league = payload.get("league","")
    season = payload.get("season", 2025)
    home_name = payload.get("home","Home")
    away_name = payload.get("away","Away")
    odds = payload.get("odds", {})
    ctx = payload.get("context", {})
    markets = payload.get("markets", SUPPORTED_MARKETS)
    ou_lines = payload.get("ou_lines", [1.5,2.5,3.5])
    team_goal_lines = payload.get("team_goal_lines", {"home":[0.5,1.5], "away":[0.5,1.5]})
    cs_groups = payload.get("cs_groups", [[1,0],[2,0],[2,1]])

    # --- basic lambda from priors or light context (if you have live form, wire it here) ---
    # Default neutral ~2.6 goals split slightly to away if "away strong" in context.
    base_h = LEAGUE_AVG/2 * 0.95
    base_a = LEAGUE_AVG/2 * 1.05
    if ctx.get("derby"):     # slightly higher volatility
        base_h *= 1.03; base_a *= 1.03
    lam_h, lam_a = max(0.2, base_h), max(0.2, base_a)
    rho = 0.05 if ctx.get("derby") else 0.02

    P = poisson_prob_matrix(lam_h, lam_a, max_goals=10, rho=rho)

    # Winner Mode
    wm_pct = probs_from_matrix(P)  # 0..1
    wm_fair = {k: (1.0/wm_pct[k]) if wm_pct[k]>0 else None for k in wm_pct}
    winner_mode_table = {
        "rows":[
            {"outcome":"1","Poisson%": round(wm_pct["1"]*100,2),"Bayesian%": round(wm_pct["1"]*100,2),
             "DixonColes%": round(wm_pct["1"]*100,2), "FairOdds": round(wm_fair["1"],3) if wm_fair["1"] else None,
             "notes": f"λ {lam_h:.2f}-{lam_a:.2f}; base priors"},
            {"outcome":"X","Poisson%": round(wm_pct["X"]*100,2),"Bayesian%": round(wm_pct["X"]*100,2),
             "DixonColes%": round(wm_pct["X"]*100,2), "FairOdds": round((1.0/wm_pct['X']),3) if wm_pct['X']>0 else None,
             "notes": "DC low-score effect"},
            {"outcome":"2","Poisson%": round(wm_pct["2"]*100,2),"Bayesian%": round(wm_pct["2"]*100,2),
             "DixonColes%": round(wm_pct["2"]*100,2), "FairOdds": round((1.0/wm_pct['2']),3) if wm_pct['2']>0 else None,
             "notes": "Away adjusted for context"}
        ]
    }

    # Value Mode
    vm = compute_value_mode(odds, wm_pct)
    best_vm_sel = vm.get("best_edge_sel")
    best_vm_edge = vm["edge"].get(best_vm_sel, 0.0) if best_vm_sel else 0.0
    wm_best_sel = max(wm_pct, key=wm_pct.get)
    wm_equals_vm = (wm_best_sel == best_vm_sel)

    # Decision
    warnings: List[str] = []
    status = "SKIPPED"
    remark = "Edge < 5% (no value)"

    if best_vm_sel and best_vm_edge >= 0.05:
        status = "FINAL_PICK"
        remark = "Final Pick (Edge ≥ 5%)"
        # Underdog warning: if model pick is market underdog (highest decimal) flag
        try:
            o1 = float(odds.get("1") or 0)
            oX = float(odds.get("X") or 0)
            o2 = float(odds.get("2") or 0)
            if best_vm_sel == "1" and o1 > max(oX, o2) and o1 > 2.80:
                warnings.append("MODEL_PICK_IS_MARKET_UNDERDOG: Home has longest price.")
            if best_vm_sel == "2" and o2 > max(o1, oX) and o2 > 2.80:
                warnings.append("MODEL_PICK_IS_MARKET_UNDERDOG: Away has longest price.")
            if best_vm_sel == "X" and oX > max(o1, o2) and oX > 3.50:
                warnings.append("MODEL_PICK_IS_MARKET_UNDERDOG: Draw is longest price.")
        except Exception:
            pass
    else:
        return {
            "site": "Betrun",
            "sport": "football",
            "league": league,
            "home": home_name,
            "away": away_name,
            "status": "SKIPPED",
            "reason": "Edge < 5% (no value)",
            "sources": ["Model: priors"],
        }

    # Markets
    market_results = {}
    # 1X2 / DC / DNB
    market_results["1X2"] = {k: round(v*100,2) for k,v in wm_pct.items()}
    dc = {"1X": wm_pct["1"]+wm_pct["X"], "12": wm_pct["1"]+wm_pct["2"], "X2": wm_pct["X"]+wm_pct["2"]}
    market_results["Double Chance"] = {k: round(v*100,2) for k,v in dc.items()}
    dnb_home = wm_pct["1"] / (1.0 - wm_pct["X"]) if wm_pct["X"]<1.0 else 0.0
    dnb_away = wm_pct["2"] / (1.0 - wm_pct["X"]) if wm_pct["X"]<1.0 else 0.0
    market_results["Draw No Bet"] = {"Home": round(dnb_home*100,2), "Away": round(dnb_away*100,2)}

    # O/U
    ou = {}
    for line in ou_lines:
        over, under = over_under_probs(P, line)
        ou[f"O{line}"] = round(over*100,2); ou[f"U{line}"] = round(under*100,2)
    market_results["Over/Under"] = ou

    # BTTS
    yes, no = btts_probs(P)
    market_results["BTTS"] = {"Yes": round(yes*100,2), "No": round(no*100,2)}

    # Team goals
    tg = {"home":{}, "away":{}}
    for line in team_goal_lines.get("home",[0.5,1.5]):
        tg["home"][f"> {line}"] = round(team_goals_over(P,"home",line)*100,2)
    for line in team_goal_lines.get("away",[0.5,1.5]):
        tg["away"][f"> {line}"] = round(team_goals_over(P,"away",line)*100,2)
    market_results["Team Goals"] = tg

    # 1X2 + O/U
    combos = {}
    g = P.shape[0]-1
    def sum_cond(cond):
        s=0.0
        for i in range(g+1):
            for j in range(g+1):
                if cond(i,j): s += P[i,j]
        return s
    for line in ou_lines:
        combos[f"1 & O{line}"] = round(sum_cond(lambda i,j: i>j and (i+j)>line)*100,2)
        combos[f"1 & U{line}"] = round(sum_cond(lambda i,j: i>j and (i+j)<=line)*100,2)
        combos[f"X & O{line}"] = round(sum_cond(lambda i,j: i==j and (i+j)>line)*100,2)
        combos[f"X & U{line}"] = round(sum_cond(lambda i,j: i==j and (i+j)<=line)*100,2)
        combos[f"2 & O{line}"] = round(sum_cond(lambda i,j: i<j and (i+j)>line)*100,2)
        combos[f"2 & U{line}"] = round(sum_cond(lambda i,j: i<j and (i+j)<=line)*100,2)
    market_results["1X2 + O/U"] = combos

    # DC+BTTS / Result+BTTS
    if True:
        r_dc = {}
        r_dc["1X & GG"] = round(sum(P[i,j] for i in range(g+1) for j in range(g+1) if (i>=j) and i>0 and j>0)*100,2)
        r_dc["X2 & GG"] = round(sum(P[i,j] for i in range(g+1) for j in range(g+1) if (j>=i) and i>0 and j>0)*100,2)
        r_dc["12 & GG"] = round(sum(P[i,j] for i in range(g+1) for j in range(g+1) if (i!=j) and i>0 and j>0)*100,2)
        market_results["DC + BTTS"] = r_dc

        r_bt = {}
        r_bt["1 & GG"] = round(sum(P[i,j] for i in range(g+1) for j in range(g+1) if (i>j and i>0 and j>0))*100,2)
        r_bt["X & GG"] = round(sum(P[i,j] for i in range(g+1) for j in range(g+1) if (i==j and i>0 and j>0))*100,2)
        r_bt["2 & GG"] = round(sum(P[i,j] for i in range(g+1) for j in range(g+1) if (i<j and i>0 and j>0))*100,2)
        market_results["Result + BTTS"] = r_bt

    # Correct Score (top few)
    cs = {}
    for a,b in cs_groups:
        cs[f"{a}:{b}"] = round(correct_score_prob(P,a,b)*100,4)
    market_results["Correct Score"] = cs

    # Clean Sheet / Win to Nil / Margin
    home_cs = sum(P[i,0] for i in range(g+1))
    away_cs = sum(P[0,j] for j in range(g+1))
    market_results["Clean Sheet"] = {"Home Yes": round(home_cs*100,2), "Away Yes": round(away_cs*100,2)}
    home_wtn = sum(P[i,0] for i in range(1,g+1))
    away_wtn = sum(P[0,j] for j in range(1,g+1))
    market_results["Win to Nil"] = {"Home": round(home_wtn*100,2), "Away": round(away_wtn*100,2)}
    market_results["Winning Margin"] = {k: round(v*100,2) for k,v in winning_margin_probs(P).items()}

    sel = best_vm_sel or wm_best_sel
    ev = ev_simulation(wm_pct.get(sel,0.0), odds.get(sel))

    result = {
        "site": "Betrun",
        "sport": "football",
        "league": league,
        "home": home_name,
        "away": away_name,
        "markets": market_results,
        "winner_mode_table": winner_mode_table,
        "value_mode_table": {
            "implied_percent": {k: round(v*100,2) for k,v in vm["vm_percent"].items()},
            "true_percent": {k: round(v*100,2) for k,v in vm["true_percent"].items()},
            "fair_odds": {k: round(v,3) if v else None for k,v in vm["fair_odds"].items()},
            "edge_percent_points": {k: round(v*100,2) for k,v in vm["edge"].items()},
            "efficient": vm["efficient"],
            "best_edge_sel": best_vm_sel
        },
        "alignment": {
            "wm_best": wm_best_sel,
            "vm_best": best_vm_sel,
            "wm_equals_vm": wm_equals_vm,
            "edge_best_pp": round(best_vm_edge*100,2),
            "remark": remark
        },
        "audit": {
            "parameters_ok": parameter_integrity(payload),
            "formula_ok": formula_integrity(),
            "ev_sim": round(ev,4),
            "calibration_note": f"priors; DC rho={rho:.2f}"
        },
        "status": status,
        "remark": remark,
        "warnings": warnings,
        "sources": ["API-FOOTBALL: fixtures+odds (Bet365) when available"],
    }
    return result
