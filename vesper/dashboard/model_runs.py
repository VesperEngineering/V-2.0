"""Read-only model-iteration data for the dashboard."""


def promotion_oos_ic(state: dict) -> float | None:
    for item in state.get("accepted", []) + state.get("rejected", []):
        threshold = item.get("baseline_comparison", {}).get("minimum_out_of_sample_ic")
        if isinstance(threshold, (int, float)):
            return float(threshold)
    return None


def best_oos_so_far(rows: list[dict]) -> list[float | None]:
    best = None
    values = []
    for row in rows:
        value = row.get("oos_ic")
        if isinstance(value, (int, float)) and (best is None or value > best):
            best = float(value)
        values.append(best)
    return values


def model_run_rows(state: dict) -> list[dict]:
    baseline = state.get("baseline", {})
    rows = [{
        "run": 0,
        "status": "BASELINE",
        "oos_ic": baseline.get("out_of_sample_ic"),
        "rank_ic": baseline.get("rank_ic"),
        "spread": baseline.get("ranking_spread"),
    }]
    for status, items in (("REJECTED", state.get("rejected", [])),
                          ("ACCEPTED", state.get("accepted", []))):
        for item in items:
            candidate = item.get("candidate", {})
            rows.append({
                "run": item.get("run"),
                "status": status,
                "oos_ic": candidate.get("out_of_sample_ic"),
                "rank_ic": candidate.get("rank_ic"),
                "spread": candidate.get("ranking_spread"),
            })
    pending = state.get("pending")
    if pending:
        rows.append({
            "run": pending.get("run"),
            "status": "RUNNING",
            "oos_ic": None,
            "rank_ic": None,
            "spread": None,
        })
    return sorted(rows, key=lambda row: row["run"] if row["run"] is not None else -1)
