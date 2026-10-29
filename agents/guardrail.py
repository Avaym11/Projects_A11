from tools.price_limits import check_price_limits


def run(proposed_price: float, cost: float, day_start_price: float,
        competitors: list, min_margin_pct: float = 15.0, max_change_pct: float = 10.0) -> dict:

    result = check_price_limits(proposed_price, cost, day_start_price, min_margin_pct, max_change_pct)

    has_stale = any(c.get("stale") for c in competitors)
    if has_stale:
        result["violations"].append("Based on stale competitor data")
        result["approved"] = False

    status = "APPROVED" if result["approved"] else "CIRCUIT_BREAKER"
    print(f"[Guardrail] {status} | proposed=${proposed_price} | floor=${result['floor']} | band=${result['band_low']}-${result['band_high']}")
    if result["violations"]:
        for v in result["violations"]:
            print(f"  [X] {v}")

    return result
