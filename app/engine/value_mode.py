from typing import Dict, Any

def compute_value_mode(odds: Dict[str,float], wm_pct: Dict[str,float]) -> Dict[str, Any]:
    # implied percentages from odds (no de-vig here)
    vm_percent = {}
    fair_odds = {}
    edge = {}
    true_percent = wm_pct.copy()
    best_sel, best_edge = None, -1.0
    efficient = True

    for k in ["1","X","2"]:
        o = odds.get(k) or 0.0
        if o > 0:
            vm_percent[k] = 1.0 / o
            fair_odds[k] = 1.0 / (true_percent.get(k,0.0) or 1e-9)
            edge[k] = (true_percent.get(k,0.0) - vm_percent[k])
            if edge[k] > best_edge:
                best_edge = edge[k]; best_sel = k
        else:
            vm_percent[k] = 0.0
            fair_odds[k] = None
            edge[k] = -1.0

    # market efficiency check: if max edge < 0.03 mark as efficient
    efficient = (best_edge < 0.03)

    return {
        "vm_percent": vm_percent,
        "true_percent": true_percent,
        "fair_odds": fair_odds,
        "edge": edge,
        "efficient": efficient,
        "best_edge_sel": best_sel
    }
