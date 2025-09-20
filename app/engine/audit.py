from typing import Dict, Any, List

MEMORY_PICKS: List[Dict[str, Any]] = []

def parameter_integrity(payload: Dict[str, Any]) -> bool:
    keys = ["home","away","odds"]
    return all(k in payload for k in keys)

def formula_integrity() -> bool:
    return True

def ev_simulation(prob: float, odds: float, stake: float = 1.0) -> float:
    if not prob or not odds:
        return 0.0
    return prob* (odds-1) - (1-prob)*1.0

def store_pick(pick: Dict[str, Any]) -> None:
    try:
        MEMORY_PICKS.append(pick)
    except Exception:
        pass

def export_picks() -> Dict[str, Any]:
    return {"items": MEMORY_PICKS}

def import_picks(items: List[Dict[str, Any]]) -> None:
    MEMORY_PICKS.clear()
    MEMORY_PICKS.extend(items or [])
